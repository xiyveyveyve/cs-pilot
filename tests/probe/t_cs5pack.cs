// t_cs5pack.cs — CS5 切帧黑盒实验台 v2（2026-11-10）
// CS5 SockectCom 无 ParsingPack；解析链 = AddToDataBuffer(byte[],int) → m_DataBuffer(List) → GetUninPack()。
// SendReturnPackage(pkg, nTimeOut, dataLen, head, nRepeat) 参数名实锤：dataLen=期待长度。
// 本探针：AddToDataBuffer 喂各类帧 → GetUninPack 黑盒问切包结果 + dump m_DataBuffer 残留。
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;

static class T5P
{
    static BindingFlags AI = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
    static BindingFlags AS = BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;

    static void P(string s) { Console.WriteLine(s); }

    static Assembly Load(string dir, string name)
    {
        var p = Path.Combine(dir, name);
        return File.Exists(p) ? Assembly.LoadFrom(p) : null;
    }

    static string DumpObj(object pack)
    {
        var barr = pack as byte[];
        if (barr != null) return "byte[" + barr.Length + "] " + BitConverter.ToString(barr).Replace("-", " ");
        var sb = new StringBuilder(pack.GetType().FullName + " { ");
        foreach (var pr in pack.GetType().GetProperties(AI | AS))
        {
            object pv = null;
            try { pv = pr.GetValue(pack, null); } catch { }
            var pva = pv as byte[];
            sb.Append(pr.Name + "=" + (pva != null ? "byte[" + pva.Length + "] " + BitConverter.ToString(pva).Replace("-", " ")
                : (pv == null ? "null" : pv.ToString())) + "  ");
        }
        return sb.ToString() + "}";
    }

    static int Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        string dir = @"D:\sci\CS Studio5\CS Studio5";
        string[] dlls = {
            "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
            "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
            "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll",
            "CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};
        foreach (var n in dlls) Load(dir, n);

        Type sockT = null;
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            try { foreach (var t in a.GetTypes()) if (t.Name == "SockectCom") { sockT = t; break; } } catch { }
            if (sockT != null) break;
        }
        if (sockT == null) { P("[FATAL] SockectCom 未找到"); return 1; }
        P("[1] SockectCom = " + sockT.FullName);

        object com = Activator.CreateInstance(sockT);
        P("[2] ctor() ok");

        var addBufM = sockT.GetMethods(AI | AS).FirstOrDefault(m => m.Name == "AddToDataBuffer");
        var getUninM = sockT.GetMethods(AI | AS).FirstOrDefault(m => m.Name == "GetUninPack");
        var readBufM = sockT.GetMethods(AI | AS).FirstOrDefault(m => m.Name == "ReadFromDataBuffer");
        P("[3] AddToDataBuffer=" + (addBufM != null ? addBufM.GetParameters().Length + "p" : "无")
          + " GetUninPack=" + (getUninM != null ? "ok" : "无")
          + " ReadFromDataBuffer=" + (readBufM != null ? readBufM.GetParameters().Length + "p" : "无"));

        Action<string> dumpBuffer = delegate(string tag)
        {
            foreach (var fn in new string[] { "m_DataBuffer", "m_DataList", "m_objDataBuffer", "m_objDataList" })
            {
                var f = sockT.GetField(fn, AI);
                if (f == null) continue;
                object v = null;
                try { v = f.GetValue(com); } catch { continue; }
                var q = v as System.Collections.IEnumerable;
                if (q == null) { P("    [" + tag + "] " + fn + " = " + (v == null ? "null" : v.GetType().Name + ":" + v)); continue; }
                int n = 0; var items = new StringBuilder();
                foreach (var it in q)
                {
                    n++;
                    if (n <= 4)
                    {
                        var barr = it as byte[];
                        items.Append(barr != null ? "[" + barr.Length + "B] " + BitConverter.ToString(barr).Replace("-", " ")
                            : (it != null ? it.GetType().Name + "/" + it : "null"));
                        items.Append("  ||  ");
                    }
                }
                P("    [" + tag + "] " + fn + " count=" + n + "  " + items);
            }
        };

        P("[4] 切帧实验（AddToDataBuffer → GetUninPack）");
        byte[][] frames = new byte[][] {
            new byte[] {0xAA,0x53,0x7E,0x6B,0x76,0x7F,0xFF,0x87},                    // 8B: wati7 应答
            new byte[] {0xAA,0x53,0x7E,0x6B,0x76,0x7F,0xFF,0x87,0x00,0x00},          // 10B
            new byte[] {0xAA,0x53,0x7E,0x6B,0x76,0x7F,0xFF,0x87,0x60,0x83,0xBC,0x4C,0xBE,0x4A,0xBA,0xC0,0x33,0x00}, // 8B+推流连发
            new byte[] {0x60,0x83,0xBC,0x4C,0xBE,0x4A,0xBA,0xC0,0x33,0x00},          // 纯 10B 推流
            new byte[] {0xAA,0x81,0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39,0x30,0x41,0x42,0x00}, // 15B SN 应答形态
        };
        int fi = 0;
        foreach (var fr in frames)
        {
            fi++;
            P("  -- 实验" + fi + " 喂 " + fr.Length + "B: " + BitConverter.ToString(fr).Replace("-", " "));
            try { addBufM.Invoke(com, new object[] { fr, fr.Length }); P("     AddToDataBuffer ok"); }
            catch (Exception e) { P("     AddToDataBuffer EXC " + e.Message); }
            for (int gi = 0; gi < 3; gi++)
            {
                object pack = null;
                try { pack = getUninM.Invoke(com, null); } catch (Exception e) { P("     GetUninPack EXC " + e.Message); break; }
                if (pack == null) { P("     GetUninPack → null"); break; }
                P("     GetUninPack → " + DumpObj(pack));
            }
            dumpBuffer("exp" + fi);
        }
        P("[done]");
        return 0;
    }
}
