// t_cs6main.cs — frmMain 静态结构侦查：BaseMainFrm 成员、frmMain 的 ctx 获取路径
using System;
using System.IO;
using System.Reflection;

static class T
{
    const string DIR = @"D:\sci\MDI Jade 9";
    static void P(string s) { Console.WriteLine(s); try { File.AppendAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6main.txt", s + "\r\n"); } catch {} }

    static int Main()
    {
        try { File.Delete(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6main.txt"); } catch {}
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
        Assembly exe = Assembly.LoadFrom(Path.Combine(DIR, "CorrTest.CSStudio.exe"));

        Type bm = null, fm = null;
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            if (!a.GetName().Name.Contains("CSStudio6") && a != exe) continue;
            foreach (Type t in a.GetTypes())
            {
                if (t.Name == "BaseMainFrm") bm = t;
                if (t.FullName == "CorrTest.CSStudio.frmMain") fm = t;
            }
        }
        if (bm == null || fm == null) { P("FATAL types not found"); return 1; }

        P("== BaseMainFrm(" + bm.Assembly.GetName().Name + ") 属性 ==");
        foreach (var pr in bm.GetProperties(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
            P("  P " + pr.PropertyType.Name + " " + pr.Name + " w=" + pr.CanWrite);
        P("== BaseMainFrm 字段 ==");
        foreach (var f in bm.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
            P("  F " + f.FieldType.Name + " " + f.Name);
        P("== frmMain 自声明属性（前40） ==");
        int n1 = 0;
        foreach (var pr in fm.GetProperties(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        { if (n1++ < 40) P("  P " + pr.PropertyType.Name + " " + pr.Name); }
        P("== frmMain 自声明字段（含 Context/Main/Com，前60） ==");
        int n2 = 0;
        foreach (var f in fm.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        {
            string ln = f.FieldType.Name + " " + f.Name;
            if (n2++ < 60 && (n2 < 25 || ln.Contains("Context") || ln.Contains("Main") || ln.Contains("Com") || ln.Contains("conn"))) P("  F " + ln);
        }
        P("DONE");
        return 0;
    }
}
