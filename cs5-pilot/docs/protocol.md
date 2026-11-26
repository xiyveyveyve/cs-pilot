# CS Studio 5 / CS350 通信协议（逆向结论）

面向 `CorrTest.CSStudio.exe` v5.6.1202.2（武汉科思特 CS350 电化学工作站）。
所有结论来自静态反编译（CorrData 层明文）+ 反射调用壳内方法实测（见 `_re/probe/`）。

## 1. 帧格式

16 字节定长：

```
AA | cmd | data[13] | SUM
 0    1      2..14     15
SUM = (sum(frame[0..14])) & 0xFF
```

- 字节序：**大端**（u16 高字节在前）
- 末尾 SUM 简单累加和，无 CRC

## 2. 固定命令帧

| 名称 | 字节 |
| --- | --- |
| Boot/握手 D0 | `AA D0 00×13 7A` |
| 版本 Version | `AA 88 00×13 32` |
| 序列号 Serial | `AA 81 00×13 2B` |
| 读 OCP | `AA 53 01 00×13 FE` |
| 启动 Start | `AA 80 51 00×13 7B` |
| 暂停 Pause | `AA 80 52 00×13 7C` |
| 停止 Stop | `AA 80 53 00×13 7D` |
| 反向 Reverse | `AA 6F FF 00×13 18` |

## 3. IO 帧（写 IO 配置）

`CommandPackage.GetIOBytes(byte[])` 实测输出：

```
AA 85 | ioBytes[0..2] | 00×11 | SUM
```

`ioBytes` 是 3 字节位域（`BaseIOClass`）：

| 字节 | 位 | 含义 |
| --- | --- | --- |
| [0] | bit0-2 | 电流量程 currRange（0..7） |
| [0] | bit4 | P_G |
| [0] | bit5-7 | 系统带宽 SYS_BAND（0..7） |
| [1] | bit0-1 | 电压量程 voltRange（0..2） |
| [1] | bit2-3 | 可选衰减 optAttenual |
| [2] | bit0 | 电流量程高位（>8 档设备才用） |

实测：`{0x90,0x02,0x00}` → `AA 85 90 02 00 00…00 C1`

`SetSysBand(4)` → `[0] = (io&~0xE0) | (4<<5)` = 0x90
`SetVoltRange(2)` → `[1] = 0x02`
`SetCurrRange(3)` → `[0] = 0x93`

**恒电流极化实际发送的 IO 帧 = `AA 85 93 02 00 00×10 C4`**

## 4. 单点 DA 输出（恒电流极化的核心）

`GalStaticParams.SendDASinglePointOut(114, 0, volt)`：

```
AA 72 00 | u16BE(dac) | 00×10 | SUM
```

`dac = SingleToUint16BigBytes(volt * DAOutSetting)`，`DAOutSetting` 默认 1.0。

量化实测（反射调用，4001 点采样，`_re/probe/da_map.csv`）：

```
dac = round((volt + 10.0) / 20.0 * 65535)
volt ∈ [-10, +10] → dac ∈ [0, 65535]
```

误差 ≤1 LSB（20 V / 65536 = 0.305 mV），工程上可忽略。
超范围返回 `0xFFFF` 并打印「当前电流值错误」。

## 5. 恒电流极化的电流→电压换算

`CurrentToVoltage.CurrToVolt(context, current_A, currRange)` 实测：

```
volt = current_A * 10^currRange
```

实测样本：`CurrToVolt(0.0002, r=0)=0.0002`、`r=3 → 0.2`、`r=7 → 2000`。

CS350 恒电流极化固定 `ManualCurRange = 3`（1 kΩ 跨阻），因此：

```
volt = (porCurr / 10^(currUnit*3)) * 1000
```

- `currUnit`：0=A、1=mA、2=μA、3=nA、4=pA
- 例：0.2 mA → 0.0002 A → **0.2 V**

## 6. GalStatic 参数默认值（`GalStaticParams`）

| 字段 | 默认 |
| --- | --- |
| porCurr | 0.2 (mA) |
| currUnit | 1 |
| testTime | 200 (s) |
| timeUnit | 0 (s) |
| useStopEvent | true |
| lessVolt / moreVolt | -2.0 / 2.0 |
| lessCharge / moreCharge | -2.0 / 2.0 |
| stopVsOcp | VsType.vsRef |
| AxisType | EvsTime |
| SampleFrq | 5 Hz |
| BaseIO | {0x90, 0x02, 0x00} |

## 7. 数据帧（设备→上位机）

10 字节，无帧头标记，**小端**：

```
60 | E(f32 LE) | I(f32 LE) | seq
```

实测样本 `60 F3 50 0E BE 00 00 D6 38 00`：

- E = float32 LE `BE 0E 50 F3` = −0.1390 V
- I = float32 LE `00 00 D6 38` = 1.02e-4 A
- seq = 0

判帧条件：首字节 0x60，长度 10。

## 8. OCP 应答帧

`AA 53 01` 的应答：

```
AA 53 | volt(3B) | curr(2B) | 00… | SUM
```

volt 24 位编码二选一（未证实）：
`(raw24 − 2^23) / 2^23 * 10` 或 `(2^23 − raw24) / 2^23 * 9.8`

## 9. 连接建立（S1–S7 已用模拟器验证）

```
AA D0 ×2 → AA D1 ×3 → AA 8B ×3
（8B 不应答则进演示模式）

启动：AA 80 53 ×3 → AA 81 ×3 → AA 53 01（OCP 轮询）
```

心跳：`AA CF 00 … 79`（软件日志 `Buffer-*.txt` 里只有它）

## 10. .cor 数据文件（CORRW ASCII）

```
CORRW ASCII
CorrTest for Windows: SN <sn> V<ver> V<boot>
ID_GalStatic
Data: <date>
Time: <time>
The polarization current(mA):0.2,Hold time(s):200,Frq(Hz):5
Open Circuit Potential (V): <ocp>
<temperature line>
Begin Information
…
End Information
E(V)	i(A/cm^2)	T(s)
<rows>
End Comments
```

## 11. 未证实项

- `AA 53` OCP 应答的 volt 24 位编码符号约定
- `AA 85` 之后设备是否回显
- 数据帧 seq 的语义（是否丢帧检测）
- 停止后设备是否自动回零/退极化