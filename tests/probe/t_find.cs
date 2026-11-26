using System;
using System.Linq;
using System.Reflection;
static class T {
    static void P(string s){ Console.WriteLine(s); }
    static int Main(){
        string dir = @"D:\sci\CS Studio5\CS Studio5";
        foreach (var dll in System.IO.Directory.GetFiles(dir, "CorrTest.*.dll")) {
            Assembly a;
            try { a = Assembly.LoadFrom(dll); } catch { continue; }
            Type[] ts;
            try { ts = a.GetTypes(); } catch { continue; }
            foreach (var t in ts) {
                if (!t.Name.Contains("CommandPackage") && !t.Name.Contains("CorrPackage")) continue;
                P("== " + t.FullName + " @ " + a.GetName().Name);
                foreach (var f in t.GetFields(BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic))
                    if (f.Name.Contains("Ocp") || f.Name.Contains("Read") || f.Name.Contains("Serial") || f.Name.Contains("Boot"))
                        P("   SF " + f.FieldType.Name + " " + f.Name);
            }
        }
        return 0;
    }
}
