# -*- coding: utf-8 -*-
r"""build_frames_c.py —— 从 simdevice JSONL 日志生成三实验下发帧结构表（Agent C 交付物）。

用法:
    python testbed/build_frames_c.py

输入: D:\deepseek\_probe\testbed_simC.jsonl  (simdevice.py live @ CNCB1 的帧日志)
输出: testbed/frames_tafel.txt / frames_eis.txt / frames_step.txt

每个输出文件:
  * === RAW === 段: 机读格式 `cmdname<TAB>LEN<TAB>hex`(空格分隔 hex, 含 SUM, LEN=整帧字节数)。
  * === 解码 === 段: 逐字段注释(偏移/类型/含义/实测值), 值直接从字节解出, 与 hex 自洽。

运行窗口按绝对时间戳( epoch 秒, 与 JSONL ts 同源 )切分, 见 RUNS 表。
"""
import json
import struct
import sys
import os

JSONL = r"D:\deepseek\_probe\testbed_simC.jsonl"
OUTDIR = os.path.dirname(os.path.abspath(__file__))

# (label, t_start, t_end) —— 各探针运行的帧窗口(Agent C 2026-11-07 实测切分)
RUNS = {
    "tafel_primary":  ("Tafel 主捕获 (InitE=-0.05 FinalE=+0.05 ScanRate=0.5mV/s Frq=1.0 OcpValue=0)",
                       1793983297.0, 1793983307.0),
    "tafel_mid":      ("Tafel 中点变体 (MidEOneEnable=true MidEOne=+0.1 MidETwoEnable=true MidETwo=+0.2)",
                       1793983726.0, 1793983736.0),
    "tafel_defaults": ("Tafel 默认参数对照 (对象全新默认: InitE=-0.1 FinalE=+0.1 ScanRate=0.5, Frq getter=2.0 未被 GUI 规则改写)",
                       1793982686.9, 1793982695.5),
    "eis_primary":    ("EIS 主捕获 (SineAmp=10mV Init_Fre=1000Hz Final_Fre=0.1Hz TenTwice=10, SendMethodBytes)",
                       1793983370.0, 1793983378.5),
    "eis_eissetup":   ("EIS SendEisSetup 路径对照 (同一参数对象, send.SendEisSetup(prm,false))",
                       1793983599.9, 1793983608.0),
    "eis_var":        ("EIS 差分变体 (SineBias=0.25 TenTwice=20 Integral_Time=77 Integral_Period=78 DelayTime=88 "
                       "PrePolTime=66 MeasurementSpeedMode=3 TestPoints=123 Mode=2 ParamsType=1 ADS_EN=1 "
                       "ADS_Fre=1234 Filter_Fre=99 AttenualSet=4)",
                       1793983735.2, 1793983743.4),
    "eis_var2":       ("EIS 单变量差分 (仅 IsAutoDelayTime=false)",
                       1793984064.8, 1793984074.0),
    "step_primary":   ("阶梯波主捕获 (Initial_E=+0.01 Final_E=-0.01 InitialTime=2 FinalTime=100 Cycles=20 TimeUnit=1(默认) OcpValue=0)",
                       1793983473.6, 1793983482.0),
    "step_step1":     ("阶梯波 Step1 变体 (Step1Enable=true Step1=+0.03 Time1=50)",
                       1793983572.9, 1793983581.5),
}

NAME_OVERRIDES = {0x70: "EisSetup?"}


def f32(b, off):
    return struct.unpack("<f", b[off:off + 4])[0]


def i32(b, off):
    return struct.unpack("<i", b[off:off + 4])[0]


def u16le(b, off):
    return struct.unpack("<H", b[off:off + 2])[0]


def u16be(b, off):
    return (b[off] << 8) | b[off + 1]


def g(cmd, name):
    return NAME_OVERRIDES.get(cmd, name)


def hexs(b):
    return b.hex(" ").upper()


def dec_0x45(data):
    return [
        "  DATA[0..1] u16BE = %d  (全部实验恒定; 语义待定, 疑似输出/量程索引 100)" % u16be(data, 0),
        "  DATA[2..4] = %s  (恒 0)" % hexs(data[2:5]),
    ]


def dec_0x40(data):
    return [
        "  DATA(%dB) = %s" % (len(data), hexs(data)),
        "  语义未定(扫描参数/设备配置); 各实验间存在少量字节差异(DevParam 差异), 逐字节自行比对。",
    ]


def dec_0x54(data):
    v = [f32(data, k) for k in range(0, 28, 4)]
    return [
        "  f32[0] @+0  = %g        <- 电量程满量程 V (两处实测均 5.0; 与 DevParam VoltRange=2.5V 的关系待定)" % v[0],
        "  f32[1] @+4  = %+.6f  <- InitE+OCP   (vsOCP 模式加 OcpValue 偏移; 本捕 OcpValue=0)" % v[1],
        "  f32[2] @+8  = %+.6f  <- Mid1+OCP    (MidEOneEnable=false 时填 InitE; 启用时=MidEOne+OCP, 见变体)" % v[2],
        "  f32[3] @+12 = %+.6f  <- Mid2+OCP    (同上, 启用时=MidETwo+OCP)" % v[3],
        "  f32[4] @+16 = %+.6f  <- FinalE+OCP" % v[4],
        "  f32[5] @+20 = %.8g  <- ScanRate V/s (对象 ScanRate 为 mV/s, 此处 /1000)" % v[5],
        "  f32[6] @+24 = %g        <- Frq = 参数对象 get_Frq() 原值 (GUI 规则=mV/s*2; 对象内 IsFrq=true->SampleFrq*BaseFreqRate, "
        "IsFrq=false->BaseFreqRate/SampleInter; 无公共 setter, InitByString 显式拒绝 Frq)" % v[6],
    ]


def dec_0x41(data):
    return [
        "  [0]      u8  = 0x%02X        <- 常量(本捕恒 01)" % data[0],
        "  [1..4]   4B  = %s  <- 常量 FF FF FF FF (int -1)" % hexs(data[1:5]),
        "  [5..8]   f32 = %g      <- Init_Fre 起始频率 Hz" % f32(data, 5),
        "  [9..12]  f32 = %g       <- SineAmp 幅值 mV" % f32(data, 9),
        "  [13..16] 4B  = %s  <- 常量(FF FF FF 01)" % hexs(data[13:17]),
        "  [17..20] i32 = %d        <- Integral_Time (默认 1; 差分实测 77)" % i32(data, 17),
        "  [21..24] i32 = %d        <- Integral_Period (默认 1; 差分实测 78)" % i32(data, 21),
        "  [25]     u8  = %d        <- 延迟模式标志 (IsAutoDelayTime=true->0, false->1; 单变量差分实测)" % data[25],
        "  [26..27] u16LE = %d      <- DelayTime (默认 500; 差分实测 88)" % u16le(data, 26),
        "  [28..38] 11B = %s <- 全 0 常量" % hexs(data[28:39]),
        "  注: TestPoints/Mode/ParamsType/ADS_EN/ADS_Fre/Filter_Fre/AttenualSet/SineBias/TenTwice/ "
        "Range_*/Filter_*/DevGain 差分均未出现在本帧。",
    ]


def dec_0x70(data):
    return [
        "  [0..3]   f32 = %g      <- Init_Fre 起始频率 Hz (与 0x41 重复出现)" % f32(data, 0),
        "  [4..7]   f32 = %g       <- Final_Fre 终止频率 Hz" % f32(data, 4),
        "  [8..11]  f32 = %g     <- SineBias 直流偏置 V (默认 0; 差分实测 0.25)" % f32(data, 8),
        "  [12..15] f32 = %g     <- 常量 0.01 (TenTwice 10->20 不变; 语义待定)" % f32(data, 12),
        "  [16..19] f32 = %g      <- 4*TenTwice (10->40.0, 20->80.0; 换算关系待定)" % f32(data, 16),
        "  [20..23] i32 = %d        <- PrePolTime (默认 0; 差分实测 66)" % i32(data, 20),
        "  [24]     u8  = %d        <- MeasurementSpeedMode (默认 0; 差分实测 3)" % data[24],
    ]


def dec_0x56(data):
    o = []
    o.append("  f32[0] @+0   = %g      <- 电量程满量程 V" % f32(data, 0))
    o.append("  f32[1] @+4   = %+.6f  <- Initial_E+OCP" % f32(data, 4))
    o.append("  f32[2] @+8   = %.6f  <- InitialTime 秒 (对象值*0.001: TimeUnit=1 即 ms, 2.0ms->0.002s —— ms 陷阱实测确认)" % f32(data, 8))
    for k in range(10):
        off = 12 + 8 * k
        o.append("  f32[%d] @+%-3d = %+.6f  <- Step%d+OCP (未启用也发对象当前值)" % (3 + 2 * k, off, f32(data, off), k + 1))
        o.append("  f32[%d] @+%-3d = %.6f  <- Time%d 秒 (未启用=0.0; 启用后=对象 ms 值*0.001, 50ms->0.05)" % (4 + 2 * k, off + 4, f32(data, off + 4), k + 1))
    o.append("  f32[23] @+92  = %+.6f  <- Final_E+OCP" % f32(data, 92))
    o.append("  f32[24] @+96  = %.6f  <- FinalTime 秒 (100ms->0.1, 同 ms 陷阱)" % f32(data, 96))
    o.append("  [100..103] i32 = %d      <- Cycles 循环数 (整型 LE, 不是 float!)" % i32(data, 100))
    o.append("  f32[26] @+104 = %g    <- Frq = get_Frq() (默认 SampleFrq*BaseFreqRate=100)" % f32(data, 104))
    return o


def dec_simple(data):
    if not data:
        return ["  (无载荷)"]
    return ["  DATA(%dB) = %s" % (len(data), hexs(data))]


DECODERS = {
    0x45: dec_0x45, 0x40: dec_0x40, 0x54: dec_0x54,
    0x41: dec_0x41, 0x70: dec_0x70, 0x56: dec_0x56,
}


def load_runs():
    recs = []
    with open(JSONL, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    out = {}
    for key, (label, t0, t1) in RUNS.items():
        out[key] = [r for r in recs if t0 <= r["ts"] <= t1 and r["dir"] in ("rx", "tx")]
    return out


HEADER = {
    "tafel": """# frames_tafel.txt —— Tafel(动电位) SendMethodBytes 下发帧捕获与逐字段解码
# 捕获: 2026-11-07, .NET CSStudio6 协议栈 -> COM91(CNCA1) -> simdevice.py live @ CNCB1 (rx=主机TX)
# 探针: testbed/probe_send3.ps1 -Exp tafel   参数类: CSStudio6.CorrData.MethodParams.PotDynamicParams
# 配方: LoadFrom DLL -> SerialConnect.Open("COM91") -> CheckPackReceiveThread -> new BaseContext ->
#       SetConnect -> ctx.ThisExp=ID_PotDynamic(枚举按名) -> ctx.BaseParam=<prm> -> prm.baseContext=ctx ->
#       new ExpComSendClass(ctx) -> ctx.set_ExpComSend(send) -> send.SendMethodBytes(prm) -> True
# 帧格式: 55 AA | LEN_H LEN_L | CMD | DATA | SUM, LEN=整帧字节数, SUM=前 LEN-1 字节累加和
""",
    "eis": """# frames_eis.txt —— EIS(频率扫描-电位控制) SendMethodBytes 下发帧捕获与逐字段解码
# 捕获: 2026-11-07, .NET CSStudio6 协议栈 -> COM91(CNCA1) -> simdevice.py live @ CNCB1 (rx=主机TX)
# 探针: testbed/probe_send3.ps1 -Exp eis   参数类: CSStudio6.CorrData.MethodParams.EISVSfrqParams
# 关键: EIS 走 SendMethodBytes 完整 4 帧下载(0x45+0x40+0x41+0x70), 前提 ctx.BaseParam 必须挂参数对象
#       (否则 EISVSfrqParams.SendMethodParams() 内部 NullRef); send.SendEisSetup(prm,false) 只发 0x41 单帧,
#       是运行中重配路径, 不是主下载路径。
# 命令 0x41=ScanStart, 0x70=新命令(simdevice 未收录, 被回 NAck)。
""",
    "step": """# frames_step.txt —— 任意恒电位阶梯波(PotSquare) SendMethodBytes 下发帧捕获与逐字段解码
# 捕获: 2026-11-07, .NET CSStudio6 协议栈 -> COM91(CNCA1) -> simdevice.py live @ CNCB1 (rx=主机TX)
# 探针: testbed/probe_send3.ps1 -Exp step   参数类: CSStudio6.CorrData.MethodParams.PotSquareParams
# 关键: 方法帧命令 = 0x56 (新命令, simdevice 未收录, 被回 NAck; 但 SendMethodBytes 仍返回 True —— 发送不等待应答)。
#       ms 陷阱实测确认: TimeUnit=1 时对象里的 ms 值在帧里一律 *0.001 变秒。
""",
}


def render(exp, keys):
    lines = [HEADER[exp]]
    for key in keys:
        label, _t0, _t1 = RUNS[key]
        recs = RUN_DATA[key]
        lines.append("")
        lines.append("=" * 76)
        lines.append("== RUN: " + label)
        lines.append("=" * 76)
        lines.append("--- RAW (machine: cmdname<TAB>LEN<TAB>hex) ---")
        for r in recs:
            if r["dir"] == "rx":
                nm = r.get("cmd_name") or r.get("name") or ("0x%02X" % r["cmd"])
                lines.append("%s\t%d\t%s" % (g(r["cmd"], nm), r["len"], r["hex"]))
        lines.append("--- 解码 ---")
        seq = 0
        for r in recs:
            if r["dir"] != "rx":
                continue
            seq += 1
            data = bytes.fromhex(r["hex"].replace(" ", ""))
            payload = data[5:-1]
            nm = r.get("cmd_name") or r.get("name") or ("0x%02X" % r["cmd"])
            lines.append("#%d %s (0x%02X) LEN=%d" % (seq, g(r["cmd"], nm), r["cmd"], r["len"]))
            dec = DECODERS.get(r["cmd"], dec_simple)(payload)
            lines.extend(dec)
            if r["cmd"] == 0x54:
                lines.append("  对照: 00 文档 3.5 真机样本 55 AA 00 22 54 00 00 A0 40 46 F8 9B BE*3 10 37 65 3F DA 03 AD 39 C3 F5 28 3F E7")
                lines.append("        -> 布局逐字段吻合(range/InitE+OCP/Mid1/Mid2/FinalE/Rate/Frq); 本捕 OcpValue=0 故电位无偏移。")
            if r["cmd"] == 0x70:
                lines.append("  对照: 无已知文档样本 —— 新发现命令帧(此前仅 0x45/0x40/0x51/0x54 有样本)。")
            if r["cmd"] == 0x56:
                lines.append("  对照: 无已知文档样本 —— 新发现命令帧。")
        lines.append("")
    lines.append("# ---- 汇总 ----")
    return lines


RUN_DATA = load_runs()

files = [
    ("frames_tafel.txt", "tafel", ["tafel_primary", "tafel_mid", "tafel_defaults"]),
    ("frames_eis.txt", "eis", ["eis_primary", "eis_eissetup", "eis_var", "eis_var2"]),
    ("frames_step.txt", "step", ["step_primary", "step_step1"]),
]
SUMMARY = {
    "tafel": [
        "# 1) Tafel 方法帧 = 0x54 CSPotDynamic, LEN=34, DATA=28B=7xf32:",
        "#    [量程5.0][InitE+OCP][Mid1+OCP][Mid2+OCP][FinalE+OCP][ScanRate V/s][Frq]",
        "# 2) 与 00 文档 3.5 真机样本逐字段吻合; Mid 槽未启用填 InitE, 启用填 MidEOne/MidETwo(变体实测)。",
        "# 3) Frq 是参数对象 get_Frq() 的原值拷贝: GUI 规则 mV/s*2, 对象内部 IsFrq=true->SampleFrq*BaseFreqRate /",
        "#    IsFrq=false->BaseFreqRate/SampleInter; 无公共 setter(InitByString 报'未实现 Set 过程')。",
        "# 4) SendMethodBytes 前置固定发 0x45 CSOutput(5B: u16BE=100+3零) + 0x40 DevSetup(32B, DATA=26B)。",
        "# 5) 序列: 0x45 -> 0x40 -> 0x54 -> (SysStart)0x30 -> (SysStop)0x32。",
    ],
    "eis": [
        "# 1) EIS 主下载 = SendMethodBytes 发 4 帧: 0x45 + 0x40 + 0x41 ScanStart(45B) + 0x70(31B, 新命令)。",
        "#    前提: ctx.BaseParam 必须指向参数对象, 否则 EISVSfrqParams.SendMethodParams() NullRef(实测复现)。",
        "# 2) send.SendEisSetup(prm,false) 单独调用只发 0x41 一帧(True), 不发 0x45/0x40/0x70 —— 不是主下载路径。",
        "# 3) 0x41 DATA=39B: [01][FFFFFFFF][Init_Fre f32][SineAmp f32][FFFFFF01][Integral_Time i32]",
        "#    [Integral_Period i32][延迟标志 u8][DelayTime u16LE][11B 零]。",
        "# 4) 0x70 DATA=25B: [Init_Fre f32][Final_Fre f32][SineBias f32][常量0.01][4*TenTwice f32]",
        "#    [PrePolTime i32][MeasurementSpeedMode u8]。",
        "# 5) 未出现在两帧中的 EIS 字段: TestPoints/Mode/ParamsType/ADS_EN/ADS_Fre/Filter_Fre/AttenualSet/",
        "#    Range_*/Filter_*/DevGain —— 本版本(CS350M, 非360)对这两帧无贡献, 待真机核对。",
    ],
    "step": [
        "# 1) 阶梯波方法帧 = 0x56 (新命令), LEN=114, DATA=108B=26xf32+1xi32:",
        "#    [量程][Initial_E+OCP][InitialTime 秒][(Step_k+OCP)(Time_k 秒) x10][Final_E+OCP][FinalTime 秒][Cycles i32][Frq]",
        "# 2) ms 陷阱实测确认: TimeUnit=1 时对象 ms 值一律 *0.001 成秒落帧 (2ms->0.002, 50ms->0.05, 100ms->0.1)。",
        "# 3) Cycles 编码为 int32 LE(偏移 DATA+100), 不是 float; 未启用的 Step_k 仍发对象当前值, Time_k=0。",
        "# 4) 模拟器对 0x56 回 NAck(未知命令)不影响发送结果(SendMethodBytes 仍 True —— 发送不等待应答)。",
    ],
}
for fname, exp, keys in files:
    lines = render(exp, keys)
    lines.extend(SUMMARY[exp])
    path = os.path.join(OUTDIR, fname)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    print("WROTE", path, len(lines), "lines")
