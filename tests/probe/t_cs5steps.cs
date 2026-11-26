// t_cs5steps.cs -- 逐步调用 CS5 下发链，定位「指令下发失败」发生在哪一步
//
// StartMethod 内部顺序（IL 实证）：
//   set_Persent → SendMethodInit → GetOcpValueAutoRange/set_OcpValue ×3
//   → SendMethodParams → InitExp → ExpCallWatiFun → …
// 本探针逐步调用并打印每一步的返回值，定位失败点。
//
// 用法：t_cs5steps.exe --port 31150
using System;
using System.Linq;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;

static class Steps
{
    const string DIR5 = @"D:\sci\CS Studio5\CS Studio5";
    static readonly string[] DLLS = {
        "CorrTest.CorrInterface.dll", "CorrTest.CorrData.dll", "CorrTest.CorrCom.dll",
        "CorrTest.CorrModules.dll", "CorrTest.CorrMath.dll", "CorrTest.CorrLog.dll",
        "CorrTest.CorrLanguage.dll", "CorrTest.CorrUSControl.dll",
        "CorrTest.NetSkin.dll", "CorrTest.NetUtility.dll", "CorrTest.CorrCSType.dll"
    };
    static Dictionary<string, Assembly> _asms = new Dictionary<string, Assembly>();

    static Type[] Types(Assembly a)
    {
        try { return a.GetTypes(); }
        catch (ReflectionTypeLoadException e) { return e.Types; }
        catch { return new Type[0]; }
    }

    static Type Find(string name)
    {
        foreach (var a in _asms.Values)
            foreach (var t in Types(a))
                if (t != null && t.Name == name) return t;
        return null;
    }

    static void P(string s) { Console.WriteLine(s); Console.Out.Flush(); }

    /// 带超时调用；返回 "OK:值" / "EXC:类型: 消息" / "HANG>ms"
    static string Try(Func<object> f, int ms)
    {
        Exception err = null;
        object res = null;
        var th = new Thread(() => { try { res = f(); } catch (Exception e) { err = e; } });
        th.IsBackground = true;
        th.Start();
        if (!th.Join(ms)) return "HANG>" + ms + "ms";
        if (err != null)
        {
            var ie = err is TargetInvocationException && err.InnerException != null ? err.InnerException : err;
            var st = ie.StackTrace;
            return "EXC:" + ie.GetType().Name + ": " + ie.Message
                + (string.IsNullOrEmpty(st) ? "" : "\n      STACK: " + st.Replace("\n", "\n      "));
        }
        if (res == null) return "OK:null";
        var b = res as bool?;
        return "OK:" + (b.HasValue ? (b.Value ? "True" : "False") : Convert.ToString(res));
    }

    static int Main(string[] args)
    {
        int port = 31150;
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == "--port") int.TryParse(args[i + 1], out port);

        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (File.Exists(p)) { try { _asms[n] = Assembly.LoadFrom(p); } catch { } }
        }

        Type ctxT = Find("BaseContext"), ocpT = Find("OcpParams"),
             expT = Find("ExpClass"), sockT = Find("SockectCom"), expEnum = Find("Experiment");
        if (ctxT == null || ocpT == null || expT == null || sockT == null || expEnum == null)
        { P("FATAL: type missing"); return 3; }

        // ---- 连接 ----
        object com = Activator.CreateInstance(sockT);
        object r;
        var openM = sockT.GetMethod("Open", new[] { typeof(string) });
        r = openM.Invoke(com, new object[] { "127.0.0.1:" + port });
        P("[1] Open = " + r);
        if (!(bool)r) return 4;
        var stM = sockT.GetMethod("StartThread");
        if (stM != null) { stM.Invoke(com, null); P("    StartThread ok"); }
        Thread.Sleep(300);

        // ---- ctx ----
        object ctx = Activator.CreateInstance(ctxT);
        ctxT.GetField("_com", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(ctx, com);
        object pp;
        Try(() => Activator.CreateInstance(Find("ParsingParamsClass")), 5000);
        pp = Activator.CreateInstance(Find("ParsingParamsClass"));
        ctxT.GetProperty("ParsingParms").SetValue(ctx, pp, null);
        ctxT.GetProperty("ParsingParmsAux").SetValue(ctx, Activator.CreateInstance(Find("ParsingParamsClass")), null);
        // ★ FlushParams NRE 根因修复（2026-11-10 堆栈实锤）：
        //   ParsingParamsClass.FlushParams(IBaseIO, Boolean) 读 this.context（ctor 348B 不设置该字段）
        //   → null → NRE。静默时代 ACK 失败提前 return 根本没走到这，echo 后 ACK 成功才暴露。
        {
            var ppt = Find("ParsingParamsClass");
            var ctxFld = ppt.GetField("context", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (ctxFld != null)
            {
                ctxFld.SetValue(pp, ctx);
                object aux = ctxT.GetProperty("ParsingParmsAux").GetValue(ctx, null);
                if (aux != null) ctxFld.SetValue(aux, ctx);
                P("    pp.context injected -> ctx");
            }
            else P("    [diag] ParsingParamsClass.context field NOT found");
        }
        ctxT.GetProperty("ExpTimeHlp").SetValue(ctx, Activator.CreateInstance(Find("ExpTimeHlpClass")), null);
        ctxT.GetProperty("ExpParamsBytes").SetValue(ctx, Activator.CreateInstance(Find("ExpParamsBytesClass"), new object[] { pp }), null);
        object send = Activator.CreateInstance(Find("ExpComSendClass"), new object[] { ctx });
        ctxT.GetProperty("ExpComSend").SetValue(ctx, send, null);
        ctxT.GetProperty("CellsSwitch").SetValue(ctx, Activator.CreateInstance(Find("CellsSwitchClass"), new object[] { ctx }), null);
        ctxT.GetProperty("ExtComHlp").SetValue(ctx, Activator.CreateInstance(Find("ExtComHlpClass"), new object[] { ctx }), null);
        var edhF = ctxT.GetField("ExtDevHlp", BindingFlags.Instance | BindingFlags.Public);
        if (edhF != null) edhF.SetValue(ctx, Activator.CreateInstance(Find("ExtDevHlpClass"), new object[] { ctx }));

        // ★ AutoSwitchVoltRangeForOcp 读 baseContext.ExtAmpData.VotCoefficient，
        //   ExtAmpData 为 NULL 就是 GetOcpValueAutoRange 的 NRE 来源。
        var eadP = ctxT.GetProperty("ExtAmpData");
        P("    [diag] ExtAmpData prop=" + (eadP == null ? "NULL" : eadP.PropertyType.FullName + " write=" + eadP.CanWrite));
        Type eadT0 = Find("ExtAmpData");
        P("    [diag] Find(ExtAmpData)=" + (eadT0 == null ? "NULL" : eadT0.FullName));
        if (eadP != null && eadP.CanWrite)
        {
            object ead = null;
            Type eadT = Find("ExtAmpData");
            if (eadT != null)
            {
                try { ead = Activator.CreateInstance(eadT); } catch { }
                if (ead == null)
                {
                    foreach (var c in eadT.GetConstructors())
                    {
                        try
                        {
                            var ps = c.GetParameters();
                            var args2 = new object[ps.Length];
                            for (int k = 0; k < ps.Length; k++)
                                args2[k] = ps[k].ParameterType.IsValueType
                                           ? Activator.CreateInstance(ps[k].ParameterType) : null;
                            ead = Activator.CreateInstance(eadT, args2);
                            break;
                        }
                        catch { }
                    }
                }
            }
            if (ead != null)
            {
                try { eadP.SetValue(ctx, ead, null); P("    ExtAmpData injected: " + ead.GetType().Name); }
                catch (Exception e) { P("    ExtAmpData set failed: " + e.Message); }
                // ★ dump 结构：S3 GetOcpValueAutoRange NRE 嫌疑=裸构造后内部字段全 null
                P("    [ExtAmpData fields]");
                foreach (var f in ead.GetType().GetFields(BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public))
                    P("      F " + f.FieldType.Name + " " + f.Name + " = " + (f.GetValue(ead) == null ? "null" : Convert.ToString(f.GetValue(ead))));
                foreach (var pr in ead.GetType().GetProperties(BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public))
                {
                    object v = null; string vs;
                    try { v = pr.GetValue(ead, null); vs = v == null ? "null" : Convert.ToString(v); }
                    catch (Exception e) { vs = "EXC " + e.GetType().Name; }
                    P("      P " + pr.PropertyType.Name + " " + pr.Name + " = " + vs + (pr.CanWrite ? " [w]" : ""));
                }
                // 注入常见系数：VotCoefficient=1.0、CurrCoefficient=1.0
                foreach (var pn in new[] { "VotCoefficient", "CurrCoefficient" })
                {
                    var pp2 = ead.GetType().GetProperty(pn);
                    if (pp2 != null && pp2.CanWrite)
                    {
                        try { pp2.SetValue(ead, 1.0, null); P("    " + pn + " set 1.0"); } catch (Exception e) { P("    " + pn + " set fail: " + e.Message); }
                    }
                    else
                    {
                        var ff = ead.GetType().GetField(pn, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
                              ?? ead.GetType().GetField("<" + pn + ">i__BackingField", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
                              ?? ead.GetType().GetField("_" + pn, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
                              ?? ead.GetType().GetField(pn.ToLowerInvariant(), BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                        if (ff != null) { try { ff.SetValue(ead, 1.0); P("    " + ff.Name + " set 1.0"); } catch (Exception e) { P("    " + ff.Name + " set fail: " + e.Message); } }
                    }
                }
                var vc = ead.GetType().GetProperty("VotCoefficient");
                if (vc != null)
                {
                    try { P("    VotCoefficient = " + vc.GetValue(ead, null)); }
                    catch (Exception e) { P("    VotCoefficient read failed: " + e.Message); }
                }
            }
            else P("    ExtAmpData: 无法构造");
        }
        P("[2] ctx assembled");

        // ---- 参数 ----
        object prm = Activator.CreateInstance(ocpT);
        ocpT.GetProperty("baseContext").SetValue(prm, ctx, null);
        ocpT.GetProperty("TestTime").SetValue(prm, 20f, null);
        ocpT.GetProperty("TestTimeUnit").SetValue(prm, 1, null);
        string baseName = Path.Combine(Path.GetTempPath(), "cspilot_steps_" + port);
        ocpT.GetProperty("FilePath").SetValue(prm, baseName, null);
        ocpT.GetProperty("FileName").SetValue(prm, Path.GetFileName(baseName), null);
        ocpT.GetProperty("ExpType").SetValue(prm, Enum.Parse(expEnum, "ID_OCP"), null);
        ctxT.GetProperty("CurExp").SetValue(ctx, Enum.Parse(expEnum, "ID_OCP"), null);

        // BaseIO 两处都要补（InitExp 第一件事就取它）
        object bio = ocpT.GetProperty("BaseIO").GetValue(prm, null);
        var devP = ocpT.GetProperty("DevParam");
        object dev = devP == null ? null : devP.GetValue(prm, null);
        if (dev != null && bio != null)
        {
            var dbo = dev.GetType().GetProperty("BaseIO");
            if (dbo != null) dbo.SetValue(dev, bio, null);
        }
        P("[3] params ready; BaseIO=" + (bio == null ? "NULL" : "ok")
          + " DevParam=" + (dev == null ? "NULL" : "ok"));

        // ---- ExpClass ----
        object ec;
        string rs = Try(() => Activator.CreateInstance(expT, new object[] { ctx, prm }), 8000);
        P("[4] ExpClass = " + rs);
        if (!rs.StartsWith("OK")) return 5;
        ec = Activator.CreateInstance(expT, new object[] { ctx, prm });
        ctxT.GetProperty("ActiveExpClass").SetValue(ctx, ec, null);

        Try(() => { expT.GetMethod("BeginStartWriteFile", Type.EmptyTypes).Invoke(ec, null); return null; }, 6000);

        // ---- 逐步下发（照 StartMethod 的 IL 顺序）----
        P("");
        P("=== 逐步下发（对齐 StartMethod IL 顺序）===");
        P("[S1] set_Persent(0)      : " + Try(() => { ocpT.GetProperty("Persent").SetValue(prm, 0.0, null); return null; }, 3000));
        P("[S2] SendMethodInit()   : " + Try(() => ocpT.GetMethod("SendMethodInit", Type.EmptyTypes).Invoke(prm, null), 15000));
        Thread.Sleep(300);
        // ★ 2026-11-10 修：原 GetMethod(name, Type.EmptyTypes) 若无参重载不存在返回 null → null.Invoke
        //   在探针 lambda 里抛 NRE（S3 假阴性）。改为按名遍历并打印实际签名。
        {
            var ms = ocpT.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                         .Where(m => m.Name == "GetOcpValueAutoRange").ToArray();
            foreach (var m in ms)
                P("    [S3 sig] GetOcpValueAutoRange(" + string.Join(",", m.GetParameters().Select(p2 => p2.ParameterType.Name + " " + p2.Name)) + ")");
            var m0 = ms.FirstOrDefault(m => m.GetParameters().Length == 0)
                  ?? ms.OrderByDescending(m => m.GetParameters().Count(p2 => p2.HasDefaultValue || p2.IsOptional)).FirstOrDefault();
            if (m0 == null) { P("[S3] GetOcpValueAutoRange() : 方法不存在"); }
            else
            {
                var ps2 = m0.GetParameters();
                var args3 = new object[ps2.Length];
                for (int k = 0; k < ps2.Length; k++)
                    args3[k] = ps2[k].ParameterType.IsValueType && !ps2[k].ParameterType.IsByRef
                               ? Activator.CreateInstance(ps2[k].ParameterType.GetElementType() ?? ps2[k].ParameterType) : null;
                var r3 = Try(() => m0.Invoke(prm, args3), 15000);
                P("[S3] GetOcpValueAutoRange() : " + r3);
                foreach (var a4 in args3)
                {
                    var arr = a4 as Array;
                    if (arr != null && arr.Length > 0)
                        P("    [S3 out] " + arr.GetType().GetElementType().Name + "[] = " + string.Join(",", arr.Cast<object>().Take(8)));
                }
            }
        }
        // ★ 2026-11-10 S4.pre：上一阶段应答残渣（List<byte> 不整除 8B 消费）会卡死判定层 → ClearData
        try
        {
            var getComC = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCom" && m2.GetParameters().Length == 0);
            var comC = getComC == null ? null : getComC.Invoke(ctx, null);
            if (comC != null)
            {
                var cdC = comC.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                             .FirstOrDefault(m2 => m2.Name == "ClearData");
                if (cdC != null) { cdC.Invoke(comC, null); P("[S4.pre] ClearData 已清残留"); }
            }
        }
        catch (Exception e4p) { P("[S4.pre] EXC " + e4p.Message); }
        P("[S4] SendMethodParams() : " + Try(() => ocpT.GetMethod("SendMethodParams", Type.EmptyTypes).Invoke(prm, null), 15000));
        Thread.Sleep(300);

        // ★ 2026-11-10 S4b：SendReturnBool 判定黑盒——S4=False 但 ACK echo 已发，直接问壳内判定逻辑
        try
        {
            var getComS4 = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCom" && m2.GetParameters().Length == 0);
            var comS4 = getComS4 == null ? null : getComS4.Invoke(ctx, null);
            if (comS4 == null) { P("[S4b] com=NULL"); }
            else
            {
                var ctS4 = comS4.GetType();
                P("[S4b] com=" + ctS4.FullName);
                byte[] f74 = new byte[16]; f74[0] = 0xAA; f74[1] = 0x74; f74[15] = 0x1E;
                byte[] f52 = new byte[16]; f52[0] = 0xAA; f52[1] = 0x52; f52[2] = 0x07; f52[3] = 0xD2; f52[5] = 0x03; f52[15] = 0xD8;
                foreach (var m in ctS4.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                                       .Where(m2 => m2.Name == "SendReturnBool" || m2.Name == "SendReturnBoolThree"))
                    P("    [S4b sig] " + m.ToString());
                var srb3 = ctS4.GetMethods().FirstOrDefault(m2 => m2.Name == "SendReturnBoolThree" && m2.GetParameters().Length == 1);
                if (srb3 != null)
                    P("[S4c] SendReturnBoolThree(f74)=" + Try(() => srb3.Invoke(comS4, new object[] { f74 }), 8000));
                var srb3p = ctS4.GetMethods().FirstOrDefault(m2 => m2.Name == "SendReturnBoolThree" && m2.GetParameters().Length == 2);
                if (srb3p != null)
                    P("[S4c2] SendReturnBoolThree(f74,f52)=" + Try(() => srb3p.Invoke(comS4, new object[] { f74, f52 }), 8000));
                var srb2 = ctS4.GetMethods().FirstOrDefault(m2 => m2.Name == "SendReturnBool" && m2.GetParameters().Length == 2);
                if (srb2 != null)
                    P("[S4d] SendReturnBool(f74,2000)=" + Try(() => srb2.Invoke(comS4, new object[] { f74, 2000 }), 8000));
                var srb3x = ctS4.GetMethods().FirstOrDefault(m2 => m2.Name == "SendReturnBool" && m2.GetParameters().Length == 3);
                if (srb3x != null)
                    P("[S4e] SendReturnBool(f74,2000,0xAA)=" + Try(() => srb3x.Invoke(comS4, new object[] { f74, 2000, (byte)0xAA }), 8000));
            }
        }
        catch (Exception e4b) { P("[S4b] EXC " + e4b.Message); }

        // ★ 2026-11-10 S4f：判定规则隔离矩阵——sim 对 AA 85 静默，用 f85 做判定帧，缓冲只含手喂候选
        try
        {
            var getComF = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCom" && m2.GetParameters().Length == 0);
            var comF = getComF == null ? null : getComF.Invoke(ctx, null);
            if (comF == null) { P("[S4f] com=NULL"); }
            else
            {
                var ctF = comF.GetType();
                byte[] f85 = new byte[16]; f85[0] = 0xAA; f85[1] = 0x85; f85[2] = 0x63; f85[3] = 0x0A; f85[15] = 0x9C;
                byte[] f52 = new byte[16]; f52[0] = 0xAA; f52[1] = 0x52; f52[2] = 0x07; f52[3] = 0xD2; f52[5] = 0x03; f52[15] = 0xD8;
                var bfF = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                var cdM = ctF.GetMethods(bfF).FirstOrDefault(m2 => m2.Name == "ClearData");
                var adbM = ctF.GetMethods(bfF).FirstOrDefault(m2 => m2.Name == "AddToDataBuffer" && m2.GetParameters().Length == 2);
                var srb3F = ctF.GetMethods(bfF).FirstOrDefault(m2 => m2.Name == "SendReturnBool" && m2.GetParameters().Length == 3);
                P("[S4f] helpers cd=" + (cdM != null) + " adb=" + (adbM != null) + " srb3=" + (srb3F != null));
                // 候选应答（剥 AA 形式）
                byte[] cA = new byte[15]; cA[0] = 0x52; cA[1] = 0x07; cA[2] = 0xD2; cA[4] = 0x03; cA[14] = 0xD8;      // echo 剥 AA
                byte[] cB = new byte[15]; cB[0] = 0xD2; cB[1] = 0x07; cB[2] = 0xD2; cB[4] = 0x03;                      // cmd+0x80
                byte[] cC = new byte[16]; Array.Copy(f52, cC, 16);                                                     // 原样带 AA
                byte[] cD = new byte[7];  cD[0] = 0x53; cD[1] = 0x7E; cD[2] = 0x6B; cD[3] = 0x76; cD[4] = 0x7F; cD[5] = 0xFF; cD[6] = 0xDA; // 7B 数据帧
                byte[] cE = new byte[15];                                                                              // 全零
                byte[][] cands = new byte[][] { cA, cB, cC, cD, cE };
                string[] names = new string[] { "52echo15B", "D2cmd15B", "AA52raw16B", "7Bdata53", "zero15B" };
                byte?[] heads = new byte?[] { (byte)0xAA, (byte)0x52, (byte)0x74, (byte)0xD2, (byte)0x85 };
                for (int ci = 0; ci < cands.Length; ci++)
                {
                    foreach (var hd in heads)
                    {
                        try
                        {
                            if (cdM != null) cdM.Invoke(comF, null);
                            if (adbM != null) adbM.Invoke(comF, new object[] { cands[ci], cands[ci].Length });
                            string tag = "[S4f] buf=" + names[ci] + " head=" + (hd == null ? "-" : "0x" + ((byte)hd).ToString("X2")) + " -> ";
                            if (srb3F != null)
                                P(tag + Try(() => srb3F.Invoke(comF, new object[] { f85, 800, (byte)hd }), 4000));
                        }
                        catch (Exception e1) { P("[S4f] cand" + ci + " EXC " + e1.Message); }
                    }
                }
                if (cdM != null) cdM.Invoke(comF, null);

                // ★ S4h：真 echo 后 dump 四容器，找判定数据源
                try
                {
                    var bfH = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                    string[] fldsH = new string[] { "m_DataBuffer", "m_DataList", "m_objDataBuffer", "m_objDataList" };
                    Action<string> dumpH = delegate(string when)
                    {
                        foreach (var fn in fldsH)
                        {
                            var fi2 = ctF.GetField(fn, bfH);
                            if (fi2 == null) { P("[S4h " + when + "] " + fn + "=<无字段>"); continue; }
                            var v2 = fi2.GetValue(comF);
                            if (v2 == null) { P("[S4h " + when + "] " + fn + "=null"); continue; }
                            var lst = v2 as System.Collections.IEnumerable;
                            int n = 0; string head = "";
                            if (lst != null)
                            {
                                foreach (var it in lst)
                                {
                                    n++;
                                    var arr = it as byte[];
                                    if (arr != null && head.Length < 60)
                                        head += "{" + arr.Length + "B:" + string.Join("", arr.Take(6).Select(b2 => b2.ToString("X2"))) + "} ";
                                    else if (head.Length < 60) head += "{" + it + "} ";
                                    if (n > 6) break;
                                }
                            }
                            P("[S4h " + when + "] " + fn + " (" + v2.GetType().Name + ") n=" + n + " " + head);
                        }
                    };
                    if (srb3F != null)
                    {
                        var rH = Try(() => srb3F.Invoke(comF, new object[] { f85, 800, (byte)0xAA }), 4000);
                        P("[S4h] srb3(f85,800,AA) 空缓冲对照=" + rH);
                        byte[] f74H = new byte[16]; f74H[0] = 0xAA; f74H[1] = 0x74; f74H[15] = 0x1E;
                        var rH2 = Try(() => srb3F.Invoke(comF, new object[] { f74H, 1500, (byte)0xAA }), 4000);
                        P("[S4h] srb3(f74,1500,AA)=" + rH2);
                        dumpH("echo后");
                        var rH3 = Try(() => srb3F.Invoke(comF, new object[] { f74H, 1500, (byte)0xAA }), 4000);
                        P("[S4h] srb3(f74,1500,AA) 二次=" + rH3);
                        dumpH("二次后");
                        // ★ S4i：f52 真 echo 对照——S4 现场 AA 52 为何 9 发全拒
                        byte[] f52H = new byte[16]; f52H[0] = 0xAA; f52H[1] = 0x52; f52H[2] = 0x07; f52H[3] = 0xD2; f52H[5] = 0x03; f52H[15] = 0xD8;
                        var rI = Try(() => srb3F.Invoke(comF, new object[] { f52H, 1500, (byte)0xAA }), 4000);
                        P("[S4i] srb3(f52,1500,AA)=" + rI);
                        dumpH("f52echo后");
                        var rI2 = Try(() => srb3F.Invoke(comF, new object[] { f52H, 1500, (byte)0x52 }), 4000);
                        P("[S4i] srb3(f52,1500,0x52)=" + rI2);
                        dumpH("f52二次后");
                    }
                }
                catch (Exception e4h) { P("[S4h] EXC " + e4h.Message); }
            }
        }
        catch (Exception e4f) { P("[S4f] EXC " + e4f.Message); }

        P("[S5] InitExp()          : " + Try(() => send.GetType().GetMethod("InitExp").Invoke(send, new object[] { prm }), 15000));
        Thread.Sleep(300);

        // ---- StartMethod 完整调用 ----
        // ★ 2026-11-10：ExpTime=0 → 实验秒完（ExpIsFinished=True）→ AddData 首行拒收。
        //   先设 ExpTime=60s + DevParam.WaitSecond=60（WatiFun 轮询轮数），给采集线程 60s 窗口。
        {
            prm.GetType().GetProperty("ExpTime").SetValue(prm, 60f, null);
            var dvPre = prm.GetType().GetProperty("DevParam").GetValue(prm, null);
            dvPre.GetType().GetProperty("WaitSecond").SetValue(dvPre, 60, null);
            P("[S6.pre] ExpTime=60f WaitSecond=60 已设");
            // ★ 2026-11-10 S6.pre2：S4/S5 阶段应答残渣同样会卡死 StartMethod 内部的 SendMethodParams
            try
            {
                var getComS6 = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCom" && m2.GetParameters().Length == 0);
                var comS6 = getComS6 == null ? null : getComS6.Invoke(ctx, null);
                if (comS6 != null)
                {
                    var cdS6 = comS6.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                                 .FirstOrDefault(m2 => m2.Name == "ClearData");
                    if (cdS6 != null) { cdS6.Invoke(comS6, null); P("[S6.pre2] ClearData 已清残留"); }
                }
            }
            catch (Exception e6p) { P("[S6.pre2] EXC " + e6p.Message); }
        }
        P("");
        object[] sa = new object[] { prm, true, true, "" };   // ★ isCallWatiFun=true：开软件自带采集/等待线程
        P("[S6] StartMethod(full)  : " + Try(() => send.GetType().GetMethod("StartMethod").Invoke(send, sa), 25000)
          + "  ret=" + sa[0] + "  err='" + sa[3] + "'");

        // ★ 2026-11-10 S6c：手动复刻 StartMethod IL 序列，逐步 dump m_DataBuffer，定位残渣来源
        try
        {
            var getComC6 = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCom" && m2.GetParameters().Length == 0);
            var comC6 = getComC6 == null ? null : getComC6.Invoke(ctx, null);
            if (comC6 == null) { P("[S6c] com=NULL"); }
            else
            {
                var ctC6 = comC6.GetType();
                var bfC6 = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                var cdC6 = ctC6.GetMethods(bfC6).FirstOrDefault(m2 => m2.Name == "ClearData");
                var fiBuf = ctC6.GetField("m_DataBuffer", bfC6);
                Action<string> dumpC6 = delegate(string when)
                {
                    if (fiBuf == null) { P("[S6c " + when + "] <无 m_DataBuffer>"); return; }
                    var v2 = fiBuf.GetValue(comC6) as System.Collections.IEnumerable;
                    int n = 0; string hx = "";
                    if (v2 != null) foreach (var it in v2) { n++; if (hx.Length < 50) hx += ((byte)it).ToString("X2") + " "; if (n > 24) break; }
                    P("[S6c " + when + "] buf n=" + n + " " + hx);
                };
                var sendInitM = ocpT.GetMethod("SendMethodInit", Type.EmptyTypes);
                var ocpM = ocpT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetOcpValueAutoRange");
                var sendParmM = ocpT.GetMethod("SendMethodParams", Type.EmptyTypes);
                if (cdC6 != null) cdC6.Invoke(comC6, null);
                dumpC6("清后");
                P("[S6c] SendMethodInit=" + Try(() => sendInitM.Invoke(prm, null), 15000));
                dumpC6("init后");
                if (ocpM != null)
                {
                    var psO = ocpM.GetParameters();
                    var aO = new object[psO.Length];
                    for (int k = 0; k < psO.Length; k++)
                        aO[k] = psO[k].ParameterType.IsByRef ? Activator.CreateInstance(psO[k].ParameterType.GetElementType()) : null;
                    P("[S6c] OcpAutoRange#1=" + Try(() => ocpM.Invoke(prm, aO), 15000));
                    dumpC6("ocr1后");
                    P("[S6c] OcpAutoRange#2=" + Try(() => ocpM.Invoke(prm, aO), 15000));
                    dumpC6("ocr2后");
                    P("[S6c] OcpAutoRange#3=" + Try(() => ocpM.Invoke(prm, aO), 15000));
                    dumpC6("ocr3后");
                }
                P("[S6c] SendMethodParams=" + Try(() => sendParmM.Invoke(prm, null), 15000));
                dumpC6("smp后");
                if (cdC6 != null) cdC6.Invoke(comC6, null);
            }
        }
        catch (Exception e6c) { P("[S6c] EXC " + e6c.Message); }
        // ★ dump StartMethod IL：找「指令下发失败」判定路径
        try
        {
            var smM = send.GetType().GetMethod("StartMethod");
            var sbody = smM == null ? null : smM.GetMethodBody();
            var sil = sbody == null ? null : sbody.GetILAsByteArray();
            P("    [S6.IL] StartMethod sig=" + (smM == null ? "?" : smM.ToString())
              + " IL=" + (sil == null ? "null" : sil.Length + "B"));
        }
        catch (Exception sex) { P("    [S6.IL] EXC " + sex.Message); }

        // ---- 数据 ----
        // ★ ExpIsFinished 状态 + 找测量时间字段（S6 ret=测量时间(s):0 → 实验可能秒完 → AddData 首行拒收）
        try
        {
            var gifM = expT.GetMethod("get_ExpIsFinished");
            P("    [S7.pre] ExpIsFinished=" + (gifM == null ? "?" : gifM.Invoke(ec, null)));
            // ★ 2026-11-10：S6 True 后 ExpIsFinished 仍 True → AddData 首行拒收。强制翻开再入库。
            var sifM = expT.GetMethod("set_ExpIsFinished");
            if (sifM != null) { sifM.Invoke(ec, new object[] { false }); P("    [S7.pre2] ExpIsFinished 强制=false"); }
        }
        catch (Exception gex) { P("    [S7.pre] ExpIsFinished EXC " + gex.Message); }
        foreach (var p2 in prm.GetType().GetProperties(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
        {
            var nl = p2.Name.ToLower();
            if ((nl.Contains("time") || nl.Contains("sec") || nl.Contains("dur")) && p2.CanRead)
            {
                try
                {
                    var v = p2.GetValue(prm, null);
                    if (v is int || v is double || v is float) P("    [S7.time] " + p2.Name + " = " + v + " (" + p2.PropertyType.Name + ")");
                }
                catch { }
            }
        }
        for (int wi = 0; wi < 4; wi++)
        {
            Thread.Sleep(1500);
            // ★ 推流死活验证：LastRecvData = 通信层最后收到的原始帧
            try
            {
                var lrd = sockT.GetProperty("LastRecvData").GetValue(com, null) as byte[];
                P("[S7." + wi + "] LastRecv=" + (lrd == null ? "null" : BitConverter.ToString(lrd).Replace("-", " ")));
            }
            catch (Exception e9) { P("[S7." + wi + "] LastRecv EXC " + e9.Message); }
            // ★ 手动驱动 ExpCallWatiFun（StartMethod isCallWatiFun=true 并未自动跑：S6 后无 AA 53 01 轮询）
            // ★ 分步复刻 WatiFun（反汇编 t_cs5wati.txt +3..+241），抓 NRE 精确位置
            try
            {
                var bcP = ocpT.GetProperty("baseContext");
                object bc = bcP.GetValue(prm, null);
                var ppW = ctxT.GetProperty("ParsingParms").GetValue(ctx, null);
                P("    [W.diag] baseContext=" + (bc == null ? "NULL" : "ok") + " ParsingParms=" + (ppW == null ? "NULL" : "ok"));
                var devW = ocpT.GetProperty("DevParam").GetValue(prm, null);
                var wsP = devW == null ? null : devW.GetType().GetProperty("WaitSecond");
                P("    [W.diag] DevParam=" + (devW == null ? "NULL" : "ok") + " WaitSecond=" + (wsP == null ? "?" : Convert.ToString(wsP.GetValue(devW, null))));
                var getCom = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCom" && m2.GetParameters().Length == 0);
                object comW = getCom == null ? null : getCom.Invoke(ctx, null);
                P("    [W.diag] GetCom()=" + (comW == null ? "NULL" : "ok"));
                var roF = null as FieldInfo;
                foreach (var a2 in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type cpT = a2.GetType("CorrTest.CorrCom.CommandPackage");
                    if (cpT == null) continue;
                    var f2 = cpT.GetField("ReadOcpBytes", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                    if (f2 != null) { roF = f2; break; }
                }
                P("    [W.diag] ReadOcpBytes=" + (roF == null ? "未找到" : "ok"));
                if (comW != null && roF != null)
                {
                    var srpM = comW.GetType().GetMethods()
                        .FirstOrDefault(m2 => m2.Name == "SendReturnPackage" && m2.GetParameters().Length == 5);
                    P("    [W.diag] SendReturnPackage(5p)=" + (srpM == null ? "NULL" : "ok"));
                    if (srpM != null)
                    {
                        var rov = roF.GetValue(null);
                        var sargs = new object[] { rov, 1500, (byte)7, (byte)170, (byte)3 };
                        var dataR = srpM.Invoke(comW, sargs) as byte[];
                        P("    [W.diag] SendReturnPackage → " + (dataR == null ? "null" : dataR.Length + "B " + BitConverter.ToString(dataR).Replace("-", " ")));
                        // ★ WatiFun return 路径的 Internation.GetString（语言表未初始化 = NRE 头号嫌疑）——无条件测
                        {
                            Type itlT = null;
                            foreach (var a2 in AppDomain.CurrentDomain.GetAssemblies())
                            {
                                try { itlT = a2.GetType("CorrTest.CorrLanguage.Internation"); } catch { }
                                if (itlT != null) break;
                            }
                            if (itlT != null)
                            {
                                var gsM = itlT.GetMethods(BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public).FirstOrDefault(m2 => m2.Name == "GetString" && m2.GetParameters().Length == 1);
                                P("    [W.diag] Internation=" + itlT.FullName + " GetString="
                                  + (gsM == null ? "?" : Try(() => gsM.Invoke(null, new object[] { "0x7000648E" }), 2000)));
                            }
                            else P("    [W.diag] Internation 类型未找到");
                        }
                        // ★ IL +332 精确复刻：prm.get_BaseIO().GetVoltRange()（BaseIO null = NRE 头号嫌疑）
                        {
                            var bio2F = prm.GetType().GetProperty("BaseIO");
                            var bio2 = bio2F == null ? null : bio2F.GetValue(prm, null);
                            P("    [W.diag] prm.BaseIO=" + (bio2 == null ? "NULL!!!" : bio2.GetType().Name));
                            if (bio2 != null)
                            {
                                var gvrm = bio2.GetType().GetMethod("GetVoltRange", Type.EmptyTypes);
                                P("    [W.diag] prm.BaseIO.GetVoltRange()=" + (gvrm == null ? "?" : Try(() => gvrm.Invoke(bio2, null), 2000)));
                                var gcrm = bio2.GetType().GetMethod("GetCurrRange", Type.EmptyTypes);
                                P("    [W.diag] prm.BaseIO.GetCurrRange()=" + (gcrm == null ? "?" : Try(() => gcrm.Invoke(bio2, null), 2000)));
                                var gpoc = bio2.GetType().GetMethod("GetPotOrCur", Type.EmptyTypes);
                                P("    [W.diag] prm.BaseIO.GetPotOrCur()=" + (gpoc == null ? "?" : Try(() => gpoc.Invoke(bio2, null), 2000)));
                            }
                        }
                        // ★ IL +474..+558 curr 量程段复刻：DevParam.IsCurrAutoRange/OnlyInc/AutoMinCurrRange + ctx.GetCurrRange/AutoRange
                        {
                            var dvW = prm.GetType().GetProperty("DevParam").GetValue(prm, null);
                            var dvT = dvW == null ? null : dvW.GetType();
                            if (dvW != null)
                            {
                                var icaM = dvT.GetMethod("get_IsCurrAutoRange", Type.EmptyTypes) ?? dvT.GetMethod("IsCurrAutoRange", Type.EmptyTypes);
                                P("    [W.diag] DevParam.IsCurrAutoRange=" + (icaM == null ? "?" : Try(() => icaM.Invoke(dvW, null), 2000)));
                                var oiM = dvT.GetMethod("get_OnlyInc", Type.EmptyTypes) ?? dvT.GetMethod("OnlyInc", Type.EmptyTypes);
                                P("    [W.diag] DevParam.OnlyInc=" + (oiM == null ? "?" : Try(() => oiM.Invoke(dvW, null), 2000)));
                            }
                            var cgM = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetCurrRange" && m2.GetParameters().Length == 1);
                            P("    [W.diag] ctx.GetCurrRange(3)=" + (cgM == null ? "?" : Try(() => cgM.Invoke(ctx, new object[] { 3 }), 2000)));
                            var arM = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "AutoRange" && m2.GetParameters().Length == 1);
                            P("    [W.diag] ctx.AutoRange(0.0)=" + (arM == null ? "?" : Try(() => arM.Invoke(ctx, new object[] { 0.0 }), 2000)));
                            var amcM = dvT.GetMethod("get_AutoMinCurrRange", Type.EmptyTypes) ?? dvT.GetMethod("AutoMinCurrRange", Type.EmptyTypes);
                            var amcV = amcM == null ? null : Try(() => amcM.Invoke(dvW, null), 2000);
                            P("    [W.diag] DevParam.AutoMinCurrRange=" + amcV);
                            var ariM = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "AutoRangeInc" && m2.GetParameters().Length == 2);
                            P("    [W.diag] AutoRangeInc sig=" + (ariM == null ? "?" : ariM.ToString()));
                            int amcI = 0;
                            if (amcV != null && amcV.StartsWith("OK:")) int.TryParse(amcV.Substring(3), out amcI);
                            P("    [W.diag] ctx.AutoRangeInc(0.0," + amcI + ")=" + (ariM == null ? "?"
                              : Try(() => ariM.Invoke(ctx, new object[] { 0.0, amcI }), 2000)));
                            // ★★ 接口版全链复刻：WatiFun 全部 callvirt 走接口，接口显式实现可能与公共 getter 不同
                            {
                                var idvI = dvT.GetInterface("IDeviceParams");
                                if (idvI != null)
                                    foreach (var gname in new[] { "get_WaitSecond", "get_IsVoltAutoRange", "get_IsCurrAutoRange", "get_OnlyInc", "get_AutoMinCurrRange" })
                                    {
                                        var im = idvI.GetMethod(gname, Type.EmptyTypes);
                                        if (im != null) P("    [W.diag] IDev." + gname + "=" + Try(() => im.Invoke(dvW, null), 2000));
                                    }
                                var ibpI = prm.GetType().GetInterface("IBaseParams");
                                if (ibpI != null)
                                    foreach (var gname in new[] { "get_ExpType", "get_baseContext", "get_DevParam", "get_BaseIO" })
                                    {
                                        var im = ibpI.GetMethod(gname, Type.EmptyTypes);
                                        if (im != null) P("    [W.diag] IBP." + gname + "=" + Try(() => im.Invoke(prm, null), 2000));
                                    }
                                // ★ IParsingParams 接口版 decode（7B 应答在场时才有效）
                                if (dataR != null && dataR.Length == 7 && ppW != null)
                                {
                                    var ippI = ppW.GetType().GetInterface("IParsingParams");
                                    if (ippI != null)
                                    {
                                        var igv = ippI.GetMethod("GetVoltValue");
                                        var igc = ippI.GetMethod("GetCurrValue");
                                        P("    [W.diag] IPP.GetVoltValue=" + (igv == null ? "?" : Try(() => igv.Invoke(ppW, new object[] { dataR, 1, 3 }), 2000))
                                          + " IPP.GetCurrValue=" + (igc == null ? "?" : Try(() => igc.Invoke(ppW, new object[] { dataR, 4, 3 }), 2000)));
                                    }
                                    else P("    [W.diag] pp 无 IParsingParams 接口");
                                }
                                // ★ ICorrCom 接口版 SendReturnPackage
                                if (comW != null)
                                {
                                    var iciI = comW.GetType().GetInterface("ICorrCom");
                                    if (iciI != null)
                                    {
                                        var isrp = iciI.GetMethod("SendReturnPackage");
                                        P("    [W.diag] ICorrCom.SendReturnPackage sig=" + (isrp == null ? "?" : isrp.ToString()));
                                        if (isrp != null && dataR != null)
                                            P("    [W.diag] ICorrCom.SendReturnPackage=" + Try(() => isrp.Invoke(comW, new object[] { rov, 1500, (byte)7, (byte)170, (byte)3 }), 3000));
                                    }
                                    else P("    [W.diag] com 无 ICorrCom 接口");
                                }
                            }
                        }
                        if (dataR != null && dataR.Length == 7)
                        {
                            var gvM = ppW.GetType().GetMethods().FirstOrDefault(m2 => m2.Name == "GetVoltValue" && m2.GetParameters().Length == 3);
                            var gcM = ppW.GetType().GetMethods().FirstOrDefault(m2 => m2.Name == "GetCurrValue" && m2.GetParameters().Length == 3);
                            var vArgs = new object[] { dataR, 1, 3 };
                            var cArgs = new object[] { dataR, 4, 3 };
                            P("    [W.diag] GetVoltValue=" + Try(() => gvM.Invoke(ppW, vArgs), 3000)
                              + " GetCurrValue=" + Try(() => gcM.Invoke(ppW, cArgs), 3000));
                            // 量程判断段（IL +332..+447）：BaseIO.GetVoltRange → ctx.GetVoltRange → Math.Abs 比较 → GetPotOrCur
                            var bioW = ocpT.GetProperty("BaseIO").GetValue(prm, null);
                            var bT = bioW == null ? null : bioW.GetType();
                            var gvrM = bT == null ? null : bT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetVoltRange" && m2.GetParameters().Length == 0);
                            var gpcM = bT == null ? null : bT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetPotOrCur" && m2.GetParameters().Length == 0);
                            P("    [W.diag] BaseIO=" + (bioW == null ? "NULL" : bT.Name)
                              + " GetVoltRange()=" + (gvrM == null ? "?" : Try(() => gvrM.Invoke(bioW, null), 2000))
                              + " GetPotOrCur()=" + (gpcM == null ? "?" : Try(() => gpcM.Invoke(bioW, null), 2000)));
                            var ctxGvr = ctxT.GetMethods().FirstOrDefault(m2 => m2.Name == "GetVoltRange" && m2.GetParameters().Length == 1);
                            if (ctxGvr != null && gvrM != null)
                            {
                                var vr = gvrM.Invoke(bioW, null);
                                P("    [W.diag] ctx.GetVoltRange(" + vr + ")=" + Try(() => ctxGvr.Invoke(ctx, new[] { vr }), 2000));
                            }
                        }
                    }
                }
            }
            catch (Exception we) { P("    [W.diag] EXC " + we.GetType().Name + ": " + we.Message + " @ " + (we.StackTrace ?? "").Split('\n').FirstOrDefault()); }
            foreach (var owner in new[] { ec, prm, send })
            {
                var wf = owner.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                             .FirstOrDefault(m2 => m2.Name == "ExpCallWatiFun");
                if (wf == null) continue;
                var wps = wf.GetParameters();
                // ★ 运行时方法体 vs 静态 dump 对比（壳可能运行时替换方法体）
                try
                {
                    var wbody = wf.GetMethodBody();
                    var wil = wbody == null ? null : wbody.GetILAsByteArray();
                    P("    [W.diag] runtime WatiFun IL=" + (wil == null ? "null" : wil.Length + "B head=" + BitConverter.ToString(wil, 0, Math.Min(20, wil.Length))));
                }
                catch (Exception iex) { P("    [W.diag] runtime IL EXC " + iex.GetType().Name + ": " + iex.Message); }
                var wargs = new object[wps.Length];
                for (int k = 0; k < wps.Length; k++)
                    // ★ 2026-11-10 破案：原代码对引用类型参数填 null → WatiFun(null) → ldarg.1 后 callvirt 即 NRE。
                    //   ExpCallWatiFun 唯一参数是 IBaseParams prm，直接传真 prm。
                    wargs[k] = (k == 0 && wps[0].ParameterType.IsInstanceOfType(prm)) ? prm
                               : wps[k].ParameterType.IsValueType && !wps[k].ParameterType.IsByRef
                                 ? Activator.CreateInstance(wps[k].ParameterType) : null;
                string wRes;
                try { wRes = "" + wf.Invoke(owner, wargs); }
                catch (Exception wex)
                {
                    var ie = wex.InnerException ?? wex;
                    wRes = "EXC:" + ie.GetType().Name + ": " + ie.Message + "\n" + (ie.StackTrace ?? "no-stack");
                }
                P("[S7." + wi + "] ExpCallWatiFun@" + owner.GetType().Name + "(" + string.Join(",", wps.Select(p2 => p2.ParameterType.Name)) + ") : " + wRes);
                // ★ ExpType 二分实验：51 不在支持列表 → WatiFun 首行 return（不进循环体）
                try
                {
                    var etP = prm.GetType().GetProperty("ExpType");
                    var etT = etP.PropertyType;
                    var oldV = etP.GetValue(prm, null);
                    var newV = etT.IsEnum ? Enum.ToObject(etT, 51) : Convert.ChangeType(51, etT);
                    etP.SetValue(prm, newV, null);
                    P("    [W.diag] ExpType " + oldV + " → 51: WatiFun=" + Try(() => wf.Invoke(owner, wargs), 8000));
                    etP.SetValue(prm, oldV, null);
                }
                catch (Exception eex) { P("    [W.diag] ExpType 实验 EXC " + eex.GetType().Name + ": " + eex.Message); }
                break;
            }
            try
            {
                var tL = expT.GetProperty("TimeList").GetValue(ec, null) as System.Collections.IList;
                var vL = expT.GetProperty("VoltList").GetValue(ec, null) as System.Collections.IList;
                P("[S7." + wi + "] Time=" + (tL == null ? -1 : tL.Count) + " Volt=" + (vL == null ? -1 : vL.Count)
                  + (tL != null && tL.Count > 0 ? "  t[0]=" + tL[0] + (vL != null && vL.Count > 0 ? " V[0]=" + vL[0] : "") : ""));
                // ★ 手动 AddData 验证入库链（AddData(Double volt, Double curr, Double dt)，前置=ExpIsFinished=False）
                try
                {
                    var adM = expT.GetMethod("AddData");
                    adM.Invoke(ec, new object[] { 0.0309, 1.13e-8, 0.1 });
                    var tl2 = expT.GetProperty("TimeList").GetValue(ec, null) as System.Collections.IList;
                    var vl2 = expT.GetProperty("VoltList").GetValue(ec, null) as System.Collections.IList;
                    P("    [S7.addData] 入库后 Time=" + (tl2 == null ? -1 : tl2.Count) + " Volt=" + (vl2 == null ? -1 : vl2.Count));
                }
                catch (Exception aex)
                {
                    var ie = aex.InnerException ?? aex;
                    P("    [S7.addData] EXC " + ie.GetType().Name + ": " + ie.Message);
                }
                if (tL != null && tL.Count > 0 && wi >= 2) break;
            }
            catch (Exception e7) { P("[S7." + wi + "] EXC " + e7.Message); }
        }
        // 落盘检查（2026-11-10 修：直接扫 Temp 下 cspilot_steps_port* 前缀，不依赖 FilePath getter 的怪值）
        try
        {
            // ★ 先手动触发写盘：WriteDataNow()（AddData 只入库不写文件）
            var wdnM = expT.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                          .FirstOrDefault(m2 => m2.Name == "WriteDataNow" && m2.GetParameters().Length == 0);
            if (wdnM != null)
            {
                try { wdnM.Invoke(ec, null); P("    [S7.write] WriteDataNow OK"); }
                catch (Exception we) { P("    [S7.write] WriteDataNow EXC " + we.Message); }
            }
            var tmpDir = Path.GetTempPath();
            foreach (var f in Directory.GetFiles(tmpDir, "cspilot_steps_" + port + "*"))
                P("    [S7 file] " + f + " (" + new FileInfo(f).Length + "B)");
        }
        catch (Exception e8) { P("    [S7 file] EXC " + e8.Message); }
        try { send.GetType().GetMethod("SendSysStop").Invoke(send, null); } catch { }
        try { expT.GetMethod("EndWriteFile", Type.EmptyTypes).Invoke(ec, null); } catch { }
        try { sockT.GetMethod("Close").Invoke(com, null); } catch { }
        Environment.Exit(0);
        return 0;
    }
}
