// CsPilotHost.cs -- CS-Pilot 纯代码宿主（读法：加载厂商程序集 -> 装配上下文 -> 下发/启停/收数/落盘）
//
// 编译（64 位，.NET Framework 4.x）：
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -nologo -out:CsPilotHost.exe CsPilotHost.cs
//
// 用法：
//   CsPilotHost.exe <job.json> [事件输出路径]
//
// 设计纪律（来自 03 反编译 API 清单 §5 / §10.10）：
//   * 只用 public 未混淆成员，绝不引用乱码字段
//   * 枚举一律按名解析，不写死数字
//   * BaseContext.SetConnect 会自动把 conn.OnPackReceive 接到 ctx.PackReceive，不手动接线
//   * 无头装配必须手动置 ctx.ExpMethodState = SysRuning（CSStart 的 ack 到不了 ctx）
//   * 绝不调用 ctx.InitCom（会自建连接覆盖注入的连接）

using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace CsPilot
{
    // ---------------------------------------------------------------- 极简 JSON 读取
    // JavaScriptSerializer 对数组返回 ArrayList、对象返回 Dictionary<string,object>。
    // 这里只做类型收敛，不引入第三方依赖。
    static class J
    {
        static readonly JavaScriptSerializer Ser = new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };

        public static Dictionary<string, object> Parse(string text)
        {
            object o = Ser.DeserializeObject(text);
            var d = o as Dictionary<string, object>;
            if (d == null) throw new Exception("作业文件顶层必须是 JSON 对象");
            return d;
        }

        public static bool Has(Dictionary<string, object> d, string k) { return d.ContainsKey(k) && d[k] != null; }

        public static object Raw(Dictionary<string, object> d, string k)
        {
            object v;
            return d.TryGetValue(k, out v) ? v : null;
        }

        public static string Str(Dictionary<string, object> d, string k, string def = null)
        {
            object v = Raw(d, k);
            return v == null ? def : Convert.ToString(v, CultureInfo.InvariantCulture);
        }

        public static double Num(Dictionary<string, object> d, string k, double def)
        {
            object v = Raw(d, k);
            if (v == null) return def;
            return Convert.ToDouble(v, CultureInfo.InvariantCulture);
        }

        public static bool Bool(Dictionary<string, object> d, string k, bool def)
        {
            object v = Raw(d, k);
            if (v == null) return def;
            return Convert.ToBoolean(v, CultureInfo.InvariantCulture);
        }

        public static List<object> Arr(Dictionary<string, object> d, string k)
        {
            object v = Raw(d, k);
            var list = new List<object>();
            if (v == null) return list;
            var al = v as ArrayList;
            if (al != null) { foreach (object o in al) list.Add(o); return list; }
            var en = v as IEnumerable;
            if (en != null) { foreach (object o in en) list.Add(o); return list; }
            list.Add(v);
            return list;
        }

        public static Dictionary<string, object> Sub(Dictionary<string, object> d, string k)
        {
            object v = Raw(d, k);
            return v as Dictionary<string, object>;
        }
    }

    // ---------------------------------------------------------------- 事件输出
    class EventLog : IDisposable
    {
        readonly StreamWriter _w;
        readonly DateTime _t0 = DateTime.UtcNow;
        readonly object _gate = new object();

        public EventLog(string path)
        {
            _w = new StreamWriter(path, false, new UTF8Encoding(false));
            _w.AutoFlush = true;
        }

        public void Emit(string ev, params object[] kv)
        {
            var sb = new StringBuilder();
            sb.Append("{\"t\":").Append((DateTime.UtcNow - _t0).TotalSeconds.ToString("0.000", CultureInfo.InvariantCulture));
            sb.Append(",\"ev\":\"").Append(Esc(ev)).Append('"');
            for (int i = 0; i + 1 < kv.Length; i += 2)
            {
                sb.Append(',').Append('"').Append(Esc(Convert.ToString(kv[i]))).Append("\":");
                sb.Append(JsonVal(kv[i + 1]));
            }
            sb.Append('}');
            string line = sb.ToString();
            lock (_gate) { _w.WriteLine(line); Console.WriteLine(line); }
        }

        static string JsonVal(object v)
        {
            if (v == null) return "null";
            if (v is bool) return ((bool)v) ? "true" : "false";
            if (v is double) return ((double)v).ToString("R", CultureInfo.InvariantCulture);
            if (v is float) return ((float)v).ToString("R", CultureInfo.InvariantCulture);
            if (v is int || v is long || v is uint || v is ulong) return Convert.ToString(v, CultureInfo.InvariantCulture);
            if (v is DateTime) return "\"" + Esc(((DateTime)v).ToString("o", CultureInfo.InvariantCulture)) + "\"";
            return "\"" + Esc(Convert.ToString(v, CultureInfo.InvariantCulture)) + "\"";
        }

        static string Esc(string s)
        {
            if (s == null) return "";
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }

        public void Dispose() { try { _w.Flush(); _w.Close(); } catch { } }
    }

    // ---------------------------------------------------------------- 宿主主体
    class Host
    {
        // ---- 反射句柄（一次解析，后续复用） ----
        Assembly _bi, _cd, _conn;
        Type _tBaseContext, _tExperiment, _tMethodState, _tVsType, _tExpComSend, _tIConnect;
        Type _tSerialConnect, _tSockectConnect;

        object _connObj;       // IConnect 实现实例
        object _ctx;           // BaseContext
        object _send;          // ExpComSendClass

        EventLog _log;
        readonly Dictionary<string, Type> _paramTypes = new Dictionary<string, Type>();
        readonly Dictionary<string, string> _expNames = new Dictionary<string, string>
        {
            {"ocp", "ID_OCP"}, {"tafel", "ID_PotDynamic"}, {"step", "ID_AnyPotStatic"}, {"eis", "ID_EISVSFRQ"},
            // 恒电流（galvanostatic）家族（2026-11-13 扩展；枚举实值已 dump 验证）
            {"gal_square", "ID_GalSquareWave"},      // 恒流方波
            {"gal_static", "ID_GalStatic"},          // 恒流阶跃
            {"gal_dynamic", "ID_GalDynamic"},        // 电流扫描
            {"gal_charge", "ID_GalCharge"}           // 恒流充放电
        };
        readonly Dictionary<string, string> _paramClassNames = new Dictionary<string, string>
        {
            {"ocp", "OcpParams"}, {"tafel", "PotDynamicParams"}, {"step", "PotSquareParams"}, {"eis", "EISVSfrqParams"},
            {"gal_square", "GalSquareParams"}, {"gal_static", "GalStaticParams"},
            {"gal_dynamic", "GalDynamicParams"}, {"gal_charge", "GalChargeParams"}
        };

        public string AssemblyDir = @"D:\sci\MDI Jade 9";

        static readonly string[] NeedDlls = {
            "CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll", "CSStudio6.Connect.dll",
            "CSStudio6.MathHlp.dll", "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll",
            "CSStudio6.SysLog.dll", "CSStudio6.USControl.dll", "CSStudio6.NetSkin.dll"
        };

        public void Load()
        {
            var asms = new Dictionary<string, Assembly>();
            foreach (string n in NeedDlls)
            {
                string p = Path.Combine(AssemblyDir, n);
                if (!File.Exists(p)) { _log.Emit("warn", "msg", "缺少程序集", "dll", n); continue; }
                asms[n] = Assembly.LoadFrom(p);
            }
            _bi = asms["CSStudio6.BaseInterface.dll"];
            _cd = asms["CSStudio6.CorrData.dll"];
            _conn = asms["CSStudio6.Connect.dll"];

            _tBaseContext = Find(_bi, "BaseContext", false);
            _tExperiment = Find(_bi, "Experiment", true);
            _tMethodState = Find(_bi, "MethodState", true);
            _tVsType = Find(_bi, "VsType", true);
            _tExpComSend = Find(_bi, "ExpComSendClass", false);
            _tIConnect = _conn.GetType("CSStudio6.Connect.Base.IConnect");
            _tSerialConnect = _conn.GetType("CSStudio6.Connect.Com.SerialConnect");
            _tSockectConnect = _conn.GetType("CSStudio6.Connect.Com.SockectConnect");

            foreach (var kv in _paramClassNames)
                _paramTypes[kv.Key] = Find(_cd, kv.Value, false);

            _log.Emit("host", "msg", "程序集加载完成",
                "pf64", Environment.Is64BitProcess,
                "clr", Environment.Version.ToString(),
                "ctx", _tBaseContext.FullName);
        }

        static Type Find(Assembly a, string name, bool isEnum)
        {
            foreach (Type t in a.GetTypes())
            {
                if (t.Name != name) continue;
                if (t.IsEnum != isEnum) continue;
                if (!isEnum && t.IsAbstract) continue;
                return t;
            }
            throw new Exception("找不到类型 " + name + "（enum=" + isEnum + "）于 " + a.GetName().Name);
        }

        string _connEndpoint;
        bool _connUseTcp;
        int _connRetry = 10;

        /// <summary>弃掉当前连接，重新 Open（用于 auto_wired=false 的半死态）。</summary>
        public void Reconnect()
        {
            try
            {
                MethodInfo c = _tIConnect.GetMethod("Close");
                if (c != null) c.Invoke(_connObj, null);
                _log.Emit("host", "msg", "旧连接已 Close");
            }
            catch (Exception e) { _log.Emit("warn", "msg", "Close 失败", "err", Inner(e)); }
            Thread.Sleep(400);
            Connect(_connUseTcp, _connEndpoint, _connRetry, quiet: true);
        }

        public void Connect(bool useTcp, string endpoint, int openRetry)
        {
            Connect(useTcp, endpoint, openRetry, quiet: false);
        }

        void Connect(bool useTcp, string endpoint, int openRetry, bool quiet)
        {
            _connUseTcp = useTcp;
            _connEndpoint = endpoint;
            _connRetry = openRetry;
            Type t = useTcp ? _tSockectConnect : _tSerialConnect;
            _connObj = Activator.CreateInstance(t);
            if (!quiet)
                _log.Emit("connect_begin", "mode", useTcp ? "tcp" : "serial", "endpoint", endpoint, "impl", t.Name);

            MethodInfo open = null;
            foreach (var m in t.GetMethods())
                if (m.Name == "Open" && m.GetParameters().Length == 1) { open = m; break; }
            if (open == null) throw new Exception("找不到 Open(string)");

            MethodInfo isOpen = t.GetMethod("IsOpen");
            bool ok = false;
            for (int i = 1; i <= Math.Max(1, openRetry) && !ok; i++)
            {
                try { open.Invoke(_connObj, new object[] { endpoint }); }
                catch (Exception e) { _log.Emit("warn", "msg", "Open 抛出", "err", Inner(e)); }
                try { ok = isOpen != null && Convert.ToBoolean(isOpen.Invoke(_connObj, null)); }
                catch { ok = false; }
                if (!ok) { _log.Emit("connect_retry", "n", i); Thread.Sleep(1000); }
            }
            _log.Emit("connect", "ok", ok, "endpoint", endpoint);
            if (!ok) throw new Exception("连接失败：" + endpoint);
            // ★ 连上后先静置一小会儿：上一进程遗留的 FIN/RST 可能让 socket 处于
            //   半关闭态，此时看似 IsOpen=true 但收发都不通（auto_wired=false 是征兆）。
            Thread.Sleep(150);

            // 起收包分发线程（5ms 出队 -> OnPackReceive -> ctx.PackReceive）
            MethodInfo cprt = _tIConnect.GetMethod("CheckPackReceiveThread");
            if (cprt == null) cprt = t.GetMethod("CheckPackReceiveThread");
            if (cprt != null) { cprt.Invoke(_connObj, null); _log.Emit("host", "msg", "CheckPackReceiveThread 已启动"); }
            else _log.Emit("warn", "msg", "实现类无 CheckPackReceiveThread");
        }

        /// <summary>建立上下文并把连接接到 ctx.PackReceive。
        /// ★ 关键：SetConnect 只有在连接对象处于健康态时才会自动接线
        ///   （auto_wired=true）。若为 false，说明连上的是半死 socket，
        ///   后续 SendMethodBytes/SysStart/BeginStartWriteFile 全部无效且可能阻塞。
        ///   此时必须弃掉连接重建，否则就是「连上了但零数据」的假象。</summary>
        public void BuildContext()
        {
            for (int attempt = 1; attempt <= 3; attempt++)
            {
                _log.Emit("host", "msg", "BaseContext ctor begin", "attempt", attempt);
                _ctx = Activator.CreateInstance(_tBaseContext);
                _log.Emit("host", "msg", "BaseContext ctor ok");
                _tBaseContext.GetMethod("SetConnect").Invoke(_ctx, new object[] { _connObj });
                _log.Emit("host", "msg", "SetConnect returned");

                object wired = null;
                PropertyInfo onRx = _tIConnect.GetProperty("OnPackReceive");
                if (onRx != null) wired = onRx.GetValue(_connObj, null);
                bool okWired = wired != null;
                _log.Emit("host", "msg", "SetConnect 完成", "auto_wired", okWired, "attempt", attempt);

                if (okWired) break;
                if (attempt == 3)
                    throw new Exception("SetConnect 3 次都未自动接线（auto_wired=false）："
                                        + "连接对象处于半死状态，端点 " + _connEndpoint);
                _log.Emit("warn", "msg", "auto_wired=false，弃连接重建");
                Reconnect();
            }

            // ExpComSendClass(IBaseContext)
            _send = Activator.CreateInstance(_tExpComSend, new object[] { _ctx });
            PropertyInfo pExpSend = _tBaseContext.GetProperty("ExpComSend");
            pExpSend.SetValue(_ctx, _send, null);
            _log.Emit("host", "msg", "发送器已装配");
        }

        public void Probe()
        {
            // SN/型号查询走 SendReturnPackage 双出队，无设备应答时会阻塞到超时；
            // 一律加守卫（3s），拿不到就跳过——本阶段判据是数据链路，不是 SN。
            // ★ 探测是可选的：SendReturnPackage 是同步请求/应答，无应答时会阻塞并把
            //   连接状态搞脏（实测连续 3 次探测后 BeginStartWriteFile 永久阻塞）。
            //   所以只在作业显式要求 probe=true 时才做，且每个只试 1 次。
            string sn = null, pst = null, rom = null;
            if (_probeEnabled)
            {
                Exception e1;
                if (Guarded("GetSerialNumber", () => { sn = Convert.ToString(Call("GetSerialNumber")); }, 2500, out e1)) { }
                if (sn == null || sn.Length == 0)
                    Guarded("GetPstType", () => { pst = Convert.ToString(Call("GetPstType")); }, 2500, out e1);
            }
            else _log.Emit("host", "msg", "探测跳过（probe=false，避免污染连接）");
            _log.Emit("probe", "sn", Trim(sn), "pst", Trim(pst), "rom", Trim(rom));

            // 软版本 + 点数（内存读）
            object soft = _tBaseContext.GetProperty("SoftVersion").GetValue(_ctx, null);
            _log.Emit("host", "msg", "ctx 就绪", "soft", soft, "pointcount", PointCount());
        }

        object Call(string method)
        {
            MethodInfo m = _tExpComSend.GetMethod(method, Type.EmptyTypes);
            if (m == null) throw new Exception("发送器无方法 " + method);
            try { return m.Invoke(_send, null); }
            catch (TargetInvocationException e) { throw e.InnerException ?? e; }
        }

        static string Trim(string s) { return s == null ? null : s.Trim('\0', ' ', '\r', '\n'); }

        static string Inner(Exception e)
        {
            while (e is TargetInvocationException && e.InnerException != null) e = e.InnerException;
            return e.GetType().Name + ": " + e.Message;
        }

        public ulong PointCount()
        {
            object v = _tBaseContext.GetProperty("PointCount").GetValue(_ctx, null);
            return v == null ? 0UL : Convert.ToUInt64(v, CultureInfo.InvariantCulture);
        }

        public string MethodStateName()
        {
            object v = _tBaseContext.GetProperty("ExpMethodState").GetValue(_ctx, null);
            return v == null ? "?" : v.ToString();
        }

        bool IsBusy()
        {
            object v = _tBaseContext.GetProperty("IsBusy").GetValue(_ctx, null);
            return v != null && Convert.ToBoolean(v, CultureInfo.InvariantCulture);
        }

        // ---- 参数对象装配：JSON 里的 key 直接按属性名写入（大小写不敏感） ----
        object BuildParams(string kind, Dictionary<string, object> kv)
        {
            Type pt = _paramTypes[kind];
            object prm = Activator.CreateInstance(pt);

            // 反挂 baseContext（EIS 必须，其余无害）
            PropertyInfo bc = pt.GetProperty("baseContext");
            if (bc == null) foreach (var n in new[] { "BaseContext", "context", "Context" }) { bc = pt.GetProperty(n); if (bc != null) break; }
            if (bc != null && bc.CanWrite) bc.SetValue(prm, _ctx, null);

            // ExpType（枚举按名解析）
            PropertyInfo pe = pt.GetProperty("ExpType");
            if (pe != null && pe.CanWrite && _expNames.ContainsKey(kind))
                pe.SetValue(prm, Enum.Parse(_tExperiment, _expNames[kind], true), null);

            if (kv != null)
            {
                foreach (var pair in kv)
                {
                    PropertyInfo p = pt.GetProperty(pair.Key,
                        BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (p == null || !p.CanWrite)
                    {
                        _log.Emit("param_skip", "kind", kind, "key", pair.Key, "why", p == null ? "no_such_prop" : "readonly");
                        continue;
                    }
                    try { p.SetValue(prm, Coerce(pair.Value, p.PropertyType), null); }
                    catch (Exception e) { _log.Emit("param_fail", "kind", kind, "key", pair.Key, "err", Inner(e)); }
                }
            }
            return prm;
        }

        object Coerce(object v, Type t)
        {
            if (v == null) return null;
            if (t.IsEnum)
            {
                if (v is string) return Enum.Parse(t, (string)v, true);
                return Enum.ToObject(t, Convert.ToInt32(v, CultureInfo.InvariantCulture));
            }
            if (t == typeof(bool)) return Convert.ToBoolean(v, CultureInfo.InvariantCulture);
            if (t == typeof(string)) return Convert.ToString(v, CultureInfo.InvariantCulture);
            if (t == typeof(Single)) return Convert.ToSingle(v, CultureInfo.InvariantCulture);
            if (t == typeof(Double)) return Convert.ToDouble(v, CultureInfo.InvariantCulture);
            if (t == typeof(int)) return Convert.ToInt32(v, CultureInfo.InvariantCulture);
            if (t == typeof(uint)) return Convert.ToUInt32(v, CultureInfo.InvariantCulture);
            if (t == typeof(short)) return Convert.ToInt16(v, CultureInfo.InvariantCulture);
            if (t == typeof(ushort)) return Convert.ToUInt16(v, CultureInfo.InvariantCulture);
            if (t == typeof(byte)) return Convert.ToByte(v, CultureInfo.InvariantCulture);
            if (t == typeof(long)) return Convert.ToInt64(v, CultureInfo.InvariantCulture);
            if (t == typeof(ulong)) return Convert.ToUInt64(v, CultureInfo.InvariantCulture);
            return Convert.ChangeType(v, t, CultureInfo.InvariantCulture);
        }

        // ---- 一次实验 ----
        public Dictionary<string, object> RunExperiment(string kind, Dictionary<string, object> spec, string outDir, bool writeNative)
        {
            var result = new Dictionary<string, object>();
            Dictionary<string, object> pv = J.Sub(spec, "params");
            Dictionary<string, object> stopSpec = J.Sub(spec, "stop");

            string expName = _expNames[kind];
            _log.Emit("exp_begin", "kind", kind, "exp", expName, "pc0", PointCount());

            // 1) ThisExp
            _tBaseContext.GetProperty("ThisExp").SetValue(_ctx, Enum.Parse(_tExperiment, expName, true), null);

            // 2) 参数对象
            object prm = BuildParams(kind, pv);
            string fileName = J.Str(pv, "FileName", kind + "_" + DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture));
            string filePath = J.Str(pv, "FilePath", Path.Combine(outDir, fileName));
            PropertyInfo pf = _paramTypes[kind].GetProperty("FileName");
            if (pf != null && pf.CanWrite && J.Str(pv, "FileName") == null) pf.SetValue(prm, fileName, null);
            PropertyInfo pp = _paramTypes[kind].GetProperty("FilePath");
            if (pp != null && pp.CanWrite && J.Str(pv, "FilePath") == null) pp.SetValue(prm, filePath, null);

            _tBaseContext.GetProperty("BaseParam").SetValue(_ctx, prm, null);

            // 3) ★ 激活运行态（无头装配必需）
            _tBaseContext.GetProperty("ExpMethodState")
                .SetValue(_ctx, Enum.Parse(_tMethodState, "SysRuning", true), null);
            _log.Emit("host", "msg", "ExpMethodState=SysRuning", "kind", kind, "state", MethodStateName());

            // 4) 原生落盘（可选；U1 未知：不依赖窗体时能否写）
            bool nativeOK = false;
            if (writeNative)
            {
                _log.Emit("native_file_begin", "kind", kind, "path", filePath);
                Exception ne;
                // ★ 异步启动（不等返回）：实测 BeginStartWriteFile 在部分连接状态下会
                //   永久阻塞，并把收包线程一并拖死（t2 假阴性根因）。改成 fire-and-forget，
                //   它自己跑通了就写原生 .cor，卡住也不影响主链路采集。
                bool returned = Guarded("BeginStartWriteFile",
                    () => _tBaseContext.GetMethod("BeginStartWriteFile").Invoke(_ctx, new object[] { false }),
                    2000, out ne);
                nativeOK = returned && ne == null;
                _log.Emit("native_file", "kind", kind, "ok", nativeOK,
                    "returned", returned,
                    "err", ne == null ? null : Inner(ne),
                    "path", filePath);
                if (nativeOK && File.Exists(filePath))
                    _log.Emit("native_file", "msg", "头部已落盘", "bytes", new FileInfo(filePath).Length);
            }

            // 5) 下发 + 启动
            ulong pc0 = PointCount();
            try
            {
                object r = null; Exception se;
                bool ok2 = Guarded("SendMethodBytes",
                    () => { r = _tExpComSend.GetMethod("SendMethodBytes").Invoke(_send, new object[] { prm }); },
                    8000, out se);
                _log.Emit("send_method", "kind", kind, "ok", r, "returned", ok2, "err", se == null ? null : Inner(se));
                if (!ok2) { SafeEndFile(nativeOK); return Fail(result, "SendMethodBytes(timeout)"); }
            }
            catch (Exception e) { _log.Emit("exp_fail", "kind", kind, "at", "SendMethodBytes", "err", Inner(e)); SafeEndFile(nativeOK); return Fail(result, "SendMethodBytes"); }

            Thread.Sleep(300);

            try
            {
                object r = null; Exception se;
                bool ok2 = Guarded("SysStart",
                    () => { r = _tExpComSend.GetMethod("SysStart").Invoke(_send, new object[] { true }); },
                    8000, out se);
                _log.Emit("sys_start", "kind", kind, "ok", r, "returned", ok2, "err", se == null ? null : Inner(se));
                if (!ok2) { SafeEndFile(nativeOK); return Fail(result, "SysStart(timeout)"); }
            }
            catch (Exception e) { _log.Emit("exp_fail", "kind", kind, "at", "SysStart", "err", Inner(e)); SafeEndFile(nativeOK); return Fail(result, "SysStart"); }

            // 6) 采集 + 策略判定
            double t0 = Now();
            double maxSec = stopSpec != null ? J.Num(stopSpec, "max_sec", 300) : 300;
            string stopType = stopSpec != null ? J.Str(stopSpec, "type", "max_sec") : "max_sec";
            var policy = Policy.Make(stopType, stopSpec);

            var series = new List<double[]>();   // [t, E, I, Q]
            ulong lastPC = pc0;
            string reason = "max_sec";
            double evalT = 0;

            while (true)
            {
                Thread.Sleep(200);
                double el = Now() - t0;

                List<double[]> fresh = DrainData(ref lastPC);
                foreach (var row in fresh)
                {
                    series.Add(row);
                    // ★ 实时波形显示（2026-11-13）：逐点 sample 事件 → viewer 窗口
                    //   row = [t, E, I, Q]；t 为实验相对秒
                    _log.Emit("sample", "kind", kind, "t", row[0], "e", row[1], "i", row[2]);
                }

                if (writeNative && fresh.Count > 0) { try { _tBaseContext.GetMethod("WriteDataNow").Invoke(_ctx, null); } catch { } }

                if (series.Count > 0)
                {
                    string why;
                    if (policy.Evaluate(series, el, out why))
                    {
                        reason = why; evalT = el;
                        _log.Emit("policy_hit", "kind", kind, "reason", why, "t", el, "n", series.Count);
                        break;
                    }
                }

                if (el > maxSec) { reason = "timeout"; evalT = el; break; }
            }

            _log.Emit("exp_sampling", "kind", kind, "n", series.Count, "elapsed", evalT, "state", MethodStateName(), "busy", IsBusy());

            // 7) 停止
            try
            {
                object r = null; Exception se;
                bool ok2 = Guarded("SysStop",
                    () => { r = _tExpComSend.GetMethod("SysStop").Invoke(_send, null); },
                    8000, out se);
                _log.Emit("sys_stop", "kind", kind, "ok", r, "returned", ok2, "err", se == null ? null : Inner(se));
            }
            catch (Exception e) { _log.Emit("warn", "msg", "SysStop 抛出", "err", Inner(e)); }

            // 等收尾（内存态轮询，不 tail 日志）
            double ws = Now();
            while (Now() - ws < 10 && (IsBusy() || MethodStateName() == "SysRuning")) Thread.Sleep(100);
            _log.Emit("exp_stopped", "kind", kind, "state", MethodStateName(), "busy", IsBusy(), "wait", Now() - ws);

            // 8) 收尾落盘
            SafeEndFile(nativeOK);

            // 9) 自己写一份（不依赖厂商写盘，作为对照/兜底）
            string ownTxt = null;
            try { ownTxt = WriteOwnFile(outDir, kind, expName, prm, series); }
            catch (Exception e) { _log.Emit("warn", "msg", "自写文件失败", "err", Inner(e)); }

            // 10) 文件事实
            var files = new List<object>();
            foreach (var f in new[] { filePath + ".cor", filePath + ".txt", filePath }) FileFact(files, f);
            if (ownTxt != null) FileFact(files, ownTxt);

            ulong pc1 = PointCount();
            result["kind"] = kind;
            result["points"] = series.Count;
            result["pointcount_delta"] = pc1 - pc0;
            result["reason"] = reason;
            result["elapsed"] = evalT;
            result["native_writer"] = nativeOK;
            result["files"] = files;
            result["own_txt"] = ownTxt;

            _log.Emit("exp_done", "kind", kind, "points", series.Count, "dp", pc1 - pc0,
                "reason", reason, "elapsed", evalT, "files", files.Count);

            // 清理（下一实验前）
            try { _tBaseContext.GetMethod("ReSetData").Invoke(_ctx, null); } catch { }
            Thread.Sleep(300);
            return result;
        }

        Dictionary<string, object> Fail(Dictionary<string, object> r, string at)
        {
            r["ok"] = false; r["fail_at"] = at;
            return r;
        }

        void SafeEndFile(bool nativeOK)
        {
            if (!nativeOK) return;
            Exception ee;
            bool okE = Guarded("EndWriteFile",
                () => _tBaseContext.GetMethod("EndWriteFile").Invoke(_ctx, null), 5000, out ee);
            _log.Emit("native_file", "msg", "EndWriteFile", "ok", okE && ee == null,
                "err", ee == null ? null : Inner(ee));
        }

        void FileFact(List<object> sink, string path)
        {
            var d = new Dictionary<string, object>();
            d["path"] = path;
            if (File.Exists(path)) { d["exists"] = true; d["bytes"] = (long)new FileInfo(path).Length; }
            else d["exists"] = false;
            sink.Add(d);
        }

        // ---- 从 IDataItem 增量取新点 ----
        // 游标按 List 下标走（不是 PointCount）：PointCount 由 ctx 自增，与 List 长度可能不同步，
        // 用 List 下标才不会重复或漏读。
        int _dataCursor;

        List<double[]> DrainData(ref ulong lastPC)
        {
            var rows = new List<double[]>();
            ulong pc = PointCount();

            PropertyInfo pData = _tBaseContext.GetProperty("DataItem");
            object di = pData.GetValue(_ctx, null);
            if (di == null) { lastPC = pc; return rows; }
            Type dt = di.GetType();

            object lockObj = SafeGet(dt, di, "DataLock");
            bool locked = false;
            try
            {
                if (lockObj != null) { Monitor.Enter(lockObj); locked = true; }

                var tv = SafeGet(dt, di, "TimeValues") as IList;
                var vv = SafeGet(dt, di, "VolteValues") as IList;
                var cv = SafeGet(dt, di, "CurrentValues") as IList;
                var qv = SafeGet(dt, di, "ChargeValues") as IList;

                int n = tv != null ? tv.Count : 0;
                if (_dataCursor > n) _dataCursor = 0;      // 被 ReSetData 清过 -> 重头
                for (int i = _dataCursor; i < n; i++)
                {
                    rows.Add(new[]
                    {
                        NumAt(tv, i), NumAt(vv, i), NumAt(cv, i), NumAt(qv, i)
                    });
                }
                _dataCursor = n;
            }
            catch (Exception e) { _log.Emit("warn", "msg", "DrainData 失败", "err", Inner(e)); }
            finally { if (locked) Monitor.Exit(lockObj); }

            lastPC = pc;
            return rows;
        }

        static object SafeGet(Type t, object o, string name)
        {
            try
            {
                PropertyInfo p = t.GetProperty(name);
                return p == null ? null : p.GetValue(o, null);
            }
            catch { return null; }
        }

        static double NumAt(IList l, int i)
        {
            if (l == null || i >= l.Count) return double.NaN;
            object v = l[i];
            return v == null ? double.NaN : Convert.ToDouble(v, CultureInfo.InvariantCulture);
        }

        // ---- 自写 txt（CSStudioFile 头 + 三列）----
        string WriteOwnFile(string outDir, string kind, string expName, object prm, List<double[]> series)
        {
            Directory.CreateDirectory(outDir);
            string path = Path.Combine(outDir, "own_" + kind + ".txt");
            string head = "CORRW ASCII\r\nCsPilot pure-code host\r\n" + expName + "\r\nData:" +
                          DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) +
                          "   Time:" + DateTime.Now.ToString("HH:mm:ss", CultureInfo.InvariantCulture) + "\r\n";
            try
            {
                MethodInfo gs = prm.GetType().GetMethod("GetSaveString");
                if (gs != null) head += "ExpParmas:" + Convert.ToString(gs.Invoke(prm, null)) + "\r\n";
            }
            catch { }

            var sb = new StringBuilder();
            sb.Append(head);
            sb.Append("E(V)\ti(A/cm2)\tT(s)\r\n");
            for (int i = 0; i < series.Count; i++)
            {
                var r = series[i];
                sb.Append(r[1].ToString("0.00000E+00", CultureInfo.InvariantCulture)).Append('\t')
                  .Append(r[2].ToString("0.00000E+00", CultureInfo.InvariantCulture)).Append('\t')
                  .Append(r[0].ToString("0.00000", CultureInfo.InvariantCulture));
                if (i < series.Count - 1) sb.Append("\r\n");
            }
            File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));
            return path;
        }

        public void Close()
        {
            try
            {
                MethodInfo c = _tIConnect.GetMethod("Close");
                if (c != null) c.Invoke(_connObj, null);
            }
            catch { }
        }

        static double Now() { return (double)Environment.TickCount / 1000.0; }


        // ---- 超时守卫：厂商某些方法在无窗体/无应答时会永久阻塞，必须隔离 ----
        // 返回 true = 在超时内返回；false = 超时（调用被丢在后台线程里，不影响主流程继续）
        bool Guarded(string tag, Action act, int timeoutMs, out Exception err)
        {
            Exception e2 = null;
            var th = new Thread(() => { try { act(); } catch (Exception e) { e2 = e; } });
            th.IsBackground = true;
            th.Start();
            bool ok = th.Join(timeoutMs);
            err = e2;
            if (!ok) _log.Emit("guard_timeout", "tag", tag, "ms", timeoutMs);
            return ok;
        }

        bool _probeEnabled = true;
        public void SetProbe(bool on) { _probeEnabled = on; }

        public void SetLog(EventLog l) { _log = l; }


        public bool HasKind(string kind) { return _paramTypes.ContainsKey(kind) && _expNames.ContainsKey(kind); }
    }

    // ---------------------------------------------------------------- 停止策略
    interface IStopPolicy
    {
        bool Evaluate(List<double[]> series, double elapsed, out string why);
    }

    static class Policy
    {
        public static IStopPolicy Make(string type, Dictionary<string, object> spec)
        {
            switch ((type ?? "max_sec").ToLowerInvariant())
            {
                case "stabilize": return new Stabilize(spec);
                case "current_density": return new CurrentDensity(spec);
                default: return new MaxSeconds(spec);
            }
        }

        class MaxSeconds : IStopPolicy
        {
            readonly double _sec;
            public MaxSeconds(Dictionary<string, object> s) { _sec = s != null ? J.Num(s, "sec", 60) : 60; }
            public bool Evaluate(List<double[]> series, double elapsed, out string why)
            {
                why = "max_sec";
                return elapsed >= _sec;
            }
        }

        // 判稳：窗口内斜率(mV/min) 达标 + 峰峰值(mV) 达标 + 保持 hold 秒
        // 纪律来自 00 §5.2：只用斜率会被正负抵消骗过，必须加峰峰值硬约束
        class Stabilize : IStopPolicy
        {
            readonly double _slopeLimit, _holdSec, _windowSec, _ptpLimit;
            double _holdStart = -1;
            public Stabilize(Dictionary<string, object> s)
            {
                _slopeLimit = s != null ? J.Num(s, "slope_mv_per_min", 5.0) : 5.0;
                _holdSec = s != null ? J.Num(s, "hold_sec", 60) : 60;
                _windowSec = s != null ? J.Num(s, "window_sec", 30) : 30;
                _ptpLimit = s != null ? J.Num(s, "peak_to_peak_mv", 5.0) : 5.0;
            }

            public bool Evaluate(List<double[]> series, double elapsed, out string why)
            {
                why = null;
                if (series.Count < 4) return false;
                double tLast = series[series.Count - 1][0];
                double tFrom = tLast - _windowSec;

                int i0 = series.Count - 1;
                while (i0 > 0 && series[i0][0] > tFrom) i0--;

                double min = double.MaxValue, max = double.MinValue, sT = 0, sE = 0, sTT = 0, sTE = 0;
                int n = 0;
                for (int i = i0; i < series.Count; i++)
                {
                    double t = series[i][0], e = series[i][1];
                    if (double.IsNaN(e)) continue;
                    if (e < min) min = e;
                    if (e > max) max = e;
                    sT += t; sE += e; sTT += t * t; sTE += t * e; n++;
                }
                if (n < 4) return false;

                double ptp_mv = (max - min) * 1000.0;
                double den = n * sTT - sT * sT;
                double slope_mv_min = den == 0 ? double.MaxValue : ((n * sTE - sT * sE) / den) * 60.0 * 1000.0;

                if (Math.Abs(slope_mv_min) <= _slopeLimit && ptp_mv <= _ptpLimit)
                {
                    if (_holdStart < 0) _holdStart = elapsed;
                    if (elapsed - _holdStart >= _holdSec)
                    {
                        why = "stabilized";
                        return true;
                    }
                }
                else _holdStart = -1;
                return false;
            }
        }

        // 判停：电流密度连续 confirm_n 次超阈值
        class CurrentDensity : IStopPolicy
        {
            readonly double _limit; readonly int _confirm; int _hit;
            public CurrentDensity(Dictionary<string, object> s)
            {
                _limit = s != null ? J.Num(s, "limit", 5.0) : 5.0;
                _confirm = (int)(s != null ? J.Num(s, "confirm_n", 2) : 2);
            }
            public bool Evaluate(List<double[]> series, double elapsed, out string why)
            {
                why = null;
                if (series.Count == 0) return false;
                double i = Math.Abs(series[series.Count - 1][2]);
                if (double.IsNaN(i)) return false;
                if (i >= _limit)
                {
                    _hit++;
                    if (_hit >= _confirm) { why = "current_density"; return true; }
                }
                else _hit = 0;
                return false;
            }
        }
    }

    // ---------------------------------------------------------------- 入口
    static class Program
    {
        static int Main(string[] args)
        {
            if (args.Length < 1)
            {
                Console.Error.WriteLine("用法: CsPilotHost.exe <job.json> [events.jsonl]");
                return 2;
            }
            string jobPath = args[0];
            string evPath = args.Length > 1 ? args[1] : Path.Combine(Path.GetDirectoryName(Path.GetFullPath(jobPath)), "events.jsonl");

            using (var log = new EventLog(evPath))
            {
                // 看门狗：厂商代码里有不可中断的阻塞点，宁可强退也要留下事件日志
                int wdSec = 300;
                var wd = new Thread(() => {
                    Thread.Sleep(wdSec * 1000);
                    log.Emit("fatal", "err", "watchdog timeout", "sec", wdSec);
                    Environment.Exit(3);
                });
                wd.IsBackground = true;
                wd.Start();

                var host = new Host();
                host.SetLog(log);
                int rc = 1;
                try
                {
                    var job = J.Parse(File.ReadAllText(jobPath, Encoding.UTF8));

                    string asmDir = J.Str(job, "assembly_dir", @"D:\sci\MDI Jade 9");
                    host.AssemblyDir = asmDir;

                    string mode = J.Str(job, "mode", "serial");
                    string endpoint = J.Str(job, "endpoint", "COM90");
                    string outDir = J.Str(job, "out_dir", Path.Combine(Path.GetDirectoryName(Path.GetFullPath(jobPath)), "out"));
                    bool writeNative = J.Bool(job, "native_writer", true);
                    int openRetry = (int)J.Num(job, "open_retry", 10);
                    Directory.CreateDirectory(outDir);

                    log.Emit("job", "file", jobPath, "mode", mode, "endpoint", endpoint, "out_dir", outDir, "native_writer", writeNative);

                    host.SetProbe(J.Bool(job, "probe", true));
                    host.Load();
                    host.Connect(mode.ToLowerInvariant() == "tcp", endpoint, openRetry);
                    host.BuildContext();
                    host.Probe();

                    var results = new List<object>();
                    foreach (object e in J.Arr(job, "experiments"))
                    {
                        var spec = e as Dictionary<string, object>;
                        if (spec == null) continue;
                        string kind = J.Str(spec, "kind", "ocp").ToLowerInvariant();
                        if (!host.HasKind(kind)) { log.Emit("warn", "msg", "未知实验类型", "kind", kind); continue; }
                        results.Add(host.RunExperiment(kind, spec, outDir, writeNative));
                    }

                    host.Close();

                    bool allOK = results.Count > 0;
                    foreach (object r in results)
                    {
                        var d = r as Dictionary<string, object>;
                        if (d != null && d.ContainsKey("fail_at")) allOK = false;
                    }
                    log.Emit("done", "ok", allOK, "n_exp", results.Count, "results", results);
                    rc = allOK ? 0 : 1;
                }
                catch (Exception ex)
                {
                    log.Emit("fatal", "err", ex.GetType().Name + ": " + ex.Message, "stack", ex.StackTrace);
                    rc = 1;
                }
                log.Emit("exit", "rc", rc);
                // ★ 必须用 Environment.Exit：IConnect.CheckPackReceiveThread 起的是**前台线程**，
                //   Main 返回后 CLR 会一直等它退出 → 宿主永不结束（runner 侧表现为 rc=124 假超时）。
                log.Dispose();
                Environment.Exit(rc);
                return rc;
            }
        }
    }
}
