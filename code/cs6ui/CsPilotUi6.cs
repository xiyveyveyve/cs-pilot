// CsPilotUi6.cs — CS6 UI 宿主：进程内拉起软件主窗体（用户看进度），代码驱动 OCP→EIS→动电位
// 装配原则：frmMain 自装 baseContext（软件原生 LAN 搜索→自动连模拟器）；宿主只读 ctx + 创建
// ExpComSendClass(ctx) 后按 Phase2-4 验证链跑实验（ThisExp/BuildParams/SysRuning/BeginStartWriteFile/
// SendMethodBytes/SysStart/轮询 PointCount/WriteDataNow/SysStop）。若 90s 内 ctx 未就绪则手动装配兜底。
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

static class Ui6
{
    const string DIR = @"D:\sci\MDI Jade 9";
    const string OUTDIR = @"C:\Users\xiyve\Documents\Corrtest\Data";
    static readonly string LogPath = @"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\ui6_run.txt";

    static Assembly _bi, _cd, _conn, _exe;
    static Type _tBaseContext, _tExperiment, _tMethodState, _tVsType, _tExpComSend;
    static bool _ilDumped = false;
    static bool _prmDumped = false;
    static Dictionary<string, Type> _paramTypes = new Dictionary<string, Type>();
    static readonly Dictionary<string, string> _paramClassNames = new Dictionary<string, string>
    {
        { "ocp", "OcpParams" }, { "tafel", "PotDynamicParams" }, { "eis", "EISVSfrqParams" }
    };
    static readonly Dictionary<string, string> _expNames = new Dictionary<string, string>
    {
        { "ocp", "ID_OCP" }, { "tafel", "ID_PotDynamic" }, { "eis", "ID_EISVSFRQ" }
    };
    // 验证过的回归参数（tests/jobs/auto_M1.json、t2_all4.json）
    static readonly Dictionary<string, Dictionary<string, object>> _params = new Dictionary<string, Dictionary<string, object>>
    {
        { "ocp", new Dictionary<string, object> { { "TestTime", 120f }, { "TestTimeUnit", 1 } } },
        { "eis", new Dictionary<string, object> { { "Init_Fre", 10000f }, { "Final_Fre", 0.1f }, { "SineAmp", 10f }, { "SineBias", 0f }, { "TenTwice", 10f } } },
        { "tafel", new Dictionary<string, object> { { "InitE", -0.3f }, { "MidEOne", -0.3f }, { "MidETwo", -0.3f }, { "FinalE", 0.8f },
            { "ScanRate", 25f }, { "ScanRateUnit", 0 }, { "OcpValue", -0.14f },
            { "InitEVsOcp", "vsRef" }, { "MidEOneVsOcp", "vsRef" }, { "MidETwoVsOcp", "vsRef" }, { "FinalEVsOcp", "vsRef" } } }
    };
    static readonly Dictionary<string, int> _maxSec = new Dictionary<string, int> { { "ocp", 200 }, { "eis", 200 }, { "tafel", 300 } };

    static object _form, _ctx, _send;

    static void P(string s)
    {
        string line = DateTime.Now.ToString("HH:mm:ss.fff", CultureInfo.InvariantCulture) + " " + s;
        Console.WriteLine(line);
        try { File.AppendAllText(LogPath, line + "\r\n"); } catch { }
    }
    static string Inner(Exception e) { Exception x = e; while (x.InnerException != null) x = x.InnerException; return x.GetType().Name + ": " + x.Message; }

    static object GetProp(object o, string name)
    {
        if (o == null) return null;
        PropertyInfo p = o.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        if (p == null || !p.CanRead) return null;
        try { return p.GetValue(o, null); } catch { return null; }
    }
    static bool SetProp(object o, string name, object v)
    {
        PropertyInfo p = o.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.IgnoreCase);
        if (p == null || !p.CanWrite) return false;
        try { p.SetValue(o, Coerce(v, p.PropertyType), null); return true; }
        catch (Exception e) { P("SetProp err " + name + " ← " + (v == null ? "null" : v.GetType().FullName) + " : " + Inner(e)); return false; }
    }
    static object Coerce(object v, Type t)
    {
        if (v == null) return null;
        if (t.IsInstanceOfType(v)) return v; // 接口/引用类型直接过（IBaseContext 等），不能走 ChangeType
        if (t.IsEnum) return v is string ? Enum.Parse(t, (string)v, true) : Enum.ToObject(t, Convert.ToInt64(v, CultureInfo.InvariantCulture));
        if (t == typeof(bool)) return Convert.ToBoolean(v, CultureInfo.InvariantCulture);
        if (t == typeof(string)) return Convert.ToString(v, CultureInfo.InvariantCulture);
        if (t == typeof(float)) return Convert.ToSingle(v, CultureInfo.InvariantCulture);
        if (t == typeof(double)) return Convert.ToDouble(v, CultureInfo.InvariantCulture);
        return Convert.ChangeType(v, t, CultureInfo.InvariantCulture);
    }

    static void LoadAsms()
    {
        string[] dlls = {
            "CSStudio6.NetSkin.dll", "CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll", "CSStudio6.Connect.dll",
            "CSStudio6.MathHlp.dll", "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll", "CSStudio6.SysLog.dll",
            "CSStudio6.USControl.dll", "CSStudio6.CorrForm.dll", "CSStudio6.Analysis.dll", "CSStudio6.ExtModule.dll" };
        foreach (string n in dlls)
        {
            string p = Path.Combine(DIR, n);
            if (!File.Exists(p)) { P("warn 缺 " + n); continue; }
            Assembly a = Assembly.LoadFrom(p);
            if (n == "CSStudio6.BaseInterface.dll") _bi = a;
            if (n == "CSStudio6.CorrData.dll") _cd = a;
            if (n == "CSStudio6.Connect.dll") _conn = a;
        }
        _exe = Assembly.LoadFrom(Path.Combine(DIR, "CorrTest.CSStudio.exe"));
        _tBaseContext = Find(_bi, "BaseContext", false);
        _tExperiment = Find(_bi, "Experiment", true);
        _tMethodState = Find(_bi, "MethodState", true);
        _tExpComSend = Find(_bi, "ExpComSendClass", false);
        foreach (var kv in _paramClassNames) _paramTypes[kv.Key] = Find(_cd, kv.Value, false);
        P("程序集加载完成 ctx=" + _tBaseContext.FullName);
    }
    static Type Find(Assembly a, string name, bool isEnum)
    {
        foreach (Type t in a.GetTypes())
        {
            if (t.Name != name || t.IsEnum != isEnum) continue;
            if (!isEnum && t.IsAbstract) continue;
            return t;
        }
        throw new Exception("找不到类型 " + name);
    }

    // ---- 手动装配兜底（CsPilotHost.BuildContext 模式）----
    static bool ManualWire()
    {
        try
        {
            Type sc = _conn.GetType("CSStudio6.Connect.Com.SockectConnect");
            object connObj = Activator.CreateInstance(sc);
            MethodInfo open = null;
            foreach (MethodInfo m in sc.GetMethods())
                if (m.Name == "Open" && m.GetParameters().Length == 1) { open = m; break; }
            open.Invoke(connObj, new object[] { "127.0.0.1:31101" });
            Thread.Sleep(200);
            MethodInfo cprt = sc.GetMethod("CheckPackReceiveThread");
            if (cprt != null) cprt.Invoke(connObj, null);
            _ctx = Activator.CreateInstance(_tBaseContext);
            _tBaseContext.GetMethod("SetConnect").Invoke(_ctx, new object[] { connObj });
            if (_form != null) SetProp(_form, "baseContext", _ctx);
            P("手动装配兜底完成（SockectConnect→31101）");
            return true;
        }
        catch (Exception e) { P("手动装配失败 " + Inner(e)); return false; }
    }

    // ---- Runner：等 ctx → 面积/型号 → 三实验 ----
    static void Runner()
    {
        try
        {
            // 1) 软件原生启动（Main 已调 EntryPoint）；默认用软件自己的 baseContext（frmMain 自持），
            //    让数据流过软件 UI 层 → 图表正常显示。--manual 才走手动线。
            Form fmForm = null;
            for (int i = 0; i < 30; i++)
            {
                Thread.Sleep(1000);
                foreach (Form f in Application.OpenForms)
                    if (f.GetType().FullName == "CorrTest.CSStudio.frmMain") { fmForm = f; break; }
                if (fmForm != null) break;
            }
            _form = fmForm;
            P("frmMain " + (fmForm != null ? "已出现" : "未出现（继续手动线）"));

            bool manual = Array.IndexOf(_args, "--manual") >= 0;
            object softCtx = fmForm != null ? GetProp(fmForm, "baseContext") : null;
            // 等软件原生 LAN 连接完成（com 非空 = 软件自己连上模拟器）
            object softConn = null;
            if (softCtx != null && !manual)
            {
                for (int i = 0; i < 20; i++)
                {
                    Thread.Sleep(1000);
                    MethodInfo gc = softCtx.GetType().GetMethod("GetConnect", Type.EmptyTypes);
                    softConn = gc != null ? gc.Invoke(softCtx, null) : null;
                    if (softConn != null) break;
                }
                if (softConn != null)
                {
                    // 等握手稳定（软件原生连接的握手链 + IsBusy 结束）
                    for (int i = 0; i < 16; i++) { Thread.Sleep(1000); if (!Convert.ToBoolean(GetProp(softCtx, "IsBusy"))) break; }
                    Thread.Sleep(3000);
                }
            }
            if (!manual && softCtx != null && softConn != null)
            {
                _ctx = softCtx;
                P("ctx 就绪 " + _ctx.GetType().Name + "（软件原生 ctx，UI 图表链全活）");
                // ExpComSend：软件原生 ctx 自带（连接完成时软件自己 new 过）——只在为空时补
                object softSend = GetProp(_ctx, "ExpComSend");
                if (softSend != null) { _send = softSend; P("ExpComSend 用软件自带实例"); }
                else { _send = Activator.CreateInstance(_tExpComSend, new object[] { _ctx }); SetProp(_ctx, "ExpComSend", _send); P("ExpComSend 软件侧为空，自 new 补挂"); }
            }
            else
            {
            if (!ManualWire()) { P("FATAL 手动装配失败"); return; }
            P("ctx 就绪 " + _ctx.GetType().Name + "（手动线）");

            // 2) 握手缓冲（SetConnect 后软件无自动握手，手动线仅需短暂稳定）
            Thread.Sleep(2000);
            P("手动线稳定，开始装配");

            // 2.5) ctx 属性探测（找面积/型号载体）
            P("ctx 属性清单:");
            foreach (PropertyInfo pr in _ctx.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                object v = null; try { v = pr.CanRead ? pr.GetValue(_ctx, null) : null; } catch { }
                P("    " + pr.PropertyType.Name + " " + pr.Name + " = " + (v == null ? "null" : v.ToString()));
            }

            // 3) ExpComSend（手动 ctx 一律自 new，与无头宿主一致）
            _send = Activator.CreateInstance(_tExpComSend, new object[] { _ctx });
            SetProp(_ctx, "ExpComSend", _send);
            P("ExpComSendClass 就绪（自new+挂ctx）");
            } // end manual-fallback else

            // 4) 面积=1 型号=x（CellParam 动态匹配）
            object cell = GetProp(_ctx, "CellParam");
            if (cell == null)
            {
                // 多通道兜底：ChannelCellParam
                cell = GetProp(_ctx, "ChannelCellParam");
            }
            if (cell != null)
            {
                var done = new List<string>();
                foreach (PropertyInfo pr in cell.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
                {
                    string ln = pr.Name.ToLowerInvariant();
                    if (!pr.CanWrite) continue;
                    if ((ln.Contains("area") || ln.Contains("surface")) && pr.PropertyType == typeof(float)) { pr.SetValue(cell, 1f, null); done.Add(pr.Name + "=1"); }
                    else if ((ln.Contains("model") || ln.Contains("xinghao")) && pr.PropertyType == typeof(string)) { pr.SetValue(cell, "x", null); done.Add(pr.Name + "=x"); }
                }
                P("CellParam 填充: " + string.Join(",", done.ToArray()));
                if (done.Count == 0)
                {
                    P("CellParam 属性清单（调试）:");
                    foreach (PropertyInfo pr in cell.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
                        P("    " + pr.PropertyType.Name + " " + pr.Name);
                }
            }
            else P("warn ctx 无 CellParam（面积/型号跳过）");

            // 5) 三实验
            var results = new List<string>();
            foreach (string kind in new[] { "ocp", "eis", "tafel" })
            {
                _first = kind == "ocp";
                string r = RunExperiment(kind);
                results.Add(kind + "=" + r);
                P("EXP-DONE " + kind + " → " + r);
            }
            P("ALL-DONE " + string.Join(" | ", results.ToArray()));
        }
        catch (Exception e) { P("FATAL Runner " + Inner(e) + "\n" + e.StackTrace); }
    }

    static string RunExperiment(string kind)
    {
        try
        {
            string expName = _expNames[kind];
            SetProp(_ctx, "ThisExp", Enum.Parse(_tExperiment, expName, true));

            object prm = Activator.CreateInstance(_paramTypes[kind]);
            // baseContext 装配：四连 fallback（对齐无头宿主 BuildParams）+ 读回验证
            bool bcOk = SetProp(prm, "baseContext", _ctx);
            if (!bcOk) bcOk = SetProp(prm, "BaseContext", _ctx);
            if (!bcOk) bcOk = SetProp(prm, "context", _ctx);
            if (!bcOk) bcOk = SetProp(prm, "Context", _ctx);
            object bcBack = null;
            foreach (string bn in new string[] { "baseContext", "BaseContext", "context", "Context" })
            { bcBack = GetProp(prm, bn); if (bcBack != null) break; }
            P("[" + kind + "] baseContext 装配=" + (bcOk ? "OK" : "FAIL") + " 读回=" + (bcBack == null ? "null!!!" : "非空"));
            if (!_prmDumped)
            {
                _prmDumped = true;
                P("[prm属性] " + prm.GetType().FullName + " 全属性:");
                foreach (PropertyInfo pr in prm.GetType().GetProperties(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                    P("    " + pr.PropertyType.Name + " " + pr.Name + " w=" + pr.CanWrite);
            }
            PropertyInfo pe = prm.GetType().GetProperty("ExpType", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (pe != null && pe.CanWrite) pe.SetValue(prm, Enum.Parse(_tExperiment, expName, true), null);
            foreach (var kv in _params[kind])
            {
                bool ok = SetProp(prm, kv.Key, kv.Value);
                if (!ok) P("param_skip " + kind + "." + kv.Key);
            }
            SetProp(prm, "FileName", "ui6_" + kind);
            SetProp(prm, "FilePath", Path.Combine(OUTDIR, "ui6_" + kind + ".cor"));

            SetProp(_ctx, "BaseParam", prm);
            SetProp(_ctx, "ExpMethodState", Enum.Parse(_tMethodState, "SysRuning", true));
            P("[" + kind + "] 参数装配完成 ExpType=" + expName);

            // ---- UI 原生模式：调 frmMain.BeginExpEx(prm)，软件自己走完整流程（建图表→发帧→画线）----
            bool uiMode = Array.IndexOf(_args, "--manual") < 0;
            // 落盘基线（方法层作用域：UI 分支要刷新，采集轮询要用）
            string watchBase = Path.GetFileNameWithoutExtension("ui6_" + kind);
            string watchDir2 = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
            long w0 = WatchLen(OUTDIR, watchBase);
            if (w0 < 0) w0 = WatchLen(watchDir2, watchBase);
            if (w0 < 0) w0 = 0;
            MethodInfo miBegin = null;
            if (uiMode && _form != null)
            {
                try
                {
                    foreach (MethodInfo m in _form.GetType().GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                    {
                        if (m.Name == "BeginExp") { miBegin = m; break; }
                        if (m.Name == "BeginExpEx" && miBegin == null) miBegin = m;
                    }
                }
                catch { }
            }
            if (uiMode && miBegin != null)
            {
                if (!_first) StopCurrent(kind);   // 开新实验前清残留（首实验跳过）
                P("[" + kind + "] UI 模式：调 " + miBegin.Name + " " + miBegin.ToString());
                try
                {
                    ((Form)_form).BeginInvoke((MethodInvoker)delegate
                    {
                        if (miBegin.Name == "BeginExp")
                            miBegin.Invoke(_form, new object[] { Enum.Parse(_tExperiment, expName, true), false });
                        else
                            miBegin.Invoke(_form, new object[] { prm });
                    });
                }
                catch (Exception e) { P("[" + kind + "] " + miBegin.Name + " EXC " + Inner(e)); }
                // helper：等参数窗弹出 → 点「确定」（模态窗期间 BeginInvoke 那头卡在 ShowDialog，正常）
                bool okClicked = WaitParamAndOk(kind);
                P("[" + kind + "] 参数窗确定=" + (okClicked ? "已点" : "未出现") + "，BaseGraph=" + (GetProp(_ctx, "BaseGraph") == null ? "null" : "已创建"));
                // 参数窗确定后刷新基线（确定前实验不写盘）
                long wb2 = WatchLen(OUTDIR, watchBase); if (wb2 < 0) wb2 = WatchLen(watchDir2, watchBase);
                if (wb2 >= 0) w0 = wb2;
                P("[" + kind + "] 基线 w0=" + w0);
            }
            else
            {

            // 原生落盘 fire-and-forget
            try { _tBaseContext.GetMethod("BeginStartWriteFile").Invoke(_ctx, new object[] { false }); }
            catch (Exception e) { P("[" + kind + "] BeginStartWriteFile err " + Inner(e)); }

            object r1 = _tExpComSend.GetMethod("SendMethodBytes").Invoke(_send, new object[] { prm });
            P("[" + kind + "] SendMethodBytes → " + r1);
            Thread.Sleep(300);
            object r2 = _tExpComSend.GetMethod("SysStart").Invoke(_send, new object[] { true });
            P("[" + kind + "] SysStart → " + r2);
            } // end manual mode

            // 采集轮询（UI 模式）：看落盘文件增长（OUTDIR 或桌面，软件可能自选目录）+ 提示框看护
            string watchFile = Path.Combine(OUTDIR, "ui6_" + kind + ".cor");
            int maxS = _maxSec[kind];
            double t0 = Environment.TickCount;
            double lastChange = 0; long lastLen = w0;
            bool sawBusy = false; int stableHits = 0;
            while (true)
            {
                Thread.Sleep(500);
                double el = (Environment.TickCount - t0) / 1000.0;
                // 提示框看护
                DismissMsgBoxes(kind);
                // UI 模式：IsBusy 起→落 = 实验自然结束（Obsidian 01：实验到时软件自己停）
                if (uiMode)
                {
                    object busy = GetProp(_ctx, "IsBusy");
                    bool b = busy is bool && (bool)busy;
                    if (b) { if (!sawBusy) P("[" + kind + "] IsBusy=True 实验运行中 t=" + el.ToString("F1")); sawBusy = true; }
                    else if (sawBusy)
                    {
                        Thread.Sleep(2000);
                        DismissMsgBoxes(kind);
                        P("[" + kind + "] IsBusy=False 实验结束 t=" + el.ToString("F1"));
                        break;
                    }
                }
                // 文件增长：OUTDIR\ui6_kind.* 或 Desktop\ui6_kind.*
                long len = WatchLen(OUTDIR, watchBase);
                if (len < 0) len = WatchLen(watchDir2, watchBase);
                if (len != lastLen) { lastLen = len; lastChange = el; stableHits = 0; }
                else if (len > 0) stableHits++;
                if (w0 >= 0 && len > w0 && el - lastChange > 12.0 && el > 15) { P("[" + kind + "] 文件稳定 len=" + len + " t=" + el.ToString("F1")); break; }
                if (w0 < 0 && len >= 0) { w0 = len; lastChange = el; P("[" + kind + "] 文件出现 len=" + len); }
                if (el > maxS) { P("[" + kind + "] 超时 len=" + lastLen + " busy=" + sawBusy + " t=" + el.ToString("F1")); break; }
            }
            // UI 模式：软件自己走完整落盘流程，宿主不插手（Obsidian 01：正常测试流程产物）
            if (uiMode)
            {
                StopCurrent(kind);   // 显式停测试，确保下一项能开
            }
            else
            {
                try { _tBaseContext.GetMethod("WriteDataNow").Invoke(_ctx, null); } catch { }
                Thread.Sleep(300);
                try { _tExpComSend.GetMethod("SysStop").Invoke(_send, null); } catch { }
                Thread.Sleep(500);
                try { _tBaseContext.GetMethod("EndWriteFile").Invoke(_ctx, null); } catch { }
            }
            string file = Path.Combine(OUTDIR, "ui6_" + kind + ".cor");
            P("[" + kind + "] 停止完成 落盘=" + (File.Exists(file) ? new FileInfo(file).Length + "B" : "无文件"));
            return "len=" + lastLen + " file=" + (File.Exists(file) ? "OK" : "MISS");
        }
        catch (Exception e)
        {
            Exception x = e; while (x.InnerException != null) x = x.InnerException;
            P("[" + kind + "] EXC " + Inner(e) + "\n[ST] " + x.StackTrace);
            return "EXC:" + Inner(e);
        }
    }

    static ulong GetPointCount()
    {
        try
        {
            object v = GetProp(_ctx, "PointCount");
            return v == null ? 0 : Convert.ToUInt64(v, CultureInfo.InvariantCulture);
        }
        catch { return 0; }
    }

    // 等参数窗（模态）出现 → 填文件名 → 点「确定」；期间自动应答「是否停止」提示框
    // Obsidian 01 教训：达停止条件后必须显式停测试，否则下一项参数窗不弹（GUI 分支修过好几遍的坑）
    static void StopCurrent(string kind)
    {
        try
        {
            object bg = GetProp(_ctx, "BaseGraph");
            if (bg != null)
            {
                var m = bg.GetType().GetMethod("ClickStopButton");
                if (m != null) { m.Invoke(bg, new object[] { true }); P("[" + kind + "] ClickStopButton(true) 已调"); }
            }
        }
        catch (Exception e) { P("[" + kind + "] ClickStopButton err " + Inner(e)); }
        Thread.Sleep(1500);
        DismissMsgBoxes(kind);   // 「测试还没有完成，是否立即停止？」→ 是(Y)
        Thread.Sleep(1500);
        DismissMsgBoxes(kind);   // 连锁框再扫一轮
    }
    static bool _first = true;   // 首实验前无残留，跳过 StopCurrent
    // 参数窗类型按实验精确映射（16:04/16:18 实测：frmOCP 确定后不销毁会残留，误抓导致错实验）
    static readonly Dictionary<string, string> _frmOf = new Dictionary<string, string> { { "ocp", "frmOCP" }, { "eis", "frmEISVSfrq" }, { "tafel", "frmPotDynamic" } };
    static bool WaitParamAndOk(string kind)
    {
        string lastSnap = "";
        for (int i = 0; i < 20; i++)
        {
            Thread.Sleep(1000);
            Form[] snap = SnapForms();
            DismissMsgBoxes(kind);
            // 诊断：非过滤窗清单（变化才打）
            {
                var names = new System.Collections.Generic.List<string>();
                foreach (Form f in SnapForms())
                {
                    if (f == _form || f.GetType().FullName == "CorrTest.CSStudio.frmMain") continue;
                    if (f.GetType().Name == "frmUser" || f.Text.Contains("用户设置")) continue;
                    if (f.Text == "提示" || f.Text == "提示信息" || f.GetType().FullName.Contains("MessageBox")) continue;
                    names.Add(f.GetType().Name + "'" + f.Text + "'");
                }
                string s = string.Join(" | ", names.ToArray());
                if (s != lastSnap) { P("[" + kind + "] 窗清单#" + i + ": " + (s == "" ? "(空)" : s)); lastSnap = s; }
            }
            foreach (Form f in SnapForms())
            {
                if (f == _form || f.GetType().FullName == "CorrTest.CSStudio.frmMain") continue;
                // 跳过用户设置框（启动残留）——真正的实验参数窗在后面
                if (f.GetType().Name == "frmUser" || f.Text.Contains("用户设置")) continue;
                if (f.Text == "提示" || f.Text == "提示信息" || f.GetType().FullName.Contains("MessageBox")) continue;
                // 跳过图表窗（上一实验的 frmShowGra，标题带 [通道）
                if (f.GetType().Name.Contains("ShowGra") || f.Text.Contains("[通道")) continue;
                // 精确匹配本实验的参数窗类型（残留窗直接跳过）
                string expect;
                if (_frmOf.TryGetValue(kind, out expect) && f.GetType().Name != expect) continue;
                P("[" + kind + "] 参数窗 " + f.GetType().FullName + " '" + f.Text + "'");
                DumpControls(f, 1);
                // 填文件名（绝对路径无扩展名，软件自加 .txt/.cor）
                // Obsidian 01：各参数窗文件名控件统一 id=Control_FileName_Text，禁止抓第一个 TextBox（EIS 窗第一个是 txtPrePotTime）
                try
                {
                    Control tb = FindById(f, "Control_FileName_Text");
                    if (tb == null) tb = FindById(f, "txtFileName");
                    if (tb == null) tb = FindByNameContains(f, "FileName");
                    if (tb is TextBox) { tb.Text = Path.Combine(OUTDIR, "ui6_" + kind); P("[" + kind + "] 文件名已填 → " + tb.Name); }
                    else P("[" + kind + "] 文件名控件未找到（跳过，用软件默认路径）");
                }
                catch (Exception e) { P("[" + kind + "] 填文件名 err " + Inner(e)); }
                // 首选 AcceptButton——放独立线程：确定处理器可能弹「文件重复→覆盖(N)」模态框，
                // Runner 必须保持自由去跑 DismissMsgBoxes 看护（01 文档坑 8）
                try
                {
                    IButtonControl ab = f.AcceptButton;
                    Form pf = f;
                    if (ab is Button)
                    {
                        var bt = (Button)ab;
                        Thread ct = new Thread(delegate()
                        {
                            try { pf.BeginInvoke((MethodInvoker)delegate { bt.PerformClick(); }); } catch { }
                        });
                        ct.IsBackground = true; ct.Start();
                        P("[" + kind + "] AcceptButton.PerformClick(异步线程)");
                        // 等参数窗自己关（确定成功）或被看护救活
                        for (int w = 0; w < 25 && !pf.IsDisposed; w++) { Thread.Sleep(400); DismissMsgBoxes(kind); }
                        P("[" + kind + "] 参数窗确定=已点，BaseGraph=" + (GetProp(_ctx, "BaseGraph") == null ? "null" : "已创建"));
                        return true;
                    }
                }
                catch (Exception e) { P("[" + kind + "] AcceptButton err " + Inner(e)); }
                // 兜底：递归找 text 含「确定」的 Button
                Control ok = FindOk(f);
                if (ok is Button) { ((Button)ok).PerformClick(); P("[" + kind + "] 兜底确定.PerformClick " + ok.Name); return true; }
                P("[" + kind + "] 参数窗无确定按钮");
                return false;
            }
        }
        return false;
    }
    static Form[] SnapForms()
    {
        FormCollection fc = Application.OpenForms;
        Form[] arr = new Form[fc.Count];
        ((System.Collections.ICollection)fc).CopyTo(arr, 0);
        return arr;
    }
    // 提示框（MessageBoxEx/AnimateMsg/「测试还没有完成，是否立即停止？」/「文件重复」）自动应答
    // 注意：必须 BeginInvoke 派回窗的 UI 线程执行 PerformClick，跨线程直调对模态框无效
    static void DismissMsgBoxes(string kind)
    {
        foreach (Form f in SnapForms())
        {
            string tn = f.GetType().FullName;
            bool msg = f.Text == "提示" || f.Text == "提示信息" || f.Text.Contains("测试") || f.Text.Contains("停止") || f.Text.Contains("重复") || tn.Contains("MessageBox");
            if (!msg) continue;
            Control b = FindButtonText(f, "覆盖") ?? FindButtonText(f, "是(Y)") ?? FindButtonText(f, "是") ?? FindButtonText(f, "确定");
            if (b is Button)
            {
                var bb = (Button)b; Form ff = f;
                try { ff.BeginInvoke((MethodInvoker)delegate { try { bb.PerformClick(); } catch { } }); P("[" + kind + "] 提示框[" + f.GetType().Name + "/" + f.Text + "]点:" + b.Text); }
                catch { }
            }
            else
            {
                var bl = new System.Collections.Generic.List<string>();
                DumpButtons(f, bl);
                P("[" + kind + "] 提示框[" + f.GetType().Name + "/" + f.Text + "] 无匹配按钮, 按钮清单: " + string.Join(",", bl.ToArray()));
            }
        }
    }
    static long WatchLen(string dir, string baseName)
    {
        try
        {
            string[] hits = Directory.GetFiles(dir, baseName + ".*");
            long max = -1;
            foreach (string h in hits) { long l = new FileInfo(h).Length; if (l > max) max = l; }
            return max;
        }
        catch { return -1; }
    }
    static Control FindButtonText(Control root, string text)
    {
        string want = text == null ? "" : text.Replace("&", "").Replace("(", "").Replace(")", "");
        foreach (Control c in root.Controls)
        {
            if (c is Button && c.Text != null)
            {
                string t = c.Text.Replace("&", "").Replace("(", "").Replace(")", "");
                if (t == want || (want.Length > 0 && t.Contains(want))) return c;
            }
            Control r = FindButtonText(c, text);
            if (r != null) return r;
        }
        return null;
    }
    static void DumpButtons(Control root, System.Collections.Generic.List<string> acc)
    {
        foreach (Control c in root.Controls)
        {
            if (c is Button) acc.Add(c.GetType().Name + "'" + c.Text + "'");
            DumpButtons(c, acc);
        }
    }
    static Control FindById(Control root, string id)
    {
        if (root.Name == id) return root;
        foreach (Control c in root.Controls) { Control r = FindById(c, id); if (r != null) return r; }
        return null;
    }
    static Control FindByNameContains(Control root, string frag)
    {
        if (root.Name != null && root.Name.IndexOf(frag, StringComparison.OrdinalIgnoreCase) >= 0 && root is TextBox) return root;
        foreach (Control c in root.Controls) { Control r = FindByNameContains(c, frag); if (r != null) return r; }
        return null;
    }
    static Control FindTextBox(Control root)
    {
        Control first = null;
        foreach (Control c in root.Controls)
        {
            TextBox tb = c as TextBox;
            if (tb != null)
            {
                if (c.Name.ToLowerInvariant().Contains("file")) return c;
                if (first == null) first = tb;
            }
            Control r = FindTextBox(c);
            if (r != null) return r;
        }
        return first;
    }
    static Control FindOk(Control root)
    {
        foreach (Control c in root.Controls)
        {
            if (c is Button && (c.Text.Contains("确定") || c.Text.ToLowerInvariant() == "ok")) return c;
            Control r = FindOk(c);
            if (r != null) return r;
        }
        return null;
    }
    static void DumpControls(Control root, int depth)
    {
        if (depth > 3) return;
        foreach (Control c in root.Controls)
        {
            P(new string(' ', depth * 2) + c.GetType().Name + " '" + c.Name + "' '" + c.Text + "'");
            DumpControls(c, depth + 1);
        }
    }

    static string[] _args;

    [STAThread]
    static int Main(string[] args)
    {
        _args = args;
        try { File.Delete(LogPath); } catch { }
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string n = new AssemblyName(e.Name).Name + ".dll";
            string p = Path.Combine(DIR, n);
            if (!File.Exists(p)) return null;
            return Assembly.LoadFrom(p);
        };
        try { Directory.CreateDirectory(OUTDIR); } catch { }
        P("=== CsPilotUi6 启动 ===");
        try
        {
            LoadAsms();

            // 软件原生启动：直接调壳的 EntryPoint（资源被壳混淆，必须由壳初始化）
            // Runner 后台线程轮询 Application.OpenForms 拿 frmMain.baseContext
            new Thread(Runner) { IsBackground = true }.Start();
            MethodInfo ep = _exe.EntryPoint;
            P("调软件 EntryPoint " + ep.DeclaringType.FullName + "." + ep.Name);
            ep.Invoke(null, new object[] { new string[0] });
            P("=== 软件消息循环退出 ===");
            return 0;
        }
        catch (Exception e)
        {
            P("FATAL Main " + Inner(e) + "\n" + e.StackTrace);
            return 1;
        }
    }
}
