# Human-Collected Embodied AI Data Infrastructure：分阶段执行计划

> 本文档用于指导从零开始建设以人采集数据为源头的 Embodied AI 数据基础设施，重点覆盖 MEgo 类穿戴式/第一视角采集和 teleoperation 采集。
>
> 当前项目处于初级阶段，近期重点是把不同来源的原始数据稳定地处理成结构清晰、质量可判断、可继续使用的 processed data。云端存储、数据产品标准化和客户交付属于后续阶段，不应与当前任务处于同一优先级。

---

## 1. 文档定位

本项目不是先制定一套行业统一规范，也不是只写某一种格式的一次性转换脚本。

当前要解决的问题是：

```text
拿到一批 Human Wearable / MEgo / Teleop Device / Robot Feedback 原始数据
  -> 知道里面有什么
  -> 能正确解码
  -> 做基础统一和清洗
  -> 完成时间与空间关系处理
  -> 识别质量问题
  -> 输出可继续分析、标注或产品化的数据
```

随着数据源、业务需求和客户需求逐渐稳定，再继续建设：

```text
云端存储与数据管理
  -> 数据集标准化与产品化
  -> Release 与客户交付
```

因此，完整路线划分为四个大阶段：

| 阶段 | 核心问题 | 当前优先级 |
|---|---|---|
| Phase 1：Data Processing Foundation | 原始数据如何变成可用的 processed data？ | **当前重点** |
| Phase 2：Storage & Data Management | 数据如何上传、存储、索引、追踪和重复处理？ | 下一步 |
| Phase 3：Dataset Standardization & Productization | 数据如何形成稳定、可版本化的数据产品？ | 中后期 |
| Phase 4：Distribution & Customer Delivery | 数据如何安全、完整地交付并被客户验收？ | 后期 |

---

## 2. 总体架构

```text
Phase 1：Data Processing Foundation
Human-Collected Raw Data
  -> Inspect / Discovery
  -> Decode
  -> Normalize / General Internal Representation
  -> Temporal Synchronization
  -> Calibration / Coordinate Transform
  -> Episode Processing
  -> Processing QC
  -> Processed Dataset

Phase 2：Storage & Data Management
Local / Edge Data
  -> Upload / Ingestion
  -> Object Storage
  -> Metadata Catalog
  -> Processing Jobs
  -> Monitoring / Access / Lifecycle

Phase 3：Dataset Standardization & Productization
Processed Data
  -> Annotation / Enrichment
  -> Stable Dataset Schema
  -> Statistics / Split
  -> Versioning / Lineage
  -> Frozen Dataset Release

Phase 4：Distribution & Customer Delivery
Frozen Release
  -> Customer Scope
  -> Final QC / Rights Gate
  -> Customer-specific Packaging
  -> Secure Access / Transfer
  -> Integrity Verification
  -> Delivery Acceptance
```

四个阶段存在依赖关系，但不是要求前一个阶段做到完全生产化后才能开始下一个阶段。正确方式是先用一个小型 vertical slice 跑通 Phase 1，再逐步补充 Phase 2；只有当数据源和使用需求逐渐稳定后，才固化 Phase 3 的产品 Schema。

---

## 3. 关键概念与命名边界

### 3.1 Raw Data

由人执行任务，并通过穿戴式设备、第一视角设备、遥操作设备、机器人反馈系统或供应商工具直接产生的数据，例如：

- MCAP / ROS Bag
- 相机视频或图像序列
- Depth 数据
- IMU / VIO / Pose
- Robot state / Robot action
- Tactile / Force / Torque
- Vendor-specific binary / protobuf / JSON / CSV
- Session、task、operator、device 等采集元数据
- Consent、privacy/redaction、license、permitted-use 等治理元数据

Raw Data 是 source of truth，原则上只读、不可覆盖。

### 3.1.1 Collection Mode 与轨迹语义

每个 recording 必须声明采集模式，不能仅凭文件名、topic 名或字段名推断：

```text
human_wearable
  人佩戴或操作 MEgo/ego 采集设备；pose、gripper、IMU 描述人或采集设备。

teleop_device_only
  有遥操作输入或示教设备轨迹，但没有经过验证的机器人执行反馈。

teleop_robot
  同时存在操作者命令和可关联的机器人 state/feedback/execution 数据。
```

控制相关时序字段必须使用以下语义之一：

```text
observed_human_motion
observed_device_pose
teleop_command
robot_measured_state
robot_commanded_action
robot_executed_action
derived_action
retargeted_action
unknown
```

`robot0`、`eef_pose` 或名为 `action` 的字段不构成 robot action 的充分证据。将 pose 复制、平移一帧或求差得到的控制量属于 `derived_action`；只有记录目标 embodiment、转换算法、版本、参数和有效性后，才能标记为 `retargeted_action`。没有机器人反馈时，不能标记为 `robot_executed_action`。

### 3.2 General Internal Representation

Phase 1 不假设已经存在行业统一的 Canonical Schema。系统只需要一个最小、通用、可扩展的内部表示，使后续模块不必理解每一种原始协议。

例如：

```text
CameraStream
  timestamps
  images
  camera_id
  encoding / color_space
  validity

IMUStream
  timestamps
  acceleration
  angular_velocity
  unit
  frame

PoseStream
  timestamps
  position
  rotation
  frame_from / frame_to
  validity / confidence

RobotStream
  timestamps
  joint_state / eef_pose / gripper_state / action
  field_semantics
  unit

CollectionContext
  collection_mode
  operator_id / device_id
  consent / privacy / license status
  source embodiment
  target embodiment (if retargeted)
  semantic evidence
```

它的目的只是支持 inspect、sync、calibration、processing 和 QC，不代表对外标准，也不要求所有未来数据都被强行压缩成完全相同的字段。

### 3.3 Stable Dataset Schema

Phase 3 才定义稳定的数据产品语义，例如 observation、state、action、task、annotation、quality 和 provenance。它需要基于已经积累的数据源、处理经验和下游需求逐步形成。

### 3.4 Physical Storage Format

HDF5、Zarr、Parquet、MP4、MCAP、ROS Bag 和 array shards 都是物理存储形式，不应直接等同于数据语义。格式可以变化，字段含义、单位、坐标系和时间映射必须明确。

---

## 4. 全阶段通用原则

以下原则从 Phase 1 开始执行，但实现深度随阶段逐步增加：

1. **Raw immutable**：不覆盖原始输入，所有处理结果写入独立位置。
2. **可重复处理**：关键参数通过 config 管理，避免只存在于脚本或人工记忆中。
3. **最小可追溯**：从第一阶段开始记录 source、处理时间、代码/配置版本和输出状态。
4. **时间语义明确**：所有时序数据保留原始 timestamp；重采样后保留映射方式。
5. **空间语义明确**：所有 pose、trajectory、point cloud 声明单位和 coordinate frame。
6. **不伪造语义**：Human ego trajectory 没有真实 robot action 或可靠 retargeting 时，不能标记为 robot action。
7. **采集模式显式化**：每个 recording 声明 `human_wearable`、`teleop_device_only` 或 `teleop_robot`，并记录判断依据。
8. **Action 分层**：人/设备观测轨迹、teleop command、robot state、commanded/executed action、derived/retargeted action 分开建模。
9. **治理信息前置**：从 ingestion 开始保留 consent、license、privacy/redaction 和 permitted-use；未知值不推断。
10. **结构化 QC**：质量结果不能只打印到控制台，必须输出结构化 report 和必要的 validity mask。
11. **模块可替换**：decoder、storage backend、QC rule 和 packaging format 应能独立替换。
12. **先闭环再扩展**：先完成一个数据源、少量模态的端到端 vertical slice，再扩展更多设备和格式。
13. **Schema 不过早固化**：Phase 1 的 general representation 允许演进；只有 Phase 3 的 release schema 才需要严格兼容和版本控制。

---

# Phase 0：工程准备

Phase 0 是 Phase 1 的轻量前置工作，不是独立的数据产品阶段。

## 5. Phase 0 目标

建立能够持续迭代、测试和运行的最小工程框架，避免后续功能都堆在单文件脚本中。

## 5.1 建议技术基线

- Python package 使用 `src/` layout。
- 使用 `pyproject.toml` 声明 Python 版本、依赖、CLI 和开发工具。
- 配置文件与代码分离。
- 使用结构化 logging 和明确的 error/status model。
- 建立 unit test、integration test 和最小 sample fixture。
- 暂不绑定 AWS、GCP 或 Azure。

## 5.2 Phase 0 仓库结构

```text
embody_data_infrastructure/
├── pyproject.toml
├── README.md
├── docs/
│   ├── architecture.md
│   ├── internal_representation.md
│   ├── timestamp_and_frames.md
│   └── qc_rules.md
├── configs/
│   ├── sources/
│   ├── decoding/
│   ├── synchronization/
│   ├── calibration/
│   ├── processing/
│   └── qc/
├── src/
│   └── embody_data/
│       ├── cli/
│       ├── ingestion/
│       ├── decode/
│       ├── representation/
│       ├── sync/
│       ├── calibration/
│       ├── episode/
│       ├── qc/
│       ├── storage/
│       └── metadata/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── examples/
│   ├── sample_raw/
│   └── sample_processed/
└── scripts/
```

Phase 3 和 Phase 4 开始前，再按需要增加：

```text
annotation/
schema_registry/
packaging/
statistics/
versioning/
lineage/
distribution/
access/
```

## 5.3 Phase 0 产出与验收

产出：

- package skeleton
- CLI 入口
- config loading
- logging / error / status 基础模型
- tests 与最小 fixture
- 基础开发说明

验收：

- 能安装项目及开发依赖。
- 能运行测试。
- 能执行空的或最小的 CLI，例如 `embody-data inspect <input>`。
- 新模块可以按清晰边界添加，不需要重新设计仓库。

---

# Phase 1：Data Processing Foundation（当前重点）

## 6. Phase 1 目标与边界

### 6.1 目标

完成以下闭环：

```text
Raw Data
  -> Inspect / Discovery
  -> Decode
  -> Normalize / General Internal Representation
  -> Temporal Synchronization
  -> Calibration / Coordinate Transform
  -> Episode Processing
  -> Processing QC
  -> Processed Dataset + Report
```

Phase 1 完成后，应能够对一批真实或 sample 数据回答：

- 里面有哪些数据流？
- 每个数据流能否正确读取？
- 时间戳、频率、单位、坐标系分别是什么？
- 不同流是否能够对齐？
- calibration 是否存在且可用？
- 哪些片段有效、可修复或应拒绝？
- 处理结果如何追溯到原始数据和处理配置？
- 数据属于 wearable ego、device-only teleop 还是带机器人反馈的 teleop？
- 每条 pose/action-like signal 是观测、命令、机器人状态、派生还是 retargeted 数据？
- 数据的 consent、privacy、license 和 permitted-use 状态是否已知？

### 6.2 当前不做

- 不制定行业统一数据规范。
- 不承诺所有机器人和设备使用一个固定 Schema。
- 不一次支持所有 raw format 和 modality。
- 不建设完整的云端调度平台。
- 不做训练 pipeline 或模型训练。
- 不做客户权限、计费、License 和商业交付门户。
- 不把 Phase 1 的内部表示直接声明为最终客户数据标准。
- 不将人或采集设备轨迹自动 retarget 到具体机器人。
- 不把 vendor 工具生成的 `action` 字段自动认定为机器人执行动作。

---

## 7. Phase 1.1：Inspect / Discovery

### 目标

在不完整解码全部数据的前提下，识别 raw recording 的结构、范围和可读性。

### 输入

- raw file 或 raw directory
- 可选 source config
- 可选人工录入的 session/task/device metadata

### 必须收集

- source_id / recording_id / session_id
- 文件列表、大小、checksum、read status
- topic / stream 名称
- message schema / encoding
- message count
- start / end timestamp / duration
- estimated frequency
- device / sensor / robot / firmware 信息
- schema 或 protocol version（若可获得）
- task / scene / operator / site 等上下文（若可获得）
- collection_mode 与分类依据
- source embodiment / capture device / teleop device
- consent / privacy-redaction / license / permitted-use（若可获得）

### 输出

```text
raw_manifest.json
topic_summary.json
ingestion_status.json
checksum_manifest.json
```

### 建议接口

```bash
embody-data inspect <raw_path> --output <manifest_dir>
```

### 验收标准

- 缺失 topic、坏文件、未知 schema 和无法读取的片段有结构化记录。
- manifest 不依赖某个训练框架。
- 后续 decode、sync、QC 可直接使用该 manifest。
- 大文件不需要全部载入内存才能完成基本扫描。

---

## 8. Phase 1.2：Decode / Deserialization

### 目标

把 storage representation 转换为程序可处理的数据，同时完整保留时序和来源信息。

### 输入

- raw recording
- raw manifest
- decoder config

### 典型映射

```text
Compressed RGB / H264 -> uint8 image array [H, W, 3]
Encoded depth         -> float32 depth map [H, W, 1]
IMU protobuf          -> acceleration + angular velocity
Pose protobuf         -> position + quaternion
Robot state/action    -> named numeric fields / vector
Tactile / force       -> sensor-specific numeric tensor
Human/device pose     -> observed pose/trajectory with explicit semantic role
Teleop input          -> teleop command, separate from robot feedback
```

### Decoder 设计要求

- 按数据源或 schema 注册 decoder，不把所有判断写进单一函数。
- 支持 selective loading：按 topic、时间范围、episode 或 shard 读取。
- 保留 source timestamp、sequence/frame id 和原始字段名称。
- decode failure 返回结构化错误和受影响范围。
- 明确 color encoding、compression、endianness 和 dtype。

### 输出

- decoded samples / stream iterator
- timestamps
- frame_id / sequence_id
- decode status / error report
- decoder name and version

### 验收标准

- 解码结果不丢失 timestamp。
- 可以只读取指定 topic 或时间段。
- 坏帧不导致整批数据无信息地失败。
- 同一 sample 输入与同一配置可以得到一致输出。

---

## 9. Phase 1.3：Normalization / General Internal Representation

### 目标

将不同 decoder 的输出映射到最小、通用的内部对象，使 sync、calibration、processing 和 QC 不需要理解原始 protobuf、ROS message 或 vendor schema。

### 最小内部对象

```text
Stream
├── stream_id
├── modality
├── timestamps: [N]
├── data or data_reference: [N, ...]
├── frame_id / sequence_id
├── dtype / shape
├── unit
├── coordinate_frame
├── encoding
├── validity / confidence
├── source_fields
├── semantic_role
├── collection_mode
├── derivation / retargeting metadata
└── representation_version
```

### 需要统一或显式声明的内容

- RGB / BGR / grayscale
- meter / millimeter
- degree / radian
- quaternion XYZW / WXYZ
- right-handed / left-handed convention
- coordinate frame 命名
- timestamp unit / clock domain
- dtype / shape / channel order
- missing value policy
- observed/commanded/executed/derived/retargeted semantic role
- source embodiment and target embodiment where applicable

### 兼容策略

- 保留 source-specific extension，避免为了“统一”而丢失原始语义。
- 未知字段可以保留在 extension metadata 中，不能静默丢弃。
- representation version 可以快速演进，早期不承诺长期兼容。

### 验收标准

- 后续模块只依赖 general representation，不直接依赖源协议。
- 每个字段都有 dtype、shape、unit、frame 或明确的 `not_applicable / unknown`。
- source field 到 internal field 的映射可追踪。

---

## 10. Phase 1.4：Temporal Synchronization

### 目标

将不同频率、不同采样时刻和可能不同 clock domain 的数据映射到共同的 reference timeline，同时保留误差和缺失信息。

### 处理步骤

1. 检查 timestamp 单位、clock source、单调性和 reset。
2. 选择 reference timeline，例如 camera0、robot control clock 或人工定义频率。
3. 为每个 stream 配置 alignment strategy。
4. 输出 aligned value、validity 和 sync error。

### 建议策略

- 相机或离散事件：nearest neighbor / previous / next。
- 连续标量或向量：linear interpolation。
- Pose translation：linear interpolation。
- Pose rotation：SLERP。
- 高频 IMU：window、mean、integral、interpolation 或 preintegration，按用途配置。
- Action / command：必须明确是 zero-order hold、nearest，还是按控制周期重采样。

### 输出示例

```text
reference_timestamps: [N]
camera0: [N, H, W, 3]
pose: [N, 7]
imu: [N, 6] or [N, K, 6]
observed_device_pose: [N, P]
teleop_command: [N, C]             # if available
robot_measured_state: [N, S]       # teleop_robot only
robot_commanded_action: [N, A]     # only with verified semantics
validity_mask: [N, ...]
sync_error: [N, ...]
alignment_metadata
```

### 验收标准

- 每个 aligned field 记录 alignment method 和 max allowed delta。
- 超过阈值的数据标记 missing，不强行匹配。
- 输出 p50 / p95 / max sync error、coverage 和 missing count。
- 保留 reference timeline 与 source timestamps 的映射。

---

## 11. Phase 1.5：Calibration / Coordinate Transform

### 目标

明确不同相机、传感器、人体或机器人坐标系之间的空间关系，使 pose、trajectory、depth 和 point cloud 可以被正确解释。

### 必须支持

- camera intrinsics
- camera / sensor / robot extrinsics
- frame graph
- static / time-varying transform
- depth projection / point cloud（按项目需要）
- calibration source and version

### 数据要求

每个空间字段必须尽可能记录：

- frame_from / frame_to
- unit
- rotation representation
- transform direction
- calibration_id
- valid time range
- confidence / status（若存在）

### 与 Synchronization 的关系

时间对齐和空间校准是两个并行维度：

```text
General Internal Streams
  -> Temporal Alignment
  -> Spatial Interpretation / Transform
  -> Usable Multimodal Episode
```

如果 transform 随时间变化，则必须使用对应 timestamp 的 transform，不能只使用静态矩阵替代。

### 验收标准

- 所有 XYZ、pose、trajectory 和 point cloud 字段都有 frame 与 unit。
- calibration 缺失或失效时，不生成看似合法的空间结果。
- processed output 可追溯到 calibration package/version。

---

## 12. Phase 1.6：Episode Processing

### 目标

把 recording 整理为边界明确、可使用的 episode 或 trajectory，同时不覆盖原始数据。

### 功能

- trimming
- episode / task segmentation
- resampling
- invalid interval masking
- trajectory filtering / smoothing
- outlier detection
- task boundary / event boundary
- derived fields（例如 velocity、relative pose；必须记录算法和参数）

### 原则

- recording、episode 和 processed episode 使用不同 ID。
- 原始 trajectory 保留，处理结果单独保存。
- smoothing、filtering 和 interpolation 参数全部配置化。
- 自动 segmentation 应保留置信度和人工修订入口。

### 验收标准

- episode start/end 和来源 recording 明确。
- trimming、smoothing、outlier 参数可追溯。
- invalid interval 不被静默删除；保留 mask 或原因。
- 处理结果可以被 QC 和后续 annotation 消费。

---

## 13. Phase 1.7：Processing QC / Validation

### 目标

判断 raw 与 processed data 是否完整、可信和可继续使用，并区分 pass、warning、repairable 和 reject。

### QC 分层

#### Ingestion / Decode QC

- file readable / checksum
- schema recognized
- decode failure
- corrupt frame / truncated recording

#### Timestamp / Sync QC

- monotonicity
- duplicate timestamp
- timestamp gap / reset
- frequency stability
- stream coverage
- sync error

#### Camera / Depth QC

- black / frozen / damaged frames
- blur / exposure / occlusion
- resolution / FPS consistency
- invalid depth ratio / depth range

#### Pose / Trajectory QC

- tracking lost
- jump / impossible velocity or acceleration
- quaternion norm
- discontinuity
- coordinate frame mismatch

#### Robot / IMU / Tactile QC

- joint limit / saturation
- missing fields
- sensor drift
- latency
- action/state inconsistency
- coverage and confidence
- collection-mode and semantic-role consistency
- teleop command / robot feedback latency（若两者均存在）
- retargeting validity and target embodiment（若适用）

#### Human Collection / Governance QC

- operator/session identity 使用 pseudonymous ID
- consent / permitted-use metadata presence
- privacy/redaction status
- wearable tracking loss / device slippage
- left/right device identity and swap detection
- human/device trajectory incorrectly labeled as robot action

### 输出示例

```json
{
  "episode_id": "...",
  "verdict": "pass | warning | repairable | reject",
  "camera_coverage": 0.99,
  "pose_coverage": 0.96,
  "max_sync_error_ms": 12.4,
  "timestamp_gap_count": 2,
  "invalid_intervals": [],
  "warnings": [],
  "qc_rule_version": "..."
}
```

同时按需要输出 frame-level / timestep-level validity mask。

### QC 的位置

QC 不是只运行一次的单独步骤。Phase 1 中至少需要：

```text
Ingestion QC
  -> Decode QC
  -> Sync / Calibration QC
  -> Episode Processing QC
  -> Final Processed Dataset Verdict
```

### 验收标准

- 有 episode-level verdict。
- 关键模态有 frame/timestep-level validity mask。
- 每条失败或警告有 rule id、原因和受影响范围。
- QC rule/config version 可追溯。
- QC report 与 processed data 一起输出。

---

## 14. Phase 1.8：Processed Dataset 输出

### 目标

输出结构清晰、能够被分析、标注或下一阶段上传管理的数据，而不是最终商业 release。

### 建议逻辑结构

```text
processed_run_<id>/
├── data/
│   ├── episodes/
│   ├── streams/
│   └── derived/
├── calibration/
├── metadata/
│   ├── source_manifest.json
│   ├── processing_manifest.json
│   ├── episode_index.json
│   └── field_descriptions.json
├── qc/
│   ├── summary.json
│   └── validity_masks/
└── README.md
```

实际落盘可使用视频、Parquet、HDF5、Zarr 或其他适合格式；此处规定的是逻辑内容，不锁死单一格式。

### 最小 Processing Manifest

- processing_run_id
- source_recording_id
- input checksums
- decoder / representation / sync / calibration / processing / qc versions
- config snapshot or config hash
- start / end time and status
- output objects and checksums
- warnings / failures

### 验收标准

- 用户无需查看处理脚本即可理解主要文件和字段。
- processed episode 可以按 episode 和时间范围读取。
- 输出含 source、processing、calibration 和 QC 信息。
- 同一原始数据可以保留多个 processing run，不互相覆盖。

---

## 15. Phase 1 MVP Vertical Slice

### MVP Scope

第一版建议严格限制在：

- 1 种人采集 raw recording 格式，优先 MCAP
- 1 个 MEgo/wearable 或 teleop 真实小样本，加可复现 mock fixture
- 2–4 个核心模态：ego RGB、IMU、observed EEF/device pose、gripper state
- 1 个 reference timeline
- 1 套最小 general internal representation
- 1 套 timestamp/camera/pose 基础 QC
- 1 种 processed output layout
- 1 个 reference reader
- 1 套 collection mode 与 action/trajectory semantic classification

MVP 只实现一种格式不等于在顶层绑定该格式。Inspector、source-profile matcher 和
decoder 分别注册；通用 Pipeline 从确认后的 profile 读取 container、encoding、
collection mode 与 trajectory semantics。新增格式应增加对应注册项，不应在 CLI 或
`processing.py` 中继续增加按扩展名、厂商名或 topic 名的硬编码分支。

建议真实样本控制在 2–5 个 recording。大型或 gated 数据不提交到仓库；测试使用小型合成 fixture。Stereo depth、point cloud、tactile、robot feedback 和 retargeting 作为扩展能力，不阻塞第一版闭环。

### MVP 闭环

```text
sample raw
  -> raw manifest
  -> decoded streams
  -> normalized internal streams
  -> synchronized episode
  -> calibration/frame metadata
  -> processed episode
  -> QC report
  -> processed dataset
  -> reference reader loads episode/timestep
```

### MVP 命令示例

```bash
embody-data inspect <raw_path> --output <manifest_dir>
embody-data process <raw_path> --config <config_path> --output <processed_dir>
embody-data validate <processed_dir>
embody-data describe <processed_dir>
```

### MVP Definition of Done

- 从 sample raw 到 processed dataset 的命令可运行。
- 失败时产生结构化错误，不只打印 traceback。
- reader 可读取指定 episode、stream 和 timestep/time range。
- 每个字段有 dtype、shape、unit、frame 或明确缺失说明。
- QC report 包含 verdict、coverage、sync error 和 invalid range。
- 处理结果可追溯到 raw source、配置与代码/模块版本。

---

# Phase 2：Storage & Data Management（下一阶段）

## 16. Phase 2 目标

当 Phase 1 能稳定产生 processed data 后，解决数据量增加、多人协作和重复运行带来的问题：

- 原始数据和处理结果放在哪里？
- 如何从采集电脑上传到统一位置？
- 如何知道当前拥有哪些 recording、episode 和模态？
- 如何避免重复上传和重复处理？
- 如何运行、失败重试和追踪 processing job？
- 如何控制权限、成本、备份和数据生命周期？

Phase 2 先使用 vendor-neutral 架构概念，不必现在决定 AWS、GCP 或 Azure。

---

## 17. Phase 2 总体架构

```text
Collection Device / Local Workstation
  -> Upload Client / Transfer Job
  -> Object Storage
       ├── raw/
       ├── processed/
       ├── annotations/
       ├── releases/
       └── temporary/
  -> Metadata Catalog / Database
  -> Processing Job / Queue / Worker
  -> Monitoring / Audit / Cost / Lifecycle
```

### 17.1 Object Storage

用于存放大文件和不可变对象，例如视频、bags、arrays、shards、calibration package 和 report。

未来可映射到：

- Amazon S3
- Google Cloud Storage
- Azure Blob Storage
- 兼容 S3 API 的其他存储

架构和代码应通过 storage interface 访问，不在业务逻辑中硬编码某个厂商。

### 17.2 Metadata Catalog / Database

用于查询“有什么数据”和“数据在哪里”，不要把所有查询都依赖于扫描文件夹。

建议管理实体：

```text
Recording
Episode
Stream / Asset
Calibration
Processing Run
QC Result
Annotation Set
Dataset Version
Release
Delivery
```

Phase 2 初期可用轻量数据库；规模和并发增加后再迁移到托管数据库或专门 catalog。

### 17.3 Processing Job Layer

用于把 Phase 1 的本地 CLI 升级为可管理的任务：

- job submission
- parameter/config snapshot
- status: queued/running/succeeded/failed/cancelled
- retry and idempotency
- logs and metrics
- resource requirements
- input/output registration

### 17.4 Access and Security

- identity and role
- least-privilege access
- encryption in transit / at rest
- secrets management
- access audit
- sensitive data classification
- separate raw, processed and customer access boundary

### 17.5 Lifecycle and Cost

- hot / warm / archive tier
- retention policy
- temporary output cleanup
- incomplete upload cleanup
- checksum and integrity verification
- backup / replication requirements
- storage and egress cost monitoring

---

## 18. Phase 2 实施子阶段

### Phase 2A：Local Storage Contract

先在本地实现与云无关的 storage interface、路径规则、object naming、checksum 和 manifest。

验收：Phase 1 不直接依赖具体云 SDK。

### Phase 2B：Single Cloud Proof of Concept

选择一个 object storage provider，跑通：

```text
upload -> integrity check -> catalog registration
       -> processing download/read -> output upload
```

验收：重复执行不会产生无法识别的重复数据；失败可恢复。

### Phase 2C：Catalog and Processing Jobs

建立 recording、episode、processing run、QC result 的查询和状态管理。

验收：可以查询某个 source 经过哪些处理、产生哪些 output、为什么失败。

### Phase 2D：Production Hardening

增加权限、审计、监控、告警、生命周期、成本和灾难恢复。

验收：云端系统满足团队使用和数据增长需求。

---

## 19. Phase 2 Definition of Done

- Raw 和 processed data 有明确 storage location 与 object identity。
- 上传后进行 checksum / integrity 验证。
- Catalog 可按 recording、episode、modality、task、site、time 和 QC 状态查询。
- Processing run 的输入、配置、状态、日志和输出可追踪。
- 重复任务具备 idempotency 或明确版本策略。
- 权限、加密、备份、生命周期和成本有基础规则。
- 本地开发仍可运行，不被单一云厂商锁死。

---

# Phase 3：Dataset Standardization & Productization（中后期）

## 20. Phase 3 启动条件

只有满足以下条件后，才适合开始固化稳定 Dataset Schema：

- 已处理多批真实数据。
- 主要数据源和 modality 已被验证。
- 时间、坐标、action 和 annotation 语义基本清楚。
- 已知至少一种明确的内部或客户使用场景。
- Phase 1 的 general representation 中哪些字段稳定、哪些字段设备特有已有经验。

---

## 21. Annotation / Enrichment

### 分层

- Basic：task、scene、success、instruction。
- Temporal：subtask、event、contact、failure/recovery。
- Spatial：object identity、bbox、mask、pose、trajectory、hand pose。
- Interaction-rich：grasp state、support relation、object-relative motion。

### 必须记录

- annotation_source
- annotator / tool
- model_version（若自动生成）
- confidence
- annotation_version
- generation / revision time
- review status

### 原则

- Annotation 与 Raw、Processing 和 Dataset Schema 分开版本化。
- 修订标注不覆盖旧版本。
- Release 明确引用哪个 annotation version。

---

## 22. Stable Dataset Schema / Schema Registry

### 建议逻辑结构

```text
episode
├── identity / timestamps / frame index
├── task / scene / instruction
├── observation
├── state
├── action
├── object / environment state
├── interaction / event
├── annotation
├── quality
└── provenance
```

### Extensions

- Human Collection Extension：collection mode、hand/body/device pose、human-object contact、operator/device identity。
- Teleop Extension：teleop device、command semantics、target embodiment、command/feedback linkage。
- Robot Extension：robot identity、joint state、EEF pose、gripper state、measured feedback。
- Action Extension：source/derivation、control semantics、frequency、absolute/delta、commanded/executed/derived/retargeted。
- Sensor Extension：RGB、Depth、IMU、VIO、Tactile、Language。

### 每个字段必须定义

- name and semantic description
- dtype and shape
- unit
- coordinate frame
- timestamp / frequency mapping
- missing policy
- source or derivation
- schema version

### Breaking Change

以下通常属于 semantic breaking change：

- 单位变化
- coordinate frame 或 transform direction 变化
- quaternion 顺序变化
- action semantics 变化
- commanded 与 executed 含义变化
- absolute 与 delta 含义变化
- 字段在不兼容条件下删除或重解释

仅改变 MP4、Parquet、HDF5、Zarr 等落盘形式，而逻辑语义不变时，不一定构成 Schema breaking change。

---

## 23. Dataset Packaging / Release Layout

建议逻辑目录：

```text
dataset_name_v1.0/
├── data/
│   ├── shard_000.*
│   └── shard_001.*
├── videos/
├── calibration/
│   ├── camera_intrinsics.json
│   ├── camera_extrinsics.json
│   └── frame_transforms.json
├── metadata/
│   ├── dataset_info.json
│   ├── schema.json
│   ├── episodes.*
│   ├── tasks.*
│   ├── stats.json
│   ├── qc.json
│   └── lineage.json
├── checksums.*
└── README.md
```

要求：

- 客户或下游团队不需要猜文件名来理解数据。
- manifest 能映射 episode 到 shard、offset、length 和关联媒体。
- 有 schema validation、episode count validation 和 missing-object validation。
- 提供 reference reader。

---

## 24. Statistics / Split

### Statistics

- mean / std / min / max
- episode length distribution
- task / scene / object / operator / site distribution
- success rate
- sensor coverage
- action/state range
- camera resolution and duration
- duplicate / near-duplicate report
- QC distribution

### Split 原则

- 按 episode、scene、object、operator、site 或 robot 分组。
- 不能把同一 episode 的相邻帧随机拆到 train/val/test。
- 泛化评估要明确 withheld dimension。
- normalization statistics 只基于 training split 计算，避免 leakage。

若标准交付不包含 split，也应提供客户自行 split 的推荐规则。

---

## 25. Versioning / Lineage / Frozen Release

### Lineage 链路

```text
raw_recording_id
  -> decoder_version
  -> representation_version
  -> sync_version
  -> calibration_version
  -> processing_version
  -> qc_version
  -> annotation_version
  -> schema_version
  -> dataset_version
  -> release_id
```

Lineage 从 Phase 1 就开始记录；Phase 3 将其固化成 release contract，而不是到最后才补写。

### Frozen Release 原则

- Release 一旦发布，不在同一版本下静默更改内容。
- 数据、Schema、annotation、QC、stats、split 和 checksums 一起冻结。
- 修复内容生成新 patch/minor/major release，并提供 changelog。
- 支持从 source 或 processing issue 定位受影响的 release。

### Phase 3 Definition of Done

- 有稳定、版本化的 Dataset Schema。
- 有 annotation contract 和 review/version 机制。
- 有 packaging、manifest、checksums 和 reference reader。
- 有 statistics 与可复现 split policy。
- 每个 sample / episode 可追溯到 source 和 processing run。
- Release 内容被冻结并带有 changelog。

---

# Phase 4：Distribution & Customer Delivery（后期）

## 26. Phase 4 目标

把冻结的数据集版本转化为可采购、可授权、可下载、可验证和可验收的客户交付物。

---

## 27. Customer Scope / Dataset Contract

交付前明确：

- task / scene / robot / device / site scope
- modality and quantity
- annotation level
- quality threshold
- schema and format
- split / statistics requirement
- permitted use / restriction
- update and correction policy
- delivery method and acceptance criteria

客户定制要求应作为配置和 contract layer，不应直接破坏通用 processed data。

---

## 28. Final QC / Rights Gate

### Final QC

- release identity and version
- object completeness
- schema validation
- count / distribution validation
- checksum validation
- QC threshold compliance
- documentation completeness

### Rights / Governance

- data ownership
- collection consent / permitted use
- privacy / sensitive content
- geographic or customer restriction
- retention and deletion obligation
- license and redistribution rules

质量通过但 rights 不满足的数据不能交付。

---

## 29. Secure Distribution

交付方式可包括：

- time-limited cloud download
- customer-specific bucket/prefix
- managed file transfer
- physical encrypted media（特殊场景）
- API / streaming access（规模化后）

必须具备：

- customer-specific delivery_id
- least-privilege access
- access expiration
- audit log
- transfer/integrity status
- revoke capability

---

## 30. Delivery Package

每个交付至少包含：

- dataset objects / shards
- manifest
- schema / data dictionary
- calibration specification
- QC report
- dataset statistics
- version / changelog
- checksum manifest
- rights / permitted-use information
- README
- reference reader or access instructions

交付流程：

```text
Customer Scope / Order
  -> Dataset Contract
  -> Release Version Lock
  -> Final QC + Rights Gate
  -> Customer-specific Packaging
  -> Secure Access / Transfer
  -> Customer Integrity Verification
  -> Delivery Acceptance
```

### Phase 4 Definition of Done

- 客户可验证 identity、completeness、integrity、schema、quality 和 rights。
- 每次交付有独立 delivery_id、release_id 和 access record。
- 能撤销访问并定位客户获得的具体版本。
- Acceptance 结果、问题和修订流程可追踪。

---

# 31. 分阶段依赖与不应提前建设的内容

| 能力 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---:|---:|---:|---:|
| Raw inspect / decode | 建设 | 扩展规模 | 使用 | 使用 |
| General internal representation | 建设、允许演进 | 持续演进 | 映射到稳定 Schema | 使用 |
| Sync / calibration / processing | 建设 | 云端执行与追踪 | 固化版本 | 使用 |
| QC | 处理质量 | 运行监控与索引 | Release acceptance | Final delivery gate |
| Metadata / provenance | 最小记录 | Catalog 化 | Release lineage | Delivery audit |
| Object storage | 本地接口 | **核心建设** | 承载 release | 承载交付 |
| Stable Dataset Schema | 不固化 | 收集需求 | **核心建设** | 合同引用 |
| Annotation | 可预留接口 | 存储与管理 | **核心建设** | 按合同交付 |
| Dataset version / split / stats | 非重点 | 可记录 run | **核心建设** | 冻结使用 |
| Customer access / rights | 不做 | 基础安全 | 准备 metadata | **核心建设** |

---

# 32. 推荐实施顺序

## 当前：Phase 0 + Phase 1 MVP

1. 建立 package、`pyproject.toml`、CLI 和测试框架。
2. 选择一个 MEgo/wearable 或 teleop MCAP 小样本和核心 modality。
3. 定义 Raw Manifest、CollectionContext、Stream、Processing Run、QC Report 的最小模型。
4. 定义 collection mode 和 action/trajectory semantic role 枚举。
5. 实现 Inspect / Discovery。
6. 实现目标 MCAP/Protobuf decoder。
7. 实现 general internal representation 与 normalization。
8. 实现 reference timeline synchronization。
9. 接入 calibration/frame metadata。
10. 实现 episode trimming/segmentation 的最小版本。
11. 实现 timestamp、camera、pose 和语义一致性基础 QC。
12. 输出 processed dataset 和 processing manifest。
13. 实现 reference reader并跑通端到端测试。

## 下一步：Phase 2A–2B

1. 定义 storage interface 和 object identity。
2. 确定 raw / processed / temporary 路径规则。
3. 实现 checksum、upload/download 和 resumable transfer。
4. 选择一个云 object storage 做 proof of concept。
5. 建立最小 Recording / Episode / Processing Run catalog。

## 稳定后：Phase 2C–2D + Phase 3

1. 增加 job queue/worker、retry、monitoring 和 audit。
2. 根据真实数据和下游需求定义 Stable Dataset Schema。
3. 建设 annotation、statistics、split、versioning 和 lineage。
4. 生成第一个 frozen internal release。

## 商业交付前：Phase 4

1. 定义 Dataset Contract 和 acceptance criteria。
2. 建设 rights gate 与 customer-specific access。
3. 完成完整性验证、交付审计和 acceptance workflow。

---

# 33. 每个工程任务的通用 Definition of Done

一个模块或阶段只有同时满足以下条件才算完成：

- 有明确输入、输出和边界。
- 有代码实现，不只停留在设计文档。
- 有配置或字段说明。
- 有结构化 output/status/error，不只在控制台打印。
- 有 unit test、integration test 或可复现 sample 验证。
- 有版本或 provenance 信息。
- 不覆盖 Raw source of truth。
- 能被下一模块消费。
- 已记录未覆盖的边界情况和生产化缺口。

---

# 34. 后续 Agent 工作规则

```text
你正在构建 Human-Collected Embodied AI Data Infrastructure，数据由人通过 MEgo/wearable ego device 或 teleoperation 系统采集。

当前优先级：
Phase 1 Data Processing Foundation。

当前目标：
将 raw data 稳定地 inspect、decode、normalize、synchronize、calibrate、process、QC，
并输出结构清晰、可追溯的 processed dataset。

工作规则：
1. 不将 Phase 1 的 General Internal Representation 宣称为行业统一 Canonical Schema。
2. 不在当前任务中擅自扩展到云平台、商业交付或模型训练。
3. Raw data 只读，所有处理结果单独输出。
4. 每个阶段产生结构化 metadata、status、version/provenance。
5. 所有时序字段保留 timestamp 或明确 reference timeline 映射。
6. 所有空间字段声明 frame、unit 和 calibration version/status。
7. QC 产生 episode-level verdict 和必要的 frame/timestep validity mask。
8. Action 字段必须明确 commanded/executed、absolute/delta、EEF/joint 等语义。
9. 每个 recording 必须声明 human_wearable、teleop_device_only 或 teleop_robot，并记录判断依据。
10. observed human/device trajectory、teleop command、robot state、derived action 和 retargeted action 必须分开；字段名不能代替语义证据。
11. 没有机器人反馈时不能声称存在 robot executed action；没有明确 retargeting contract 时不能声称 policy-ready robot action。
12. 从 ingestion 开始保留 consent、privacy/redaction、license 和 permitted-use metadata；未知值保持 unknown。
13. 优先完成一个小型端到端 vertical slice，再扩展格式和 modality。
14. 信息不足时，保留可扩展接口并明确假设，不硬编码无法验证的未来规范。

每次任务完成后报告：
- 修改的模块和文件。
- 对应 Phase 与子阶段。
- 输入、输出及新增 metadata/config。
- 运行过的测试和验证命令。
- 已知限制和下一步建议。
- collection mode 及 action/trajectory 语义判断。
```

---

# 35. 单任务 Agent Prompt 模板

```text
请基于 DATA_INFRASTRUCTURE_PHASED_EXECUTION_PLAN.md 实现 <Phase / 子阶段>。

范围：
- 只实现 <具体模块/功能>。
- 不重构无关模块。
- 不提前实现后续 Phase 的生产化能力。

输入：
- <输入文件/目录/对象>
- <配置文件>

输出：
- <结构化数据产物>
- <metadata/status/version/provenance>
- <测试或 sample>

验收标准：
- <可运行命令>
- <预期输出>
- <字段/时间/坐标/QC 要求>

完成后报告：
- 修改文件列表。
- 验证命令与结果。
- 未覆盖的边界情况。
- 对下一阶段接口的影响。
```

---

# 36. 当前最终目标总结

当前不追求一次搭建完整商业数据平台。近期成功标准是：

> 拿到一批由人通过 MEgo/wearable 或 teleop 系统采集的多模态原始数据后，可以在不混淆人、设备、命令和机器人反馈语义的前提下，稳定完成 discovery、decode、normalization、时间对齐、空间关系处理、episode processing 和 QC，并输出结构清晰、可追溯、可继续用于标注、retargeting 或机器人学习的数据。

之后再按顺序解决：

```text
先把数据处理正确
  -> 再把数据存好、管好、找得到
  -> 再把稳定数据标准化成产品
  -> 最后安全、完整地交付给客户
```

这四层必须保持边界清楚，但 metadata、QC 和 provenance 从 Phase 1 起就应保留最小基础，避免后期无法追溯。
