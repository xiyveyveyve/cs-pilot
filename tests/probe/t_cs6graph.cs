// t_cs6graph.cs — 图表链侦查：frmMain 方法清单（Graph/Start/Exp 相关）+ BaseGraphFrm 结构 + ctx.BaseGraph 现值
using System;
using System.IO;
using System.Reflection;

static class T
{
    const string DIR = @"D:\sci\MDI Jade 9";
    static void P(string s) { Console.WriteLine(s); try { File.AppendAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6graph.txt", s + "\r\n"); } catch { } }

    static int Main()
    {
        try { File.Delete(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6graph.txt"); } catch { }
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

        try
        {
            // 1) 全程序集找 BaseGraphFrm 类型
            P("== BaseGraphFrm 类型搜索 ==");
            Type bg = null;
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (!a.GetName().Name.Contains("CSStudio6") && a != exe) continue;
                foreach (Type t in a.GetTypes())
                {
                    if (t.Name == "BaseGraphFrm") { bg = t; P("  " + a.GetName().Name + " → " + t.FullName); }
                    else if (t.Name.Contains("GraphFrm")) P("  [同名族] " + a.GetName().Name + " → " + t.FullName);
                }
            }
            if (bg == null) { P("  !! 未找到 BaseGraphFrm"); return 0; }
            P("== BaseGraphFrm 结构 ==");
            foreach (ConstructorInfo c in bg.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                P("  C " + c.ToString());
            foreach (PropertyInfo p in bg.GetProperties(BindingFlags.Public | BindingFlags.Instance))
                P("  P " + p.PropertyType.Name + " " + p.Name + " w=" + p.CanWrite);
            foreach (MethodInfo m in bg.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
            {
                if (m.Name.StartsWith("get_") || m.Name.StartsWith("set_")) continue;
                P("  M " + m.ToString());
            }
            foreach (FieldInfo f in bg.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                P("  F " + f.FieldType.Name + " " + f.Name);

            // 2) frmMain 方法清单（名字含 Graph/Start/Exp/Show/Add）
            Type fm = null;
            foreach (Type t in exe.GetTypes()) if (t.FullName == "CorrTest.CSStudio.frmMain") { fm = t; break; }
            if (fm != null)
            {
                P("== frmMain 方法（Graph/Start/Exp/Graph 相关） ==");
                foreach (MethodInfo m in fm.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                {
                    string ln = m.Name.ToLowerInvariant();
                    if (ln.Contains("graph") || ln.Contains("start") || ln.Contains("startrun") || ln.Contains("beg") && ln.Contains("exp"))
                        P("  M " + m.ToString());
                }
                P("== frmMain 字段（Graph 相关） ==");
                foreach (FieldInfo f in fm.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                {
                    string ln = f.Name.ToLowerInvariant();
                    if (ln.Contains("graph") || f.FieldType.Name.Contains("Graph"))
                        P("  F " + f.FieldType.FullName + " " + f.Name);
                }
            }

            // 3) BaseContext 全方法（Graph/Show 相关）
            Type bc = null;
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (!a.GetName().Name.Contains("CSStudio6")) continue;
                foreach (Type t in a.GetTypes()) if (t.Name == "BaseContext") { bc = t; break; }
                if (bc != null) break;
            }
            if (bc != null)
            {
                P("== BaseContext 方法（Graph/Show 相关） ==");
                foreach (MethodInfo m in bc.GetMethods(BindingFlags.Public | BindingFlags.Instance))
                {
                    string ln = m.Name.ToLowerInvariant();
                    if (ln.Contains("graph") || ln.Contains("show") || ln.Contains("graphfrm"))
                        P("  M " + m.ToString());
                }
            }
        }
        catch (Exception e) { P("FATAL " + e.Message + "\n" + e.StackTrace); }
        P("DONE");
        return 0;
    }
}
