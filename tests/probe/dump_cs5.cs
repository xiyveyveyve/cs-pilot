// dump_cs5.cs —— 探 CS5（CorrTest.*）的纯代码宿主可行性
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    string[] need={"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
                   "CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll",
                   "CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll",
                   "CorrTest.CorrCSType.dll"};
    var asms=new List<Assembly>();
    foreach(var n in need){ try{ var a=Assembly.LoadFrom(Path.Combine(dir5,n)); asms.Add(a); L("LOAD OK "+n); }catch(Exception e){ L("LOAD FAIL "+n+" :: "+e.GetType().Name+": "+e.Message); } }
    var bi=asms.Count>0?asms[0]:null;
    L("\n=== Interface asm types (Context/Base*) ===");
    foreach(var a in asms) {
      Type[] ts; try{ ts=a.GetTypes(); }catch(ReflectionTypeLoadException e){ ts=e.Types; }catch{ continue; }
      foreach(var t in ts) if(t!=null && (t.Name.Contains("BaseContext")||t.Name=="BaseMainFrm"||t.Name=="IDataItem"||t.Name=="IExpClass"))
        L("  "+a.GetName().Name+" :: "+t.FullName+" abstract="+t.IsAbstract+" iface="+t.IsInterface);
    }
    L("\n=== BaseContext members ===");
    foreach(var a in asms){
      Type[] ts; try{ ts=a.GetTypes(); }catch(ReflectionTypeLoadException e){ ts=e.Types; }catch{ continue; }
      foreach(var t in ts){
        if(t==null||t.Name!="BaseContext") continue;
        L("-- "+a.GetName().Name+" :: "+t.FullName+" abstract="+t.IsAbstract);
        try{
          foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance)) L("   P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
          foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
            if(!m.Name.StartsWith("get_")&&!m.Name.StartsWith("set_")) L("   M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
        }catch(Exception e){ L("   ERR "+e.Message); }
      }
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5.txt", sb.ToString());
    Environment.Exit(0);
  }
}
