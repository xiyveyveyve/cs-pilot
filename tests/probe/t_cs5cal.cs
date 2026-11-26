// t_cs5cal.cs — 黑盒标定 GetVoltValue/GetCurrValue 的字节编码公式
// 依据：ExpCallWatiFun 实锤应答格式 7B(data[1..3]=volt3B,data[4..6]=curr3B) / 5B(data[1..2]=volt2B,data[3..4]=curr2B)
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;

static class CalProbe
{
    const string DIR5 = @"D:\sci\CS Studio5\CS Studio5";
    static readonly string[] DLLS = new string[] {
        "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
        "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
        "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll",
        "CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};
    static readonly System.Collections.Generic.Dictionary<string, Assembly> _asms =
        new System.Collections.Generic.Dictionary<string, Assembly>();

    static Type Find(string n)
    {
        foreach (var kv in _asms)
            foreach (var t in T(kv.Value)) if (t != null && t.Name == n) return t;
        return null;
    }
    static Type[] T(Assembly a) { try { return a.GetTypes(); } catch (ReflectionTypeLoadException e) { return e.Types; } catch { return new Type[0]; } }

    static void P(string s) { Console.WriteLine(s); Console.Out.Flush(); }

    static int Main(string[] args)
    {
        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (File.Exists(p)) { try { _asms[n] = Assembly.LoadFrom(p); } catch { } }
        }
        var ctxT = Find("BaseContext"); var ppt = Find("ParsingParamsClass");
        if (ctxT == null || ppt == null) { P("FATAL type missing"); return 3; }
        var BF = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        object ctx = Activator.CreateInstance(ctxT);
        object pp = Activator.CreateInstance(ppt);
        ctxT.GetProperty("ParsingParms").SetValue(ctx, pp, null);
        // FlushParams 用（本探针不发送，但保持一致）
        var ctxFld = ppt.GetField("context", BF);
        if (ctxFld != null) ctxFld.SetValue(pp, ctx);

        // ★ dump ctx 全属性 null 状态 + 自动装配 null 引用属性（找 GetVoltValue 的 NRE 根）
        P("=== BaseContext 属性装配 ===");
        foreach (var pr in ctxT.GetProperties(BF))
        {
            object v = null;
            try { v = pr.GetValue(ctx, null); } catch { }
            string vs;
            if (v == null)
            {
                // 尝试构造注入
                if (pr.CanWrite && pr.PropertyType.IsClass && !pr.PropertyType.IsArray)
                {
                    try
                    {
                        object nv = Activator.CreateInstance(pr.PropertyType);
                        pr.SetValue(ctx, nv, null);
                        vs = "null→new " + pr.PropertyType.Name;
                    }
                    catch
                    {
                        vs = "null（构造失败 " + pr.PropertyType.Name + "）";
                    }
                }
                else vs = "null（只读 " + pr.PropertyType.Name + "）";
            }
            else vs = "= " + (v.GetType().Name);
            P("  " + pr.PropertyType.Name.PadRight(24) + " " + pr.Name + " : " + vs);
        }

        var gvolt = ppt.GetMethods(BF).Where(m => m.Name == "GetVoltValue").ToArray();
        var gcurr = ppt.GetMethods(BF).Where(m => m.Name == "GetCurrValue").ToArray();
        foreach (var m in gvolt) P("[sig] " + m);
        foreach (var m in gcurr) P("[sig] " + m);
        var volt3 = gvolt.FirstOrDefault(m => { var ps = m.GetParameters(); return ps.Length == 3 && ps[0].ParameterType == typeof(byte[]); });
        var curr3 = gcurr.FirstOrDefault(m => { var ps = m.GetParameters(); return ps.Length == 3 && ps[0].ParameterType == typeof(byte[]); });
        if (volt3 == null || curr3 == null) { P("FATAL GetVolt/Curr(3p) not found"); return 4; }

        P("");
        P("=== 3B 标定（WatiFun 7B 格式：data[1..3]=volt, data[4..6]=curr）===");
        int[] raws = new int[] { 0x000000, 0x000001, 0x0000FF, 0x400000, 0x7FFFFF, 0x800000, 0x800001, 0xC00000, 0xFFFFFF, 0x010000, 0x001000 };
        foreach (int r in raws)
        {
            var data = new byte[] { 0x53, (byte)(r >> 16 & 0xFF), (byte)(r >> 8 & 0xFF), (byte)(r & 0xFF), 0, 0, 0 };
            object v = null, c = null; string ve = "", ce = "";
            try { v = volt3.Invoke(pp, new object[] { data, 1, 3 }); } catch (Exception e) { ve = e.InnerException != null ? e.InnerException.Message : e.Message; }
            try { c = curr3.Invoke(pp, new object[] { data, 4, 3 }); } catch (Exception e) { ce = e.InnerException != null ? e.InnerException.Message : e.Message; }
            P(string.Format("  raw24={0:X6}  volt={1}{2}  curr={3}{4}",
                r, v == null ? "?" : Convert.ToString(v), ve == "" ? "" : " EXC:" + ve,
                c == null ? "?" : Convert.ToString(c), ce == "" ? "" : " EXC:" + ce));
        }
        P("");
        P("=== 2B 标定（WatiFun 5B 格式：data[1..2]=volt, data[3..4]=curr）===");
        int[] raw2s = new int[] { 0x0000, 0x0001, 0x00FF, 0x4000, 0x7FFF, 0x8000, 0x8001, 0xC000, 0xFFFF, 0x0100, 0x0010 };
        foreach (int r in raw2s)
        {
            var data = new byte[] { 0x53, (byte)(r >> 8 & 0xFF), (byte)(r & 0xFF), 0, 0 };
            object v = null, c = null; string ve = "", ce = "";
            try { v = volt3.Invoke(pp, new object[] { data, 1, 2 }); } catch (Exception e) { ve = e.InnerException != null ? e.InnerException.Message : e.Message; }
            try { c = curr3.Invoke(pp, new object[] { data, 3, 2 }); } catch (Exception e) { ce = e.InnerException != null ? e.InnerException.Message : e.Message; }
            P(string.Format("  raw16={0:X4}  volt={1}{2}  curr={3}{4}",
                r, v == null ? "?" : Convert.ToString(v), ve == "" ? "" : " EXC:" + ve,
                c == null ? "?" : Convert.ToString(c), ce == "" ? "" : " EXC:" + ce));
        }
        P("");
        P("=== 2B/3B 标志探测：ParsingParamsClass 布尔字段 ===");
        foreach (var f in ppt.GetFields(BF))
            if (f.FieldType == typeof(bool))
                P("  bool " + f.Name + " = " + f.GetValue(pp));
        P("[done]");
        return 0;
    }
}
