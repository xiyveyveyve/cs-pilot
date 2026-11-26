// t_cs5probe.cs —— CS5 应答变体扫描专用探针（精简版：只走到 StartMethod）
//
// 用法：t_cs5probe.exe --port 31050
// 输出：单行结论 "StartMethod → ret=... err='...'" 供 scan_ack.py 抓取
//
// 装配要点（2026-11-10 实证，全部必需）：
//   * 连接：SockectCom.Open() + StartThread()
//   * 连接注入：写 BaseContext 私有字段 _com（CS5 无 SetConnect）
//   * ctx 接口成员按依赖顺序补齐（否则 set_baseContext NRE）
//   * 补 BaseContext.ExtDevHlp 公有字段（否则 StartMethod 内 SendRotatingSpeed NRE）
//   * 枚举一律按名解析（CS5 与 CS6 数值不同）
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;

static class Cs5Probe
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

    static string Try(Func<object> f, int ms, out object result)
    {
        Exception err = null;
        object res = null;
        var th = new Thread(() => { try { res = f(); } catch (Exception e) { err = e; } });
        th.IsBackground = true;
        th.Start();
        bool ok = th.Join(ms);
        result = res;
        if (!ok) return "HANG>" + ms + "ms";
        if (err != null)
        {
            var ie = err is TargetInvocationException && err.InnerException != null ? err.InnerException : err;
            return "EXC " + ie.GetType().Name + ": " + ie.Message;
        }
        return "OK";
    }

    static int Main(string[] args)
    {
        int port = 31050;
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == "--port") int.TryParse(args[i + 1], out port);

        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (!File.Exists(p)) continue;
            try { _asms[n] = Assembly.LoadFrom(p); } catch { }
        }
        if (_asms.Count == 0) { Console.WriteLine("StartMethod → 程序集全加载失败"); return 3; }

        Type ctxT = Find("BaseContext"), ocpT = Find("OcpParams"),
             expT = Find("ExpClass"), sockT = Find("SockectCom"),
             expEnumT = Find("Experiment");
        if (ctxT == null || ocpT == null || expT == null || sockT == null || expEnumT == null)
        {
            Console.WriteLine("StartMethod → 关键类型缺失");
            return 3;
        }

        object result;
        // ---- 连接 ----
        object com = Activator.CreateInstance(sockT);
        string r = Try(() => sockT.GetMethod("Open", new[] { typeof(string) })
                                  .Invoke(com, new object[] { "127.0.0.1:" + port }), 10000, out result);
        if (r != "OK" || !(bool)result)
        {
            Console.WriteLine("StartMethod → 连接失败 " + r);
            return 4;
        }
        Try(() => { var m = sockT.GetMethod("StartThread"); if (m != null) m.Invoke(com, null); return null; }, 5000, out result);
        Thread.Sleep(300);

        // ---- 上下文 ----
        object ctx = Activator.CreateInstance(ctxT);
        ctxT.GetField("_com", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(ctx, com);

        object pp;
        Try(() => Activator.CreateInstance(Find("ParsingParamsClass")), 5000, out pp);
        Try(() => { ctxT.GetProperty("ParsingParms").SetValue(ctx, pp, null); return null; }, 3000, out result);
        Try(() => { ctxT.GetProperty("ParsingParmsAux").SetValue(ctx, Activator.CreateInstance(Find("ParsingParamsClass")), null); return null; }, 3000, out result);
        Try(() => { ctxT.GetProperty("ExpTimeHlp").SetValue(ctx, Activator.CreateInstance(Find("ExpTimeHlpClass")), null); return null; }, 3000, out result);
        Try(() => { ctxT.GetProperty("ExpParamsBytes").SetValue(ctx, Activator.CreateInstance(Find("ExpParamsBytesClass"), new object[] { pp }), null); return null; }, 3000, out result);
        object send;
        Try(() => Activator.CreateInstance(Find("ExpComSendClass"), new object[] { ctx }), 5000, out send);
        Try(() => { ctxT.GetProperty("ExpComSend").SetValue(ctx, send, null); return null; }, 3000, out result);
        Try(() => { ctxT.GetProperty("CellsSwitch").SetValue(ctx, Activator.CreateInstance(Find("CellsSwitchClass"), new object[] { ctx }), null); return null; }, 3000, out result);
        Try(() => { ctxT.GetProperty("ExtComHlp").SetValue(ctx, Activator.CreateInstance(Find("ExtComHlpClass"), new object[] { ctx }), null); return null; }, 3000, out result);

        // ---- ExtDevHlp 公有字段（StartMethod 内 SendRotatingSpeed 依赖）----
        var edhF = ctxT.GetField("ExtDevHlp", BindingFlags.Instance | BindingFlags.Public);
        if (edhF != null)
        {
            Try(() => { edhF.SetValue(ctx, Activator.CreateInstance(Find("ExtDevHlpClass"), new object[] { ctx })); return null; }, 3000, out result);
        }

        // ---- 参数 ----
        object prm = Activator.CreateInstance(ocpT);
        ocpT.GetProperty("baseContext").SetValue(prm, ctx, null);
        ocpT.GetProperty("TestTime").SetValue(prm, 20f, null);
        ocpT.GetProperty("TestTimeUnit").SetValue(prm, 1, null);
        string baseName = Path.Combine(Path.GetTempPath(), "cspilot_cs5scan_" + port);
        ocpT.GetProperty("FilePath").SetValue(prm, baseName, null);
        ocpT.GetProperty("FileName").SetValue(prm, Path.GetFileName(baseName), null);
        ocpT.GetProperty("ExpType").SetValue(prm, Enum.Parse(expEnumT, "ID_OCP"), null);
        ctxT.GetProperty("CurExp").SetValue(ctx, Enum.Parse(expEnumT, "ID_OCP"), null);

        // ---- ExpClass ----
        object ec;
        r = Try(() => Activator.CreateInstance(expT, new object[] { ctx, prm }), 8000, out ec);
        if (r != "OK") { Console.WriteLine("StartMethod → ExpClass 失败 " + r); return 5; }
        ctxT.GetProperty("ActiveExpClass").SetValue(ctx, ec, null);

        Try(() => { expT.GetMethod("BeginStartWriteFile", Type.EmptyTypes).Invoke(ec, null); return null; }, 6000, out result);

        // ---- InitExp ----
        string rInit = Try(() => send.GetType().GetMethod("InitExp").Invoke(send, new object[] { prm }), 12000, out result);
        if (rInit != "OK")
        {
            Console.WriteLine("StartMethod → InitExp 失败 " + rInit);
            return 6;
        }

        // ---- StartMethod ----
        object[] smArgs = new object[] { prm, true, false, "" };
        string rSm = Try(() => send.GetType().GetMethod("StartMethod").Invoke(send, smArgs), 20000, out result);
        if (rSm != "OK")
        {
            Console.WriteLine("StartMethod → " + rSm);
            return 7;
        }
        Console.WriteLine("StartMethod → ret=" + result + " err='" + smArgs[3] + "'");

        // ---- 快速看一眼有没有数据 ----
        Thread.Sleep(3000);
        try
        {
            var tL = expT.GetProperty("TimeList").GetValue(ec, null) as System.Collections.IList;
            var vL = expT.GetProperty("VoltList").GetValue(ec, null) as System.Collections.IList;
            Console.WriteLine("Data → Time=" + (tL == null ? -1 : tL.Count) + " Volt=" + (vL == null ? -1 : vL.Count));
        }
        catch { }

        Try(() => send.GetType().GetMethod("SendSysStop").Invoke(send, null), 8000, out result);
        try { expT.GetMethod("EndWriteFile", Type.EmptyTypes).Invoke(ec, null); } catch { }
        try { sockT.GetMethod("Close").Invoke(com, null); } catch { }
        Environment.Exit(0);
        return 0;
    }
}
