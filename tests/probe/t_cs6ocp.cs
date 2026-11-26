// t_cs6ocp.cs — A5 静态侦查：frmOCP「确定」click 处理器与静默校验分支（夜间自动化 A5）
// 只 LoadFrom + 反射读类型/IL，绝不实例化窗体、不弹 GUI、不碰连接。
using System;
using System.IO;
using System.Reflection;

static class T
{
    const string DIR = @"D:\sci\MDI Jade 9";
    const string OUT = @"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6ocp.txt";
    static void P(string s) { Console.WriteLine(s); try { File.AppendAllText(OUT, s + "\r\n"); } catch { } }

    static int Main()
    {
        try { File.Delete(OUT); } catch { }
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string n = new AssemblyName(e.Name).Name + ".dll";
            string p = Path.Combine(DIR, n);
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        string[] dlls = { "CSStudio6.NetSkin.dll", "CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll",
            "CSStudio6.Connect.dll", "CSStudio6.MathHlp.dll", "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll",
            "CSStudio6.SysLog.dll", "CSStudio6.USControl.dll", "CSStudio6.CorrForm.dll", "CSStudio6.Analysis.dll",
            "CSStudio6.ExtModule.dll" };
        foreach (string d in dlls) { string p = Path.Combine(DIR, d); if (File.Exists(p)) Assembly.LoadFrom(p); }

        Type ocp = null, bpf = null;
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            if (!a.GetName().Name.Contains("CSStudio6")) continue;
            Type[] ts;
            try { ts = a.GetTypes(); } catch { continue; }
            foreach (Type t in ts)
            {
                if (t.FullName == "CSStudio6.CorrForm.MethodForms.frmOCP") ocp = t;
                if (t.Name == "BaseParamFrm") bpf = t;
            }
        }
        if (ocp == null) { P("FATAL frmOCP not found"); return 1; }
        P("[T] frmOCP=" + ocp.FullName + " base=" + (ocp.BaseType != null ? ocp.BaseType.FullName : "?"));
        if (bpf != null) P("[T] BaseParamFrm=" + bpf.FullName + " @" + bpf.Assembly.GetName().Name);

        // 1) 控件字段（找确定按钮）
        P("\n== [1] frmOCP Control-derived 字段 ==");
        foreach (var f in ocp.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        {
            Type bt = f.FieldType;
            bool ctl = false;
            for (Type x = bt; x != null; x = x.BaseType) { if (x.FullName == "System.Windows.Forms.Control") { ctl = true; break; } }
            if (ctl || (f.Name.ToLower().Contains("ok") || f.Name.ToLower().Contains("accept") || f.Name.ToLower().Contains("btn")))
                P("  F " + f.FieldType.Name + " " + f.Name);
        }

        // 2) 事件接线侦查：全方法名清单（Click/OK/Begin/Exp 相关）
        P("\n== [2] frmOCP 方法（含继承链 2 级）Click/OK/Exp/Begin 相关 ==");
        Type cur = ocp;
        for (int level = 0; cur != null && level < 3; level++, cur = cur.BaseType)
        {
            foreach (var m in cur.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly | BindingFlags.Static))
            {
                string ln = m.Name.ToLower();
                if (ln.Contains("click") || ln.Contains("ok") || ln.Contains("begin") || ln.Contains("exp") || ln.Contains("accept"))
                    P("  [" + level + "]" + cur.Name + "." + m.Name + " IL=" + BodyLen(m) + "B static=" + m.IsStatic);
            }
        }

        // 3) 找疑似确定处理器并 dump IL（含解析后的调用目标）
        string[] cand = { "btnOK_Click", "btOK_Click", "btnOk_Click", "btn_ok_Click", "OK_Click", "btnAccept_Click", "btnSure_Click", "button1_Click", "frmOCP_Click" };
        MethodInfo hit = null;
        foreach (var m in ocp.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly | BindingFlags.Static))
        {
            foreach (string c in cand) if (m.Name.Equals(c, StringComparison.OrdinalIgnoreCase)) { hit = m; break; }
            if (hit != null) break;
        }
        // 兜底：找 (object,EventArgs) 签名且 IL 最大的前 3 个
        if (hit == null)
        {
            MethodInfo[] ms = ocp.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly | BindingFlags.Static);
            MethodInfo best = null; int bestLen = 0;
            foreach (var m in ms)
            {
                var ps = m.GetParameters();
                if (ps.Length == 2 && m.Name.ToLower().Contains("_click") || (ps.Length == 2 && ps[0].ParameterType.Name == "Object" && ps[1].ParameterType.Name.Contains("EventArgs")))
                {
                    int len = BodyLen(m);
                    if (len > bestLen) { bestLen = len; best = m; }
                }
            }
            hit = best;
        }
        if (hit == null) { P("\n== [3] 未找到疑似确定处理器（列出全部 _click 方法名）==");
            foreach (var m in ocp.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly | BindingFlags.Static))
                if (m.Name.ToLower().Contains("click")) P("  ? " + m.Name);
        }
        else
        {
            P("\n== [3] 确定处理器候选: " + ocp.Name + "." + hit.Name + " ==");
            DumpIL(hit);
        }

        // 4) BaseParamFrm 层的 OK/确定公共逻辑
        if (bpf != null)
        {
            P("\n== [4] BaseParamFrm OK/Begin/Exp 相关方法 ==");
            foreach (var m in bpf.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly | BindingFlags.Static))
            {
                string ln = m.Name.ToLower();
                if (ln.Contains("ok") || ln.Contains("begin") || ln.Contains("exp") || ln.Contains("check") || ln.Contains("valid") || ln.Contains("save"))
                    P("  " + bpf.Name + "." + m.Name + " IL=" + BodyLen(m) + "B");
            }
        }
        P("\n[done]");
        return 0;
    }

    static int BodyLen(MethodBase m)
    {
        try { return m.GetMethodBody().GetILAsByteArray().Length; } catch { return -1; }
    }

    static void DumpIL(MethodBase m)
    {
        byte[] il;
        try { il = m.GetMethodBody().GetILAsByteArray(); } catch (Exception e2) { P("  IL unreadable: " + e2.Message); return; }
        if (il.Length <= 8) { P("  IL=" + il.Length + "B HEX: " + BitConverter.ToString(il) + "  ← 桩/薄方法"); return; }
        Module mod = m.Module;
        P("  IL=" + il.Length + "B，解析调用目标：");
        for (int i = 0; i < il.Length; i++)
        {
            byte op = il[i];
            int tokLen = (op == 0x28 || op == 0x6F || op == 0x73 || op == 0x72 || op == 0x27 || op == 0x75) ? 4 : 0;
            if (tokLen > 0 && i + 4 < il.Length)
            {
                int tok = il[i + 1] | (il[i + 2] << 8) | (il[i + 3] << 16) | (il[i + 4] << 24);
                string name = "?";
                try
                {
                    MethodBase mb = null;
                    if (op == 0x6F || op == 0x28 || op == 0x73) mb = mod.ResolveMethod(tok);
                    else if (op == 0x72) { string s = mod.ResolveString(tok); name = "ldstr \"" + (s.Length > 60 ? s.Substring(0, 60) : s) + "\""; }
                    if (mb != null) name = mb.DeclaringType.Name + "." + mb.Name;
                }
                catch { name = "?"; }
                if (name != "?") P("    +" + i + " " + (op == 0x6F ? "callvirt" : op == 0x73 ? "newobj" : "call") + " -> " + name);
                i += tokLen;
            }
        }
    }
}
