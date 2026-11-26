using System;
using System.IO;
using System.Reflection;
class T {
  static StreamWriter w;
  static void L(string s){ w.WriteLine(s); w.Flush(); }
  static void Main(){
    w = new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t2.log", false);
    L("start PF64=" + Environment.Is64BitProcess);
    string dir = @"D:\sci\MDI Jade 9";
    L("before load");
    var bi = Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.BaseInterface.dll"));
    L("loaded " + bi.FullName);
    Type ctxType = null;
    foreach(var t in bi.GetTypes()) if (t.Name=="BaseContext" && !t.IsAbstract){ ctxType=t; break; }
    L("ctxType=" + (ctxType==null?"NULL":ctxType.FullName));
    if(ctxType!=null){
      L("before ctor");
      object inst = Activator.CreateInstance(ctxType);
      L("ctor ok");
      var p = ctxType.GetProperty("PointCount");
      L("PointCount=" + (p==null?"nop":p.GetValue(inst).ToString()));
    }
    L("done");
    w.Close();
  }
}
