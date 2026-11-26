// t_cs5r.cs —— CS5 真机「欧姆表」探针：恒流阶跃测电阻（2026-11-18）
//
// 接线（用户已接）：电阻接 WE↔CE，RE 夹 CE 端，GND 悬空。
// 原理：GalStatic 恒流阶跃 → 软件本体协议栈发帧 → 真机设备输出电流 →
//       ExpClass.VoltList 收 E(t) → R = ΔE/ΔI。
// 双极性设计：--curr 正跑一轮、负跑一轮（同进程内两次实验），
//       R = (E+ − E−)/(I+ − I−) 消热电动势/偏移，并证明数据真实
//       （demo 陪跑指纹不会随电流变号翻转）。
//
// 这是 CS5 纯代码线首次真机运行（S1-S7 配方从模拟器 TCP 改串口 CorCom）。
// 红线：只碰 --com 指定口；电流默认 ±0.1mA（电阻上 0.1mA×10kΩ=1V，安全）；
//       |E| 超 9V 判合规电压触顶（开路/超量程），自动放弃并报告。
//
// 用法：t_cs5r.exe --com COM10 [--curr 0.1] [--time 12] [--single]
using System;
using System.Linq;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Threading;

static class RMeter
{
    const string DIR5 = @"D:\sci\CS Studio5\CS Studio5";
    static readonly string[] DLLS = {
        "CorrTest.CorrInterface.dll", "CorrTest.CorrData.dll", "CorrTest.CorrCom.dll",
        "CorrTest.CorrModules.dll", "CorrTest.CorrMath.dll", "CorrTest.CorrLog.dll",
        "CorrTest.CorrLanguage.dll", "CorrTest.CorrUSControl.dll",
        "CorrTest.NetSkin.dll", "CorrTest.NetUtility.dll", "CorrTest.CorrCSType.dll"
    };
    static Dictionary<string, Assembly> _asms = new Dictionary<string, Assembly>();
    static string LOGF;

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
    static void P(string s)
    {
        Console.WriteLine(s); Console.Out.Flush();
        try { File.AppendAllText(LOGF, s + "\r\n"); } catch { }
    }
    static string Try(Func<object> f, int ms)
    {
        Exception err = null; object res = null;
        var th = new Thread(() => { try { res = f(); } catch (Exception e) { err = e; } });
        th.IsBackground = true; th.Start();
        if (!th.Join(ms)) return "HANG>" + ms + "ms";
        if (err != null)
        {
            var ie = err is TargetInvocationException && err.InnerException != null ? err.InnerException : err;
            return "EXC:" + ie.GetType().Name + ": " + ie.Message;
        }
        if (res == null) return "OK:null";
        var b = res as bool?;
        return "OK:" + (b.HasValue ? (b.Value ? "True" : "False") : Convert.ToString(res));
    }

    // ---- 类型缓存 ----
    static Type ctxT, galT, expT, comT, expEnum;
    static object ctx, send, _com;

    static int Main(string[] args)
    {
        string comPort = "COM10";
        double curr_mA = 0.1;
        double testTime = 12.0;
        bool single = false;
        for (int i = 0; i < args.Length - 1; i++)
        {
            if (args[i] == "--com") comPort = args[i + 1];
            if (args[i] == "--curr") double.TryParse(args[i + 1], out curr_mA);
            if (args[i] == "--time") double.TryParse(args[i + 1], out testTime);
        }
        for (int i = 0; i < args.Length; i++) if (args[i] == "--single") single = true;
        if (Math.Abs(curr_mA) > 2.0) { P("FATAL: 电流上限 ±2mA（安全门）"); Environment.Exit(2); }

        LOGF = @"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5r_" + comPort + ".log";
        try { File.Delete(LOGF); } catch { }

        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (File.Exists(p)) { try { _asms[n] = Assembly.LoadFrom(p); } catch { } }
        }
        ctxT = Find("BaseContext"); galT = Find("GalStaticParams");
        expT = Find("ExpClass"); comT = Find("CorCom"); expEnum = Find("Experiment");
        if (ctxT == null || galT == null || expT == null || comT == null || expEnum == null)
        { P("FATAL: type missing ctx=" + (ctxT != null) + " gal=" + (galT != null)
           + " exp=" + (expT != null) + " com=" + (comT != null)); Environment.Exit(3); }

        // ---- 串口连接（CSDirect 时代验证过 CorCom.Open(COM)）----
        object com = Activator.CreateInstance(comT);
        _com = com;
        var openM = comT.GetMethods().FirstOrDefault(m => m.Name == "Open"
            && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType == typeof(string));
        if (openM == null) { P("FATAL: CorCom.Open(string) 不存在"); Environment.Exit(4); }
        object ro = openM.Invoke(com, new object[] { comPort });
        P("[1] CorCom.Open(" + comPort + ") = " + ro);
        if (ro is bool && !(bool)ro) { P("FATAL: 串口打开失败（被占用？）"); Environment.Exit(4); }
        var stM = comT.GetMethod("StartThread");
        if (stM != null) { Try(() => stM.Invoke(com, null), 5000); P("    StartThread ok"); }
        Thread.Sleep(500);

        // ---- ctx 装配（S1-S7 实证配方，逐项）----
        ctx = Activator.CreateInstance(ctxT);
        ctxT.GetField("_com", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(ctx, com);
        object pp = Activator.CreateInstance(Find("ParsingParamsClass"));
        ctxT.GetProperty("ParsingParms").SetValue(ctx, pp, null);
        ctxT.GetProperty("ParsingParmsAux").SetValue(ctx, Activator.CreateInstance(Find("ParsingParamsClass")), null);
        var ctxFld = Find("ParsingParamsClass").GetField("context",
            BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        if (ctxFld != null)
        {
            ctxFld.SetValue(pp, ctx);
            object aux = ctxT.GetProperty("ParsingParmsAux").GetValue(ctx, null);
            if (aux != null) ctxFld.SetValue(aux, ctx);
            P("    pp.context injected");
        }
        ctxT.GetProperty("ExpTimeHlp").SetValue(ctx, Activator.CreateInstance(Find("ExpTimeHlpClass")), null);
        ctxT.GetProperty("ExpParamsBytes").SetValue(ctx,
            Activator.CreateInstance(Find("ExpParamsBytesClass"), new object[] { pp }), null);
        send = Activator.CreateInstance(Find("ExpComSendClass"), new object[] { ctx });
        ctxT.GetProperty("ExpComSend").SetValue(ctx, send, null);
        ctxT.GetProperty("CellsSwitch").SetValue(ctx, Activator.CreateInstance(Find("CellsSwitchClass"), new object[] { ctx }), null);
        ctxT.GetProperty("ExtComHlp").SetValue(ctx, Activator.CreateInstance(Find("ExtComHlpClass"), new object[] { ctx }), null);
        var edhF = ctxT.GetField("ExtDevHlp", BindingFlags.Instance | BindingFlags.Public);
        if (edhF != null) edhF.SetValue(ctx, Activator.CreateInstance(Find("ExtDevHlpClass"), new object[] { ctx }));
        var eadP = ctxT.GetProperty("ExtAmpData");
        if (eadP != null && eadP.CanWrite)
        {
            Type eadT = Find("ExtAmpData");
            if (eadT != null)
            {
                object ead = null;
                try { ead = Activator.CreateInstance(eadT); } catch { }
                if (ead != null)
                {
                    eadP.SetValue(ctx, ead, null);
                    foreach (var pn in new[] { "VotCoefficient", "CurrCoefficient" })
                    {
                        var p2 = ead.GetType().GetProperty(pn);
                        if (p2 != null && p2.CanWrite) { try { p2.SetValue(ead, 1.0, null); } catch { } }
                    }
                }
            }
        }
        P("[2] ctx assembled");

        // ---- ★ 收包委托挂载（CS5 的 "SetConnect" 等价物）----
        //   BaseCorrCom.OnRecePackage : Comdelegate+RecePackage(byte[], bool)
        //   BaseContext.Com_OnRecePackage(byte[], bool) —— ctx 的收包处理器。
        //   进程内装配直接注入 _com 绕过了软件自己的接线，数据帧会被静默丢弃
        //   （2026-11-18 真机实证：.cor 只有头、VoltList=0、OCP 读"没有接收到数据"）。
        //   挂上后设备数据帧 → Com_OnRecePackage → 解析 → AddData → VoltList/落盘。
        try
        {
            var onRecP = comT.GetProperty("OnRecePackage", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                      ?? comT.BaseType.GetProperty("OnRecePackage", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            var handlerM = ctxT.GetMethod("Com_OnRecePackage", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (onRecP != null && handlerM != null)
            {
                var delType = onRecP.PropertyType;
                var d = Delegate.CreateDelegate(delType, ctx, handlerM, true);
                object curObj = onRecP.GetValue(com, null);
                var curDel = curObj as Delegate;
                var combined = curDel == null ? d : Delegate.Combine(curDel, d);
                onRecP.SetValue(com, combined, null);
                P("    OnRecePackage += ctx.Com_OnRecePackage  [" + delType.Name + "]");
            }
            else P("    [warn] 委托挂点未找到 onRecP=" + (onRecP != null) + " handler=" + (handlerM != null));
            var edeM = comT.GetMethod("EnableDataEvent", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                    ?? comT.BaseType.GetMethod("EnableDataEvent", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (edeM != null) { edeM.Invoke(com, new object[] { true }); P("    EnableDataEvent(true)"); }
        }
        catch (Exception e) { P("    [warn] 委托挂载失败: " + e.Message); }

        // ---- 双极性两轮（或单轮）----
        var results = new List<double[]>();   // [I_A, E_med, n, E_first, E_last]
        double[] polarities = single ? new[] { curr_mA } : new[] { curr_mA, -curr_mA };
        int round = 0;
        foreach (double pol in polarities)
        {
            round++;
            P("");
            P("======== 第 " + round + " 轮：I = " + pol + " mA ========");
            var res = RunOne(pol, testTime);
            if (res == null) { P("!! 本轮失败"); if (round == 1) { P("RESULT_JSON {\"ok\":false}"); Environment.Exit(6); } continue; }
            results.Add(res);
        }

        // ---- 收尾：断开 ----
        try { comT.GetMethod("Close").Invoke(com, null); } catch { }

        // ---- R 计算 ----
        P("");
        P("======== 结果 ========");
        if (results.Count == 2)
        {
            double dI = results[0][0] - results[1][0];          // A
            double dE = results[0][1] - results[1][1];          // V
            double R = Math.Abs(dI) > 1e-15 ? dE / dI : double.NaN;
            P("E(+I)=" + results[0][1].ToString("F6") + " V  E(-I)=" + results[1][1].ToString("F6") + " V");
            P("R = ΔE/ΔI = " + R.ToString("F2") + " Ω   （双极性，消热电动势）");
            P("RESULT_JSON {\"ok\":true,\"R_ohm\":" + R.ToString("F3")
              + ",\"I_mA\":" + curr_mA + ",\"E_pos\":" + results[0][1].ToString("F6")
              + ",\"E_neg\":" + results[1][1].ToString("F6")
              + ",\"n_pos\":" + (int)results[0][2] + ",\"n_neg\":" + (int)results[1][2] + "}");
        }
        else if (results.Count == 1)
        {
            double R = results[0][1] / results[0][0];
            P("E=" + results[0][1].ToString("F6") + " V @ I=" + results[0][0] * 1000 + " mA");
            P("R = E/I = " + R.ToString("F2") + " Ω   （单极性，含偏移）");
            P("RESULT_JSON {\"ok\":true,\"R_ohm\":" + R.ToString("F3")
              + ",\"I_mA\":" + (results[0][0] * 1000) + ",\"E\":" + results[0][1].ToString("F6")
              + ",\"n\":" + (int)results[0][2] + ",\"single\":true}");
        }
        else { P("RESULT_JSON {\"ok\":false}"); Environment.Exit(7); }
        // ★ CS5 收包/轮询线程是前台线程，Main 返回后 CLR 一直等（与 CS6
        //   CheckPackReceiveThread 同款）；必须显式 Environment.Exit。
        P("[done] exit");
        Environment.Exit(0);
        return 0;
    }

    // ---- 单轮恒流阶跃 ----
    static double[] RunOne(double curr_mA, double testTime)
    {
        // 参数对象（每轮全新，防跨轮状态污染）
        object prm = Activator.CreateInstance(galT);
        galT.GetProperty("baseContext").SetValue(prm, ctx, null);
        SetP(prm, "PorCurr", (float)curr_mA);
        SetP(prm, "CurrUnit", 1);                    // 1=mA（CS6 同款语义，默认值回读核对）
        SetP(prm, "TestTime", (float)testTime);
        SetP(prm, "TimeUnit", 0);
        SetP(prm, "ExpTime", (float)(testTime + 30));   // S7 教训：ExpTime=0 → 秒完拒收
        foreach (var stop in new[] { "UseStopEvent", "UseStopByVolt", "UseStopByCharge" })
            SetP(prm, stop, false);
        string fname = "r_meter_" + Math.Abs(curr_mA).ToString("0.###") + "mA_"
                     + DateTime.Now.ToString("HHmmss");
        SetP(prm, "FileName", fname);
        SetP(prm, "FilePath", Path.Combine(Path.GetTempPath(), fname));
        galT.GetProperty("ExpType").SetValue(prm, Enum.Parse(expEnum, "ID_GalStatic"), null);
        ctxT.GetProperty("CurExp").SetValue(ctx, Enum.Parse(expEnum, "ID_GalStatic"), null);
        // 回读关键参数核对
        P("    prm: PorCurr=" + GetP(prm, "PorCurr") + " CurrUnit=" + GetP(prm, "CurrUnit")
          + " TestTime=" + GetP(prm, "TestTime") + " ExpType=" + GetP(prm, "ExpType"));

        // BaseIO 注入（InitExp 第一件事取它）
        object bio = GetP(prm, "BaseIO");
        object dev = GetP(prm, "DevParam");
        if (dev != null && bio != null)
        {
            var dbo = dev.GetType().GetProperty("BaseIO");
            if (dbo != null) dbo.SetValue(dev, bio, null);
            try { dev.GetType().GetProperty("WaitSecond").SetValue(dev, 30, null); } catch { }
        }

        // ExpClass + 原生落盘
        object ec = Activator.CreateInstance(expT, new object[] { ctx, prm });
        ctxT.GetProperty("ActiveExpClass").SetValue(ctx, ec, null);
        Try(() => { expT.GetMethod("BeginStartWriteFile", Type.EmptyTypes).Invoke(ec, null); return null; }, 6000);

        // 下发链（S1→S2→S4→S5→S6，恒流不需要 OCP：isGetOcp=false isCallWatiFun=false）
        SetP(prm, "Persent", 0.0);
        P("[S2] SendMethodInit  : " + Try(() => galT.GetMethod("SendMethodInit", Type.EmptyTypes).Invoke(prm, null), 15000));
        Thread.Sleep(300);
        ClearData();
        P("[S4] SendMethodParams: " + Try(() => galT.GetMethod("SendMethodParams", Type.EmptyTypes).Invoke(prm, null), 25000));
        Thread.Sleep(300);
        P("[S5] InitExp          : " + Try(() => send.GetType().GetMethod("InitExp").Invoke(send, new object[] { prm }), 15000));
        Thread.Sleep(300);
        ClearData();
        // ExpIsFinished 翻开（S7 教训）
        var sifM = expT.GetMethod("set_ExpIsFinished");
        if (sifM != null) { try { sifM.Invoke(ec, new object[] { false }); } catch { } }
        // ★ 2026-11-18 第五轮定案：CS5 是问答式采样，WatiFun 才是采集循环。
        //   isCallWatiFun=true 时 StartMethod 会阻塞跑满整个实验（42s）；
        //   放后台线程跑，主线程并行观察 VoltList 与串口原始缓冲。
        object[] sa = new object[] { prm, true, true, "" };
        string s6ret = "(running)";
        var tStart = new Thread(() =>
        {
            try
            {
                var rr = send.GetType().GetMethod("StartMethod").Invoke(send, sa);
                s6ret = "OK:" + rr + " err='" + sa[3] + "'";
            }
            catch (Exception e) { s6ret = "EXC:" + e.Message; }
        });
        tStart.IsBackground = true;
        tStart.Start();
        P("[S6] StartMethod 后台启动（WatiFun 轮询循环 ~42s）");

        // ---- 采集：并行观察 VoltList + 串口原始缓冲 ----
        var vL = expT.GetProperty("VoltList");
        var volt = new List<double>();          // VoltList 入库的 E
        var ocpV = new List<double>();          // OCP 同步轮询读回的 E（对照）
        var mOcp = galT.GetMethods().FirstOrDefault(m => m.Name == "GetOcpValueAutoRange"
                                                      && m.GetParameters().Length == 2);
        var bufF = comT.BaseType == null ? null : comT.BaseType.GetField("m_DataBuffer",
            BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        var getUnin = comT.BaseType == null ? null : comT.BaseType.GetMethod("GetUninPack",
            BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        double t0 = Now();
        double deadline = t0 + testTime + 35;
        bool railed = false;
        int lastLogged = -1;
        while (Now() < deadline && tStart.IsAlive)
        {
            Thread.Sleep(500);
            try
            {
                var vs = vL == null ? null : vL.GetValue(ec, null) as System.Collections.IList;
                if (vs != null && vs.Count > volt.Count)
                    for (int i = volt.Count; i < vs.Count; i++) volt.Add(Convert.ToDouble(vs[i]));
            }
            catch { }
            // 每 5 秒记录一次串口原始缓冲长度（确认设备到底有没有发字节）
            int sec = (int)(Now() - t0);
            if (sec / 5 != lastLogged / 5)
            {
                lastLogged = sec;
                string bufInfo = "?";
                try
                {
                    var b = bufF == null ? null : bufF.GetValue(_com) as System.Collections.IList;
                    bufInfo = b == null ? "n/a" : b.Count + "B";
                    if (getUnin != null)
                    {
                        var raw = getUnin.Invoke(_com, null) as byte[];
                        if (raw != null && raw.Length > 0)
                            bufInfo += " unin=" + BitConverter.ToString(raw, 0, Math.Min(raw.Length, 24));
                    }
                }
                catch (Exception e) { bufInfo = "EXC " + e.Message; }
                P("    [" + sec + "s] VoltList=" + volt.Count + "  rxbuf=" + bufInfo);
            }
            double eNow = volt.Count > 0 ? volt[volt.Count - 1] : 0.0;
            if (Math.Abs(eNow) > 9.0) { railed = true; break; }
        }
        P("[S6] StartMethod 后台结束: " + s6ret);
        // 停止 + 落盘
        Try(() => send.GetType().GetMethod("SendSysStop").Invoke(send, null), 8000);
        Thread.Sleep(800);
        Try(() => expT.GetMethod("WriteDataNow", Type.EmptyTypes).Invoke(ec, null), 5000);
        var ewf = expT.GetMethod("EndWriteFile", Type.EmptyTypes);
        if (ewf != null) Try(() => ewf.Invoke(ec, null), 5000);

        if (railed)
        {
            P("    !! |E|>9V 合规电压触顶：R 超出本档电流量程（开路或大阻值），本轮作废");
            return null;
        }
        if (volt.Count < 5)
        {
            P("    !! VoltList 无点（" + volt.Count + "），OCP 轮询对照 " + ocpV.Count + " 点");
            return null;
        }
        P("    [采集通道] VoltList 入库 有效点数=" + volt.Count);
        // 中段中位数（去头去尾 20%）
        int lo = (int)(volt.Count * 0.2), hi = (int)(volt.Count * 0.8);
        if (hi <= lo) { lo = 0; hi = volt.Count; }
        var mid = volt.GetRange(lo, hi - lo);
        mid.Sort();
        double med = mid[mid.Count / 2];
        double iA = curr_mA * 1e-3;
        P("    本轮：n=" + volt.Count + "  E_med=" + med.ToString("F6") + " V"
          + "  E_first=" + volt[0].ToString("F6") + "  E_last=" + volt[volt.Count - 1].ToString("F6"));
        string docFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Personal),
                                      "Corrtest", "Data", fname);
        if (File.Exists(docFile)) P("    落盘：" + docFile + " (" + new FileInfo(docFile).Length + " B)");
        return new double[] { iA, med, volt.Count, volt[0], volt[volt.Count - 1] };
    }

    static void ClearData()
    {
        try
        {
            var getCom = ctxT.GetMethods().FirstOrDefault(m => m.Name == "GetCom" && m.GetParameters().Length == 0);
            object c = getCom == null ? null : getCom.Invoke(ctx, null);
            if (c == null) return;
            var cd = c.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                       .FirstOrDefault(m => m.Name == "ClearData");
            if (cd != null) cd.Invoke(c, null);
        }
        catch { }
    }
    static void SetP(object o, string name, object v)
    {
        try
        {
            var p = o.GetType().GetProperty(name);
            if (p != null && p.CanWrite) p.SetValue(o, Convert.ChangeType(v, p.PropertyType), null);
        }
        catch (Exception e) { P("    [set " + name + " EXC] " + e.Message); }
    }
    static object GetP(object o, string name)
    {
        try { var p = o.GetType().GetProperty(name); return p == null ? null : p.GetValue(o, null); }
        catch { return null; }
    }
    static double Now() { return DateTime.Now.Ticks / 1e7; }
}
