using System; using System.Collections.Generic; using System.Web.Script.Serialization;
class T { static void Main(){
  var js=new JavaScriptSerializer();
  var o = js.Deserialize<Dictionary<string,object>>("{\"a\":1,\"b\":[1,2],\"c\":{\"d\":true}}");
  Console.WriteLine("keys="+o.Count+" a="+o["a"]+" b0="+((object[])o["b"])[0]+" d="+((Dictionary<string,object>)o["c"])["d"]);
}}
