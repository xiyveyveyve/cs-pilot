using System;
using System.Reflection;
class T {
  static void Main(){
    string dir = @"D:\sci\MDI Jade 9";
    var bi = Assembly.LoadFrom(System.IO.Path.Combine(dir,"CSStudio6.BaseInterface.dll"));
    var ctxType = bi.GetType("CSStudio6.BaseInterface.Context.BaseContext");
    Console.WriteLine("BaseContext = " + (ctxType==null?"NULL":ctxType.FullName));
    if(ctxType!=null){
      var inst = Activator.CreateInstance(ctxType);
      Console.WriteLine("instance ok: " + inst.GetType().Name);
      Console.WriteLine("PointCount=" + ctxType.GetProperty("PointCount").GetValue(inst));
      Console.WriteLine("thisexp=" + ctxType.GetProperty("ThisExp").GetValue(inst));
    }
    Console.WriteLine("PF=" + Environment.Is64BitProcess + " ver=" + Environment.Version);
  }
}
