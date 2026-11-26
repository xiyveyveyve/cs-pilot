// t_cs5rt.cs — CS5 运行时黑盒：壳的运行时解密激活后，直接实例化 CorrPackage
// 喂应答帧变体 → 问 IsMsgPack/CheckPack/get_Command/get_Length/packModel
// 目的：确认 0x74/0x85 应答是否被分流进 dataMsg（S4 False 元凶）
using System;
using System.IO;
using System.Reflection;

static class P{
  static StreamWriter w;
  static void L(string s){ w.WriteLine(s); }
  const string D5 = @"D:\sci\CS Studio5\CS Studio5";
  static readonly string[] DLLS5 = new string[] {
    "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
    "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
    "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll",
    "CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};

  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static BindingFlags BF = BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;

  static void Main(){
    try{
      string logPath=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,@"..\..\logs\t_cs5rt.txt"));
      using(w=new StreamWriter(logPath,false)){
        L("[t_cs5rt] CS5 运行时黑盒 CorrPackage 侦查 "+DateTime.Now);
        foreach(var n in DLLS5){ string p=Path.Combine(D5,n); if(File.Exists(p)){ try{Assembly.LoadFrom(p);}catch{} } }
        // 找 CorrPackage
        Type cp=null; string cpAsm="";
        foreach(var n in DLLS5){
          string p=Path.Combine(D5,n); if(!File.Exists(p)) continue;
          Assembly a=null; try{a=Assembly.LoadFrom(p);}catch{continue;}
          foreach(var t in T(a)){ if(t!=null&&t.Name=="CorrPackage"){ cp=t; cpAsm=n; break; } }
          if(cp!=null) break;
        }
        if(cp==null){ L("CorrPackage 未找到"); return; }
        L("[CP] CorrPackage @ "+cpAsm);
        // ctors
        L("[ctors]");
        foreach(var c in cp.GetConstructors(BF)){
          var ps=c.GetParameters(); var arr=new string[ps.Length];
          for(int i=0;i<ps.Length;i++) arr[i]=ps[i].ParameterType.Name+" "+ps[i].Name;
          L("  .ctor("+string.Join(", ",arr)+")");
        }
        // methods
        L("[methods]");
        foreach(var m in cp.GetMethods(BF)){
          if(m.DeclaringType==typeof(object)) continue;
          var ps=m.GetParameters(); var arr=new string[ps.Length];
          for(int i=0;i<ps.Length;i++) arr[i]=ps[i].ParameterType.Name+" "+ps[i].Name;
          L("  "+m.ReturnType.Name+" "+m.Name+"("+string.Join(", ",arr)+")");
        }
        L("[fields]");
        foreach(var f in cp.GetFields(BF)) L("  "+f.FieldType.Name+" "+f.Name);
        // 运行时黑盒：实例化 + 喂帧
        object pkg=null;
        foreach(var c in cp.GetConstructors(BF)){
          var ps=c.GetParameters();
          if(ps.Length==0){ pkg=c.Invoke(new object[0]); break; }
        }
        if(pkg==null){ L("[RT] 无无参构造，黑盒跳过"); L("[done]"); return; }
        L("[RT] 实例化成功，开始喂帧");
        // 找成员
        MethodInfo setIsDemo=null,mIsMsg=null,mCheck=null,mGetCmd=null,mGetLen=null,mGetAll=null,mGetModel=null;
        foreach(var m in cp.GetMethods(BF)){
          if(m.Name=="set_AllData"&&m.GetParameters().Length==1) setIsDemo=m;
          else if(m.Name=="IsMsgPack"&&m.GetParameters().Length==0) mIsMsg=m;
          else if(m.Name=="CheckPack"&&m.GetParameters().Length==0) mCheck=m;
          else if(m.Name=="get_Command") mGetCmd=m;
          else if(m.Name=="get_Length") mGetLen=m;
          else if(m.Name=="get_AllData") mGetAll=m;
          else if(m.Name=="get_packModel"||m.Name=="get_PackModel") mGetModel=m;
        }
        FieldInfo fModel=null;
        foreach(var f in cp.GetFields(BF)) if(f.Name.ToLower().Contains("model")) fModel=f;
        if(fModel!=null) L("[RT] packModel 字段 = "+fModel.Name);
        // 变体帧
        // 1) 0x74 方法帧回显（16B，SUM 1E）
        byte[] f74=new byte[16]; f74[0]=0xAA; f74[1]=0x74; f74[15]=0x1E;
        // 2) 0x85 63 应答回显（变长 8B 示例 AA 85 63 0A xx SUM —— 用 sim 实际发法：echo 全帧）
        byte[] f85=new byte[6]{0xAA,0x85,0x63,0x0A,0x00,0xF2}; // AA+85+63+0A+00=1F2? AA+85+63+0A+00 = 0x172 → &0xFF=0x72；修正
        f85[5]=0x72;
        // 3) 0x53 双帧之一 echo（16B AA 53 01 ... SUM）
        byte[] f53=new byte[16]; f53[0]=0xAA; f53[1]=0x53; f53[2]=0x01; f53[15]=(byte)((0xAA+0x53+0x01)&0xFF);
        // 4) CF 帧 AA CF 00 (SUM=AA+CF=0x179→0x79)
        byte[] fcf=new byte[4]{0xAA,0xCF,0x00,0x79};
        // 5) SN 应答 AA + 12B SN + SUM（13B体，总15B？sim: AA+SN12+SUM）
        byte[] fsn=new byte[14]; fsn[0]=0xAA; for(int i=1;i<=12;i++) fsn[i]=(byte)('0'+(i%10)); fsn[13]=0; int s=0xAA; for(int i=1;i<=12;i++) s+=fsn[i]; fsn[13]=(byte)(s&0xFF);
        // 6) CS6 数据帧 60 开头（55 AA ...格式不同，CS5 无此）—— 60+E f32... 10B
        byte[] f60=new byte[10]; f60[0]=0x60; f60[1]=0x3D; f60[2]=0xCC; f60[3]=0xCC; f60[4]=0xCD; for(int i=5;i<9;i++) f60[i]=0; f60[9]=1;
        byte[][] variants=new byte[][]{f74,f85,f53,fcf,fsn,f60};
        string[] names=new string[]{"0x74方法帧回显16B","0x85应答6B","0x53回显16B","AA CF 00 4B","0x81 SN应答14B","0x60数据帧10B"};
        for(int i=0;i<variants.Length;i++){
          try{
            setIsDemo.Invoke(pkg,new object[]{variants[i]});
            object cmd=mGetCmd!=null?mGetCmd.Invoke(pkg,null):null;
            object len=mGetLen!=null?mGetLen.Invoke(pkg,null):null;
            object isMsg=mIsMsg!=null?mIsMsg.Invoke(pkg,null):null;
            object ck=mCheck!=null?mCheck.Invoke(pkg,null):null;
            object model=fModel!=null?fModel.GetValue(pkg):null;
            L("[RT] "+names[i]+" → Command="+(cmd==null?"?":cmd.ToString())
              +" Length="+(len==null?"?":len.ToString())
              +" IsMsgPack="+(isMsg==null?"?":isMsg.ToString())
              +" CheckPack="+(ck==null?"?":ck.ToString())
              +" packModel="+(model==null?"?":model.ToString()));
          }catch(Exception e){
            var ie=e.InnerException??e;
            L("[RT] "+names[i]+" → EXC "+ie.GetType().Name+": "+ie.Message);
          }
        }
        // PART2: CheckPack 长度边界扫描（IsCSTModel true/false 双分支）
        L("[P2] CheckPack 长度边界（内容=AA cmd 00...，SUM 正确）");
        FieldInfo fCST=null;
        foreach(var f in cp.GetFields(BF)) if(f.Name=="IsCSTModel") fCST=f;
        foreach(bool cst in new bool[]{true,false}){
          if(fCST!=null) fCST.SetValue(pkg,cst);
          L("[P2] --- IsCSTModel="+cst+" ---");
          for(int len=2;len<=17;len++){
            byte[] fr=new byte[len]; fr[0]=0xAA; fr[1]=0x53;
            int s2=0xAA+0x53; for(int k=2;k<len-1;k++) s2+=fr[k];
            fr[len-1]=(byte)(s2&0xFF);
            try{
              setIsDemo.Invoke(pkg,new object[]{fr});
              object ck=mCheck.Invoke(pkg,null);
              L("[P2] len="+len+" → CheckPack="+ck);
            }catch(Exception e){
              var ie=e.InnerException??e;
              L("[P2] len="+len+" → EXC "+ie.GetType().Name+"："+ie.Message);
            }
          }
        }
        // PART3: 真实 sim 应答帧形态核对（与 sim_cs5.py 产出一致的字节）
        L("[P3] sim 应答帧形态核对");
        if(fCST!=null) fCST.SetValue(pkg,true);
        byte[][] real=new byte[][]{
          new byte[16],                                    // 占位
          new byte[]{0xAA,0xCF,0x00,0x79},                 // 0x80 53 应答（4B CF）
          new byte[]{0xAA,0xCF,0x01,0x7A},                 // 0x80 51 应答
          new byte[]{0xAA,0x50,0x00,0xFA},                 // 0xD0 应答 echo-0x80（4B）
          new byte[]{0xAA,0x51,0x00,0xFB},                 // 0xD1 应答（4B）
          new byte[]{0xAA,0x0B,0x00,0xBB},                 // 0x8B 应答（4B）
          new byte[]{0xAA,0x09,0x31,0x32,0x33,0x34,0x35,0xC2}, // 0x09 SN5 应答（7B）
          new byte[]{0xAA,0xF9,0x00,0x00,0xC8,0x41,0x52},  // 0xF9 25.0f 应答（7B）
          new byte[]{0xAA,0x88,0x56,0x35,0x2E,0x36,0x08},  // 0x88 版本 V5.6（7B）
        };
        // 第一行做 0x74 真回显
        for(int k=0;k<16;k++) real[0][k]=0; real[0][0]=0xAA; real[0][1]=0x74; real[0][15]=0x1E;
        string[] rn=new string[]{"0x74回显16B","0x80 53→CF 4B","0x80 51→CF 4B","0xD0→echo-80 4B","0xD1→echo-80 4B","0x8B→echo-80 4B","0x09→SN 7B","0xF9→25f 7B","0x88→V5.6 7B"};
        for(int i=0;i<real.Length;i++){
          try{
            setIsDemo.Invoke(pkg,new object[]{real[i]});
            object ck=mCheck.Invoke(pkg,null);
            L("[P3] "+rn[i]+" → CheckPack="+ck);
          }catch(Exception e){
            var ie=e.InnerException??e;
            L("[P3] "+rn[i]+" → EXC "+ie.GetType().Name+"："+ie.Message);
          }
        }
        L("[done]");
      }
    }catch(Exception e){ Console.WriteLine("[FATAL] "+e.GetType().Name+": "+e.Message+"\n"+e.StackTrace); }
  }
}
