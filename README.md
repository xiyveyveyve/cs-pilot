# CS Pilot · 纯代码路线（`pure-code` 分支）

本分支为 `cs-pilot` 仓库的 **`pure-code`** 分支，聚焦不依赖软件界面的无头控制、协议逆向、模拟器测试床与真机工具脚本；GUI 寄生式自动化（UIA 多机编排）位于 **`gui`** 分支。

## 目录结构

| 目录 | 说明 |
|---|---|
| `code/` | C# 无头宿主（`cshost/CsPilotHost.cs`、`cs6ui/CsPilotUi6.cs`）、Python 编排与判稳策略（`pilot.py`、`policies.py`、`viewer.py`）、CS6/CS5 模拟器（`sim/`、`cs5/`） |
| `docs/` | 方案与阶段结论文档（`01_纯代码路线_方案.md`、`02_CS5阶段结论.md`、`03_恒电流族扩展.md`） |
| `tests/` | 回归测试（`run_all.py`、`run_case.py`、`test_gal_frames.py`、`test_policies.py`）、golden 帧（`golden/`）、作业配置（`jobs/`）及 C# 探针源码（`probe/`） |
| `tools/` | 真机实验启动、在线监视、手机推送通知与摄像头抓拍脚本 |
| `cs5-pilot/` | 脱离 Windows/.NET DLL 的纯 Python + Kivy 跨平台 CS Studio 5 协议栈与上位机（同步自 `D:\deepseek\CS5Pilot`） |
| `logs/` | 保留核心过程与计划文档：`PROGRESS.md`、`巡检记录.md`、`OVERNIGHT_PLAN.md` |

## 忽略说明

以下本地产物与敏感配置已通过 `.gitignore` 排除，不入版本库：
- `.exe` / `.dll` / `.pdb` / `__pycache__/` / `*.pyc` 编译与缓存产物
- `tmp_*.py` 临时探针脚本、`events.jsonl`、`io_ocp`
- `data/` 实验与仿真数据、`cs5-pilot/out/` 输出目录
- `logs/` 下的运行日志与临时输出（仅保留上述 3 份 `.md` 记录）
- `tools/notify.json` 个人推送配置（请按 `tools/notify.py` 头部说明自行创建）

## 常用复现命令

```bash
# 纯代码线全套离线回归（需先按环境编译 CsPilotHost.exe / CsPilotUi6.exe）
python tests/run_all.py
python tests/test_gal_frames.py

# CS5 纯 Python 协议栈离线自测（无需硬件与 .NET）
python cs5-pilot/tools/selftest.py
```
