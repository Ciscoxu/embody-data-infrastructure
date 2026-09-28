# Human-Collected Embodied Data Infrastructure

面向人类采集具身数据的本地处理基础设施。当前建设范围是 Phase 0 工程基础和
Phase 1 Data Processing Foundation，主要处理 MEgo/第一视角穿戴设备与遥操作系统
产生的多模态原始数据。

当前不包含云存储、云端任务调度、模型训练、稳定客户 Schema 或商业交付。

## 核心原则

- Raw 数据是不可变 source of truth，任何产物都写入新的输出目录。
- 来源格式、采集模式和处理用途是三个独立分类维度。
- 所有时间序列保留原始 timestamp、clock domain 和 reference timeline 映射。
- pose、轨迹和空间变换保留单位、坐标系、方向与 calibration identity。
- 人体或采集设备轨迹不会被静默标记为机器人动作。
- 未知的 consent、privacy、license、frame 或 clock 信息保持 `unknown`。
- 所有阶段输出结构化 status、QC 和 provenance，而不只依赖日志。

## 本地 Pipeline

Phase 1 本地 Pipeline 分为四层：

```text
不可变 Raw
  -> 第 1 层：来源发现与分类
  -> 第 2 层：来源适配与解码
  -> 第 3 层：通用语义处理核心
  -> 第 4 层：用途策略与本地产物
```

第 1 层输出 source inventory、profile decision、collection-mode evidence、checksum、
schema、topic、clock 和 rights metadata。专用 inspector 通过内容签名注册和分发；普通
文件或目录仍可生成 inventory，但没有匹配 inspector 时不能进入完整 processing。

第 2 层通过 `(container, encoding, source_profile)` adapter registry 选择 decoder。
Protobuf 只是 GenRobot MCAP adapter 的实现细节，不是所有来源的必经步骤。

当前只注册了一个 MCAP inspector、一个 GenRobot RealOmin source profile 和一个对应
decoder adapter。这是当前 MVP 的实现范围，不是顶层 Pipeline 的固定类型约束：
`processing.py` 从 inspection/profile decision 获取 container、encoding、collection mode
和轨迹语义，不直接写死 GenRobot 或 MCAP。

第 3 层完成 vendor-neutral representation、时间映射、calibration、episode、source
QC、semantic QC 和 validity masks。下游 reader 不需要导入 MCAP 或厂商 decoder。

第 4 层读取 processed dataset，生成互不覆盖的本地 purpose run。目前实现：

- `archival`：完整文件 inventory、大小和 SHA-256。
- `exploration`：preview index、下采样记录和数值摘要。

`learning_readiness`、`retargeting` 和 `control_evaluation` 当前只保留明确接口，调用时
返回结构化 `purpose_unsupported`，不会提前执行训练、IK 或机器人控制。

详细设计见 [本地 Pipeline 四层分类设计](docs/local_pipeline_four_layers.md)。

## 当前数据源：GenRobot RealOmin

首个且当前唯一的完整处理 adapter 是 `genrobot_realomin_mcap`，对应 Hugging Face gated dataset
`genrobot2025/10Kh-RealOmin-OpenData`。

当前支持的主要流包括：

- 左右 camera0 H.264；
- IMU；
- magnetic encoder / gripper opening；
- VIO EEF/device pose；
- camera calibration（来源 recording 存在时）。

Gen DAS 是人操作的双手采集设备，因此当前 profile 明确声明：

```text
collection_mode = human_wearable
eef_pose        = observed_device_pose
magnetic_encoder = observed_human_motion
robot action    = not_emitted
```

`robot0`、`robot1`、`eef_pose` 或厂商 H5 中名为 `action` 的字段都不能单独证明存在
机器人 commanded/executed action。

数据集为 gated dataset。下载前需要在
[数据集页面](https://huggingface.co/datasets/genrobot2025/10Kh-RealOmin-OpenData)
接受访问条件，并通过 `hf auth login` 或标准 `HF_TOKEN` 环境变量认证。不要把 token
写进配置、日志或 manifest。

## 环境安装

要求 Python 3.11 或更高版本。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

如需验证 H.264 是否可解码，再安装 video extra：

```powershell
python -m pip install -e ".[dev,video]"
```

安装后可以使用 `embody-data`，也可以直接运行：

```powershell
python -m embody_data --help
```

## 运行方式

### 1. 查看远程样本

只列出路径和大小，不下载 payload：

```powershell
embody-data source-list --limit 20
embody-data source-list --path-prefix "Clutter Tidy-Up [Stage2]/00001" --limit 20
```

### 2. 预演和下载 Raw

先执行 bounded dry-run：

```powershell
embody-data acquire `
  --output data/raw/genrobot-realomin `
  --dry-run `
  --max-files 3 `
  --max-bytes 2147483648
```

确认选择后下载；默认支持 resume：

```powershell
embody-data acquire `
  --output data/raw/genrobot-realomin `
  --max-files 3 `
  --max-bytes 2147483648
```

可以重复传入 `--path` 精确选择远程文件。下载状态写入
`data/raw/genrobot-realomin/acquisition_status.json`。认证失败会返回结构化
`blocked_auth`。

### 3. Inspect 原始 recording

专用 inspector 根据文件内容而不是扩展名匹配；因此有效 MCAP 即使没有 `.mcap` 后缀也
可以被识别。当前未注册其他容器 inspector，非 MCAP 文件或目录只执行通用 inventory。

```powershell
embody-data inspect `
  "data/raw/genrobot-realomin/Clutter Tidy-Up [Stage2]/00001/01708.mcap" `
  --output ".local/inspect/01708"
```

主要输出：

- `raw_manifest.json`：文件身份和 checksum；
- `source_inventory.json`：container、schema、stream、clock、frame、rights；
- `profile_decision.json`：source profile 候选、证据和决定；
- `topic_summary.json`：topic、消息数、时间范围和频率；
- `ingestion_status.json`：结构化执行状态。

### 4. Process recording

每次使用新的输出目录；Pipeline 会拒绝覆盖非空目录：

```powershell
embody-data process `
  "data/raw/genrobot-realomin/Clutter Tidy-Up [Stage2]/00001/01708.mcap" `
  --output "data/processed/genrobot-realomin-01708-v3" `
  --config "configs/processing/mvp.json"
```

处理顺序：

```text
inspect/profile decision
  -> adapter dispatch/decode
  -> semantic normalization
  -> synchronization mapping
  -> calibration validation
  -> episode derivation
  -> source + semantic QC
  -> processed manifest
```

Processing config 还可提供：

- `streams`：原始 topic 或 normalized stream ID 列表；
- `start_time_ns` / `end_time_ns`：MCAP log-time 纳秒半开区间；
- `reference_stream`：同步 reference stream；
- `max_sync_delta_ns`：最近邻映射最大时间误差。

### 5. 查看和验证 processed run

```powershell
embody-data describe "data/processed/genrobot-realomin-01708-v3"
embody-data validate "data/processed/genrobot-realomin-01708-v3"
```

`describe` 输出 processed manifest；`validate` 输出聚合 QC。QC `fail` 表示某些用途
不满足条件，不等于所有数据都不可归档。例如缺少相机 calibration 时，归档仍可继续，
但依赖完整三维几何的用途应拒绝。

### 6. 生成本地 PurposeRun

Exploration：

```powershell
embody-data purpose `
  "data/processed/genrobot-realomin-01708-v3" `
  --output "data/purpose/genrobot-realomin-01708/exploration/run-v1" `
  --config "configs/purposes/exploration.json"
```

Archival：

```powershell
embody-data purpose `
  "data/processed/genrobot-realomin-01708-v3" `
  --output "data/purpose/genrobot-realomin-01708/archival/run-v1" `
  --config "configs/purposes/archival.json"
```

PurposeRun 不重新解码 raw，也不修改 processed run。每个输出都有独立 manifest、QC、
status、provenance、validity mask 和 artifacts。

## 项目目录结构

```text
embody_data_infrastructrure/
├── AGENTS.md                     # Agent 持久约束与数据语义规则
├── EXECUTION_PLAN.md             # Phase 0–4 总体执行计划
├── README.md                     # 项目入口与运行说明
├── pyproject.toml                # 包、依赖、CLI、pytest、Ruff、mypy 配置
├── configs/
│   ├── sources/                  # 来源 profile、collection mode、rights
│   ├── processing/               # sync/calibration/episode 处理参数
│   ├── purposes/                 # archival / exploration purpose profile
│   ├── decoding/                 # 后续 decoder 配置扩展点
│   ├── synchronization/          # 后续同步策略配置扩展点
│   ├── calibration/              # 后续标定策略配置扩展点
│   └── qc/                       # 后续 QC policy 配置扩展点
├── docs/
│   ├── architecture.md           # 模块所有权和架构边界
│   ├── local_pipeline_four_layers.md
│   ├── python_files_guide.md      # 各 Python 文件职责、输入输出与边界
│   ├── internal_representation.md
│   ├── timestamp_and_frames.md
│   ├── qc_rules.md
│   ├── genrobot_realomin_source.md
│   └── codex_agent_setup.md
├── src/embody_data/
│   ├── acquisition/              # 有限额、可恢复的本地数据获取
│   ├── ingestion/                # Inspector registry、Raw discovery、inventory、checksum
│   ├── decode/                   # Adapter registry、MCAP/Protobuf 解码
│   ├── representation/           # Vendor-neutral stream/record 语义模型
│   ├── sync/                     # Reference timeline 与时间误差映射
│   ├── calibration/              # Calibration/frame/transform 验证
│   ├── episode/                  # Episode 边界与派生策略
│   ├── qc/                       # Source/semantic findings 与 validity masks
│   ├── metadata/                 # Source profile、collection mode、manifest 模型
│   ├── purpose/                  # Archival/exploration PurposeRun
│   ├── storage/                  # 纯本地 layout、ProcessedReader、PurposeReader
│   ├── cli/                      # embody-data 命令行入口
│   ├── processing.py             # 四层 Pipeline 编排入口
│   ├── config.py                 # JSON/TOML/YAML 配置加载
│   ├── errors.py                 # 结构化错误
│   ├── status.py                 # 结构化状态
│   └── logging.py                # 日志配置
├── tests/
│   ├── fixtures/                 # 小型 synthetic Protobuf MCAP 生成器
│   ├── unit/                     # 模型、dispatch、QC、purpose 单元测试
│   └── integration/              # 四层 CLI 和端到端测试
├── data/
│   ├── raw/                      # 本地不可变 Raw，不提交大型/gated 数据
│   ├── processed/                # 第 3 层 normalized processed runs
│   └── purpose/                  # 第 4 层本地用途产物
├── examples/                     # 示例输入说明
└── scripts/                      # 辅助脚本说明与后续扩展点
```

## 运行后文件夹结构

### Processed run

```text
data/processed/<recording-run>/
├── data/
│   ├── streams/                  # 每条 normalized stream 一个 JSONL
│   ├── assets/                   # H.264 等大二进制资产
│   ├── episodes/                 # Episode 边界、策略和状态
│   └── derived/                  # 后续合法派生结果，不覆盖观测
├── calibration/
│   └── camera_calibration.json
├── metadata/
│   ├── inspect/
│   │   ├── raw_manifest.json
│   │   ├── source_inventory.json
│   │   ├── profile_decision.json
│   │   ├── topic_summary.json
│   │   ├── checksum_manifest.json
│   │   └── ingestion_status.json
│   ├── timestamp_mapping.json
│   ├── provenance.json
│   ├── processing_status.json
│   └── processed_manifest.json
└── qc/
    ├── source_qc.json
    ├── semantic_qc.json
    ├── qc_report.json
    └── validity_masks/<stream-id>.json
```

### Purpose run

```text
data/purpose/<recording>/<purpose>/<run-id>/
├── artifacts/
│   ├── archival_inventory.json   # archival profile
│   ├── preview_index.json        # exploration profile
│   └── summary_statistics.json   # exploration profile
├── validity_masks/
│   └── selected_streams.json
├── purpose_manifest.json
├── purpose_qc.json
├── purpose_status.json
└── provenance.json
```

## Python Reader

下游读取 processed data 不需要导入 MCAP 或厂商 decoder：

```python
from pathlib import Path

from embody_data.storage import ProcessedReader, PurposeReader

processed = ProcessedReader(Path("data/processed/genrobot-realomin-01708-v3"))
for stream_id in processed.stream_ids():
    first_record = next(processed.iter_stream(stream_id))
    print(stream_id, first_record["source_timestamp_ns"])

purpose = PurposeReader(
    Path("data/purpose/genrobot-realomin-01708/exploration/run-v1")
)
print(purpose.qc()["verdict"])
```

## 开发与验证

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```

Synthetic fixtures 在测试期间生成，不提交大型或 gated recording。新增 decoder、同步
策略或 purpose 时，必须同时增加结构化状态、可复现 fixture、单元测试和跨模块测试。

当前基线验证结果：

- 31 tests passed；
- Ruff 全部通过；
- strict mypy 检查 41 个 source files 通过；
- 真实 `01708.mcap` 已验证 8 条 normalized streams 和独立 exploration PurposeRun。

## 已知限制

- 当前只注册了 MCAP inspector、GenRobot RealOmin profile matcher 和对应的
  embedded-Protobuf decoder adapter；注册接口已解耦，但其他格式尚不能 process。
- 时间同步目前以 nearest-reference mapping 为主，未自动估算跨时钟漂移。
- Whole-recording episode 是当前 source profile 的候选策略，不适用于所有来源。
- 当前真实 `01708.mcap` 缺少 camera calibration，且部分 IMU/gripper frame 未知；因此
  processed QC 为 `fail`，但 exploration 可以按降级策略输出 `warn`。
- Tactile、stereo depth、point cloud、retargeting 和 robot feedback 仍是扩展能力。

更多边界与路线图见 [EXECUTION_PLAN.md](EXECUTION_PLAN.md)、
[架构说明](docs/architecture.md)、[Python 文件用途说明](docs/python_files_guide.md)
和 [QC 规则](docs/qc_rules.md)。
