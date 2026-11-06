// rxprobe_helper.cs -- CS-Pilot testbed RX probe helper (C# 5 compatible, PS 5.1 Add-Type)
// Wires SerialConnect.OnPackReceive -> BaseContext.PackReceive and instruments the chain.
// Referenced assemblies: System.dll, System.Core.dll, CSStudio6.Connect.dll, CSStudio6.BaseInterface.dll
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using System.Threading;
using CSStudio6.Connect.Base;
using CSStudio6.Connect.Com;

// Captures Console.WriteLine from library internals (e.g. BaseContext.PackReceive's
// "未识别数据包类型：XX" diagnostics) into RxProbe.Log.
public class ConsoleCaptor : System.IO.TextWriter
{
    private StringBuilder sb = new StringBuilder();
    public ConsoleCaptor() { }
    public override Encoding Encoding { get { return Encoding.UTF8; } }
    public override void Write(char value)
    {
        lock (RxProbe.Gate)
        {
            sb.Append(value);
            if (value == '\n')
            {
                string line = sb.ToString().TrimEnd();
                if (line.Length > 0) RxProbe.Log.Add("CONSOLE " + line);
                if (RxProbe.Log.Count > 8000) RxProbe.Log.RemoveRange(0, 2000);
                sb.Clear();
            }
        }
    }
    public override void Write(string value) { foreach (char c in value) this.Write(c); }
    public override void WriteLine(string value) { this.Write(value); this.Write('\n'); }
}

public static class RxProbe
{
    public static readonly List<string> Log = new List<string>();
    public static readonly object Gate = new object();
    public static long RxCount = 0;        // packs delivered to OnPackReceive
    public static long CtxCallCount = 0;   // ctx.PackReceive invoked
    public static long CtxErrCount = 0;    // ctx.PackReceive threw
    public static object BoundCtx = null;
    public static PackReceiveEvent.PackReceive PrevHandler = null;
    private static MethodInfo CtxMethod = null;

    static void Note(string s)
    {
        lock (Gate)
        {
            Log.Add(s);
            if (Log.Count > 6000) Log.RemoveRange(0, 2000);
        }
    }

    public static string Hex(CorrPackage p)
    {
        if (p == null || p.AllData == null) return "<null>";
        StringBuilder sb = new StringBuilder();
        byte[] d = p.AllData;
        for (int i = 0; i < d.Length && i < 48; i++) sb.Append(d[i].ToString("X2")).Append(' ');
        sb.Append("| cmd=").Append(((int)p.Command).ToString("X2")).Append(" len=").Append(p.Length);
        return sb.ToString();
    }

    // OnPackLog fires inside ParsingPack for every RX frame that got parsed (valid or not)
    public static void WireLog(object conn)
    {
        SerialConnect sc = (SerialConnect)conn;
        sc.OnPackLog = delegate(string comName, bool isRev, CorrPackage pack)
        {
            Note("PACKLOG " + comName + (isRev ? " RX " : " TX ") + Hex(pack));
        };
    }

    static void OnRx(CorrPackage pack)
    {
        Interlocked.Increment(ref RxCount);
        object ctx = BoundCtx;
        MethodInfo mi = CtxMethod;
        if (ctx != null && mi != null)
        {
            Interlocked.Increment(ref CtxCallCount);
            try { mi.Invoke(ctx, new object[] { pack }); }
            catch (Exception ex)
            {
                Interlocked.Increment(ref CtxErrCount);
                Exception inn = ex.InnerException;
                Note("CTXERR " + (inn != null ? (inn.GetType().Name + ": " + inn.Message) : ex.Message));
            }
        }
        PackReceiveEvent.PackReceive prev = PrevHandler;
        if (prev != null) { try { prev(pack); } catch (Exception ex) { Note("PREVERR " + ex.Message); } }
    }

    // Bind conn.OnPackReceive = RxProbe.OnRx, forwarding to ctx.PackReceive.
    // Returns "was-null" if nothing was wired before (expected in headless assembly).
    public static string WireReceive(object conn, object ctx)
    {
        SerialConnect sc = (SerialConnect)conn;
        PrevHandler = sc.OnPackReceive;
        BoundCtx = ctx;
        CtxMethod = ctx.GetType().GetMethod("PackReceive");
        sc.OnPackReceive = OnRx;
        return PrevHandler == null ? "was-null" : "was-set(wrapped)";
    }

    public static string UnwireReceive(object conn)
    {
        SerialConnect sc = (SerialConnect)conn;
        BoundCtx = null;
        CtxMethod = null;
        sc.OnPackReceive = PrevHandler;
        return "unwired";
    }

    // Build a synthetic CS-model frame (55 AA LEN_H LEN_L CMD payload SUM) and hand it
    // straight to ctx.PackReceive -- bypasses the serial layer, unit-tests the storage path.
    public static string InjectToCtx(object ctx, byte cmd, byte[] payload)
    {
        int n = (payload == null) ? 0 : payload.Length;
        byte[] frame = new byte[6 + n];
        frame[0] = 0x55; frame[1] = 0xAA;
        frame[2] = (byte)((frame.Length >> 8) & 0xFF);
        frame[3] = (byte)(frame.Length & 0xFF);
        frame[4] = cmd;
        if (n > 0) Array.Copy(payload, 0, frame, 5, n);
        int sum = 0;
        for (int i = 0; i < frame.Length - 1; i++) sum += frame[i];
        frame[frame.Length - 1] = (byte)(sum & 0xFF);
        CorrPackage p = new CorrPackage();
        p.packModel = PackModel.CS;
        p.AllData = frame; // InitPack: Command = AllData[4]
        object target = (BoundCtx != null) ? BoundCtx : ctx;
        MethodInfo mi = target.GetType().GetMethod("PackReceive");
        try
        {
            mi.Invoke(target, new object[] { p });
            return "inject ok " + Hex(p);
        }
        catch (Exception ex)
        {
            Exception inn = ex.InnerException;
            return "inject ERR " + (inn != null ? inn.ToString() : ex.ToString());
        }
    }

    public static string DumpState(object conn, object ctx)
    {
        StringBuilder sb = new StringBuilder();
        try
        {
            Type t = ctx.GetType();
            sb.Append("PointCount=").Append(t.GetProperty("PointCount").GetValue(ctx, null));
            sb.Append(" StartSample=").Append(t.GetProperty("StartSample").GetValue(ctx, null));
            sb.Append(" State=").Append(t.GetProperty("ExpMethodState").GetValue(ctx, null));
            sb.Append(" IsBusy=").Append(t.GetProperty("IsBusy").GetValue(ctx, null));
            sb.Append(" ThisExp=").Append(t.GetProperty("ThisExp").GetValue(ctx, null));
            object di = t.GetProperty("DataItem").GetValue(ctx, null);
            if (di == null) { sb.Append(" DataItem=<null>"); }
            else
            {
                Type dt = di.GetType();
                sb.Append(" DataItem=").Append(dt.Name);
                string[] names = new string[] { "TimeValues", "VolteValues", "CurrentValues", "ChargeValues", "Indexs", "OrigE", "OrigI", "EisDatas" };
                foreach (string pn in names)
                {
                    PropertyInfo pp = dt.GetProperty(pn);
                    if (pp == null) continue;
                    object lst = pp.GetValue(di, null);
                    int c = -1;
                    System.Collections.IEnumerable en = lst as System.Collections.IEnumerable;
                    if (en != null) { c = 0; foreach (object o in en) c++; }
                    sb.Append(' ').Append(pn).Append('=').Append(c);
                }
            }
            SerialConnect sc = conn as SerialConnect;
            if (sc != null) sb.Append(" OnPackReceive=").Append((sc.OnPackReceive != null) ? "SET" : "NULL");
            sb.Append(" rx=").Append(Interlocked.Read(ref RxCount));
            sb.Append(" ctxCall=").Append(Interlocked.Read(ref CtxCallCount));
            sb.Append(" ctxErr=").Append(Interlocked.Read(ref CtxErrCount));
        }
        catch (Exception ex) { sb.Append(" DUMPERR ").Append(ex.Message); }
        return sb.ToString();
    }

    public static string Tail(int n)
    {
        lock (Gate)
        {
            int start = Math.Max(0, Log.Count - n);
            StringBuilder sb = new StringBuilder();
            for (int i = start; i < Log.Count; i++) sb.AppendLine(Log[i]);
            return sb.ToString();
        }
    }

    // Route Console.WriteLine into RxProbe.Log (keeps previous writer as mirror target).
    public static void CaptureConsole()
    {
        Console.SetOut(new ConsoleCaptor());
    }

    // Direct storage unit test through the IDataItem interface (MAdd may be an
    // explicit interface implementation, invisible to public-only reflection).
    public static string DirectMAdd(object ctx, ulong idx, double t, double e, double i, double c)
    {
        try
        {
            object diProp = ctx.GetType().GetProperty("DataItem").GetValue(ctx, null);
            if (diProp == null) return "DataItem=<null>";
            CSStudio6.BaseInterface.Datas.IDataItem di = diProp as CSStudio6.BaseInterface.Datas.IDataItem;
            if (di == null) return "DataItem not IDataItem: " + diProp.GetType().FullName;
            di.Add(idx, t, e, i, c);
            return "Add ok";
        }
        catch (Exception ex)
        {
            Exception inn = ex.InnerException;
            return "MAdd ERR " + (inn != null ? inn.ToString() : ex.ToString());
        }
    }

    // Read the head pack of the RX queue without consuming? Not exposed -- instead
    // expose ClearData(false) semantics (drop queued packs) through BaseConnect.
    public static string ClearQueue(object conn)
    {
        try
        {
            conn.GetType().GetMethod("ClearData", new Type[] { typeof(bool) }).Invoke(conn, new object[] { false });
            return "ClearData(false) ok";
        }
        catch (Exception ex) { return "ClearData ERR " + ex.Message; }
    }

    // Counter snapshot string (for before/after diffing an injection).
    public static string GetCounters()
    {
        return "rx=" + Interlocked.Read(ref RxCount) + " ctxCall=" + Interlocked.Read(ref CtxCallCount);
    }

    // Drain console lines captured since last drain (so nothing is lost between phases).
    public static string DrainConsole()
    {
        lock (Gate)
        {
            StringBuilder sb = new StringBuilder();
            for (int i = Log.Count - 1; i >= 0; i--)
            {
                if (Log[i].StartsWith("CONSOLE "))
                {
                    sb.Insert(0, Log[i] + " ;; ");
                    Log.RemoveAt(i);
                    if (sb.Length > 1500) break;
                }
            }
            return sb.ToString();
        }
    }
}
