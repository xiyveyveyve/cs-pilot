# CS5 Pilot — CS Studio 5 的跨平台替代上位机

针对 **武汉科思特 CS350** 电化学工作站的纯 Python 重写，目标是让实验能在
**Linux 与 Android** 上跑，不再依赖 Windows 上的 `CorrTest.CSStudio.exe`。

第一期覆盖：**恒电流极化（GalStatic）**。

## 为什么能重写

CS Studio 5 的通讯协议极其简单：16 字节定长帧 + 累加和，无 CRC、无加密握手。
实验逻辑（参数类、帧构造）位于 `CorrTest.CorrData.dll`，**未加壳、可完整反编译**；
只有底层通讯（`CorrTest.CorrCom.dll`、`CorrTest.CorrModules.dll`）被 ConfuserEx
式壳保护——但可以**在 .NET Framework 宿主里反射调用**这些方法直接取到答案。

本项目所有协议常量均来自这两条路径，不止是猜的。详见 [`docs/protocol.md`](docs/protocol.md)。

## 目录

```
cs5/            协议栈（无第三方依赖）
  frame.py      16B 帧构造与校验
  da.py         电压 -> 16 位 DAC
  galstatic.py  恒电流极化参数与指令帧
  protocol.py   固定命令帧、连接/启停序列
  session.py    设备会话
  datalog.py    CORRW ASCII（.cor）读写
  transport.py  串口 / TCP / 回环
sim/device.py   设备模拟器（无硬件自测）
gui/app.py      Kivy 界面（桌面 + Android）
tools/          自测、CLI
data/da_map.csv 厂商量化函数实测采样表（4001 点）
```

## 用法

### 1. 自测（无需硬件）

```bash
python tools/selftest.py
```

覆盖：固定帧校验和、4001 点 DA 量化对照、恒电流帧生成、数据帧解析、
模拟器端到端采集与 .cor 往返。

### 2. 看要发什么帧

```bash
python tools/run_galstatic.py --curr 0.2 --unit mA --time 200 --dry-run
```

### 3. 连真机

```bash
python tools/run_galstatic.py --port COM10 --curr 0.2 --unit mA --time 200
# Linux
python tools/run_galstatic.py --port /dev/ttyUSB0 --curr 0.2
# 串口服务器
python tools/run_galstatic.py --port TCP:192.168.1.50:4001
```

### 4. 图形界面

```bash
pip install -r requirements.txt
python gui/app.py
```

### 5. Android

```bash
pip install buildozer
buildozer android debug
```

Android 上的串口需要 USB-OTG：Kivy 侧把 `SerialTransport` 换成基于
`usb4a` + `pyserial` 的实现（或用串口转 WiFi，直接走 `TcpTransport`）。

## 硬件事实

- CS350 无网口，原厂走 USB 转串口（CH340/CP2102/CHIYU），波特率默认 9600
- 恒电流极化固定手动电流量程 3（1 kΩ 跨阻）：`DA 电压 = 电流(A) × 1000`
- 0.2 mA → 0.2 V DA 输出，与厂商 `SingleToUint16BigBytes(0.2) = 82 8F` 完全吻合

## 尚未验证

协议里有一处仍未在真机上确认：`AA 53` 读 OCP 应答中 24 位电位的符号约定。
模拟器与上位机两端目前使用对称映射 `raw/16777215*20-10`。
首次真机对接时请先用万用表或原软件读数对照一次。

## 安全边界

本项目只读分析原程序，不修改 `D:\sci\CS Studio5` 下任何文件、不连接正在被
原软件占用的串口。真机测试请在原软件停止后进行。