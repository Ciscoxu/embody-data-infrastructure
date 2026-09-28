# 本地 Pipeline 四层分类设计

## 1. 范围与命名

本文定义的是 **Phase 1 内部的四层本地处理架构**，不是
`EXECUTION_PLAN.md` 中的 Phase 1–4 产品路线图。当前范围只覆盖：

```text
本地不可变 Raw
  -> 来源发现与分类
  -> 来源适配与解码
  -> 通用语义处理核心
  -> 用途策略与本地产物
```

不包含云存储、上传、任务调度、数据目录服务、客户交付或模型训练。

四层设计的目标是让新增来源不再复制整条流水线，让同一份标准化数据可被多个
用途策略复用，同时保留来源事实、时间与空间语义、QC 和 provenance。

## 2. 三个相互独立的分类轴

Pipeline 不使用一个 `source_type` 同时表达格式、语义和用途。每个 processing run
必须分别声明以下三个轴。

### 2.1 来源分类：决定怎样读取

- 容器或物理格式：`mcap`、`ros1_bag`、`ros2_bag`、`hdf5`、
  `parquet`、`video_csv`、`vendor_binary`。
- 编码或 schema：embedded Protobuf、ROS message/CDR、JSON、表结构或厂商 schema。
- source profile：例如 `genrobot_realomin_mcap`，负责 topic/key 与设备事实的映射。
- clock evidence：log、publish、header、video PTS、硬件触发或未知时钟域。

Protobuf 是 GenRobot MCAP adapter 的实现细节，不是通用 Pipeline 的固定步骤。

### 2.2 采集模式分类：决定数据是什么

- `human_wearable`：人体或穿戴/手持采集设备的观测。
- `teleop_device_only`：操作设备意图存在，但没有已验证的机器人执行反馈。
- `teleop_robot`：命令与同步机器人 state/feedback 均有证据。

控制相关字段必须进一步分类为 `observed_human_motion`、
`observed_device_pose`、`teleop_command`、`robot_measured_state`、
`robot_commanded_action`、`robot_executed_action`、`derived_action`、
`retargeted_action` 或 `unknown`。弱证据只能保留为较不确定的分类。

### 2.3 用途分类：决定怎样处理和验收

- `archival`：身份、完整性、来源字段与重处理能力优先。
- `exploration`：索引、预览、统计和低成本关联优先。
- `learning_readiness`：只检查训练前置条件并生成本地窗口/映射；不做模型训练。
- `retargeting`：生成单独的 `derived_action` 或 `retargeted_action`，必须声明目标
  embodiment、算法、参数和有效性。
- `control_evaluation`：只接受有充分命令与反馈证据的数据。

用途分类不能改变来源事实。例如 exploration 可以容忍缺少相机外参，但三维几何或
retargeting policy 应因此失败。

## 3. 第 1 层：来源发现与分类

### 职责

- 注册本地 raw 文件或目录，只读并计算对象身份。
- 探测容器、schema、channel/topic、编码、消息数量和时间范围。
- 提取时间戳候选、clock domain 证据、frame/calibration 候选和设备元数据。
- 根据显式配置、正式文档和内容指纹选择 source profile 候选。
- 记录 collection mode 的值、证据来源和置信级别；不能仅凭名称推断。
- 保留 consent、license、privacy/redaction、operator pseudonym 和 permitted-use，
  未知值保持 `unknown`。

### 输入与输出契约

输入是本地 raw path 和可选的用户 source hint。输出为：

```text
SourceInventory
├── source_object_identity
├── files / checksums / read status
├── container / schema / stream inventory
├── timestamp and clock candidates
├── calibration and frame candidates
├── profile candidates + evidence
├── collection_mode decision + evidence
└── rights and privacy metadata
```

结构化失败包括 `raw_not_found`、`unsupported_container`、`corrupt_container`、
`unknown_schema` 和 `profile_ambiguous`。发现失败不修改 raw，也不自动升级语义。

### 当前代码映射

`ingestion/base.py` 提供内容匹配的 inspector registry；`mcap_inspect.py` 注册当前唯一
的 MCAP inspector。`metadata/source_profiles.py` 提供 profile matcher registry、明确的
confirmed/ambiguous/unknown decision，以及 collection-mode evidence。有效 MCAP 不依赖
文件扩展名即可识别；普通文件/目录只能生成基础 inventory，尚不能进入完整 processing。

当前缺口是其他容器 inspector、更多 source profile matcher，以及跨 inspector 通用的
schema/clock evidence 抽象；这些缺口不能通过在 CLI 中新增文件名判断来绕过。

## 4. 第 2 层：来源适配与解码

### 职责

本层由三个可替换部分组成：

```text
transport reader -> schema decoder -> source profile mapper
```

- transport reader 读取 MCAP、Bag、HDF5 等容器。
- schema decoder 将 Protobuf、CDR 或其他编码变成 source-near message。
- source profile mapper 解释 topic/key、设备角色、来源单位和字段位置。
- 所有输出保留 log/publish/header timestamp、sequence、frame、原始字段和解码状态。
- 支持按 stream/topic 和时间范围选择性读取。

本层不选择训练窗口、不做 retargeting、不把观测转换为 action，也不决定最终 QC
阈值。

### 输入与输出契约

输入是 `SourceInventory`、确认后的 source profile 和 raw object。输出为：

```text
DecodedEnvelope
├── source_stream_id / source_message_type
├── log / publish / header timestamp
├── clock domain evidence
├── sequence_id / frame_id
├── source-near payload
├── preserved source extensions
└── decoder identity / structured error
```

建议 dispatch key 使用 `(container, encoding, source_profile)`，而不是在 CLI 或
单一 pipeline 函数中按文件名分支。

### 当前代码映射

`decode/mcap.py`、`decode/genrobot.py` 和 `representation/genrobot.py` 已完成
RealOmin embedded-Protobuf vertical slice。`decode/base.py` 的 adapter registry 已成为
实际 dispatch 入口，`processing.py` 根据确认后的 Source Profile 构造
`(container, encoding, source_profile)` key；stream 和 log-time 范围选择已经贯通。
`process_genrobot_mcap()` 只保留为向后兼容包装器。

当前仍只有一个实际 decoder adapter；新增来源还需要实现自己的 decoder 和
representation mapper，但不应修改通用 sync、episode、QC 或 reader。

## 5. 第 3 层：通用语义处理核心

### 职责

本层是 vendor-neutral 的 Phase 1 核心，下游不得依赖 Protobuf、MCAP topic 或厂商
类型。其内部顺序为：

```text
semantic mapping
  -> clock model and synchronization mapping
  -> calibration/frame validation
  -> episode derivation
  -> source and semantic QC facts
```

最低语义对象包括视觉、IMU、pose、gripper、teleop intent、robot measured state、
commanded/executed action、derived/retargeted action、calibration 和 episode boundary。

每个 stream/record 必须携带：

- collection mode 与 semantic role；
- 原始时间戳、timestamp source 和 clock domain；
- unit、coordinate frame、transform direction 和 calibration identity；
- source field mapping、extensions、representation version 和 provenance；
- validity/confidence，未知事实显式为 `unknown` 或 `not_applicable`。

同步输出是 source 到 reference timeline 的映射，不覆盖原始时间戳。空间变换与时间
映射分属 calibration 和 sync。Episode 边界必须记录策略和证据。

### 输入与输出契约

输入是 `DecodedEnvelope` 流与 source profile mapping。输出为可由
`ProcessedReader` 读取的 `NormalizedDataset`：

```text
NormalizedDataset
├── stream descriptors and records
├── source timestamps and clock mappings
├── calibration/frame facts
├── episodes and boundary evidence
├── source/semantic QC findings
└── provenance
```

### 当前代码映射

`representation/`、`sync/`、`calibration/`、`episode/`、`qc/`、`metadata/` 和
`ProcessedReader` 已提供 MVP。主要缺口是：

- typed descriptor 仍把 collection mode 和 semantic role 放在 extensions；
- clock domain 目前多为 `unknown`，同步只有单一 nearest policy；
- 缺失相机标定时不能支持需要三维几何的用途；
- whole-recording episode 只是当前 profile 的候选策略；
- QC 仍混合 source facts 与用途验收，尚无 validity mask 的完整落盘流程。

## 6. 第 4 层：用途策略与本地产物

### 职责

第 4 层不重新解码 raw。它读取第 3 层数据，以 purpose profile 选择处理、容错和验收
策略。每个 policy 产生独立本地输出和 QC，不覆盖标准化数据。

```text
archival
  -> checksums, inventory, provenance completeness

exploration
  -> preview index, downsampled trajectory, summary statistics

learning_readiness
  -> reference windows, masks, observation/action semantic checks

retargeting
  -> frame mapping, IK/constraints, separately named retargeted_action

control_evaluation
  -> command/feedback pairing, latency and tracking error
```

当前优先落地 `archival` 和 `exploration`。`learning_readiness` 只建立读取与验收接口；
没有可靠 action 时必须输出不满足条件，而不是制造 action。Retargeting 和 control
evaluation 保留接口，只有在来源证据满足时实现。

### 输入与输出契约

输入是 `NormalizedDataset`、purpose profile 和本地输出目录。输出为：

```text
PurposeRun
├── purpose profile + version
├── selected episodes/streams
├── generated local artifacts
├── purpose-specific QC and validity masks
├── derivation/provenance links
└── structured status/error
```

用途 policy 不能把 warning 静默变为 pass，也不能覆盖第 3 层的 source/semantic QC。
它只能声明某项 finding 对本用途是允许、降级还是拒绝。

### 当前代码映射

`archival` 与 `exploration` 已实现独立 PurposeRun manifest、QC、status、provenance、
validity mask 和本地产物。它们只读取 normalized dataset，不重新解码 raw，也不覆盖
processed run。`learning_readiness`、`retargeting` 和 `control_evaluation` 当前明确返回
`purpose_unsupported`，这是符合当前阶段边界的。

## 7. 本地目录边界

Raw 保持不可变；每个 normalized run 和 purpose run 使用新目录：

```text
data/
├── raw/<source>/<recording>/...
├── processed/<recording>/<run_id>/
│   ├── data/streams/
│   ├── data/assets/
│   ├── data/episodes/
│   ├── calibration/
│   ├── metadata/
│   │   ├── source_inventory.json
│   │   ├── profile_decision.json
│   │   ├── timestamp_mapping.json
│   │   ├── provenance.json
│   │   └── processed_manifest.json
│   └── qc/
│       ├── source_qc.json
│       └── semantic_qc.json
└── purpose/<recording>/<purpose>/<run_id>/
    ├── artifacts/
    ├── validity_masks/
    ├── purpose_qc.json
    └── purpose_manifest.json
```

Phase 1 的 `storage/` 只负责这些本地路径和 reader/writer interface；不得导入云 SDK。

## 8. 配置模型

一次本地 processing run 的配置逻辑上分成四段。当前 source/processing 由 process
入口消费，purpose 使用单独 profile 配置和 `embody-data purpose` 命令：

```yaml
source:
  path: data/raw/genrobot-realomin/.../01708.mcap
  container: mcap
  profile: genrobot_realomin_mcap

collection:
  mode: human_wearable
  semantic_evidence: documented_source_profile

processing:
  reference_timeline: camera0
  synchronization_policy: nearest
  calibration_policy: preserve_and_validate
  episode_policy: whole_recording

purpose:
  profile: archival_and_exploration
  missing_calibration: warn_for_preview
```

用户显式配置可以确认 profile，但不能用来伪造来源中不存在的机器人反馈。

## 9. 当前 RealOmin 状态基线

截至 2026-09-24，本地状态为：

- acquisition 已成功固定 revision `fcbc0d38550e134f273426aa7c9cc2b491270bc4`，
  本地存在 `01706.mcap`、`01707.mcap` 和 `01708.mcap`，总计 169,619,631 bytes。
- `01708.mcap` 已跑通 inspect、decode/normalize、sync、calibration validation、
  whole-recording episode、QC 和 processed manifest。
- 输出 8 条标准化流：左右两侧 camera、IMU、magnetic encoder 和 EEF pose。
- collection mode 为 `human_wearable`；EEF pose 是 `observed_device_pose`，magnetic
  encoder 是人体操作设备的观测；不输出通用 robot action。
- 4 个 RobotInfo/SystemInfo topic 被保留在 inventory，但在 v2 中明确记录为
  `not_in_phase1_mvp_mapping`。
- 当前 QC 为 `fail`：缺少 `camera_calibration`；另有 4 个 IMU/gripper stream 的
  coordinate frame 为 unknown。这个结果不阻止归档，但阻止依赖完整三维几何的用途。

## 10. 实施顺序与完成标准

### A. 固化第 1–2 层边界

- 已增加 typed `SourceInventory`、`ProfileDecision` 和 collection-mode evidence。
- 已建立 inspector、profile matcher 和 decoder adapter registry，使 CLI 和 pipeline
  不依赖 GenRobot 函数名或 `.mcap` 扩展名。
- 已贯通 stream/time-range selective decode。
- 用 synthetic fixture 覆盖未知 schema、profile ambiguous 和 decode failure。

完成标准：新增来源只需 reader/decoder/profile mapper，不修改通用 sync、episode、QC
和 reader。

### B. 固化第 3 层语义核心

- 将 collection mode、semantic role、frame 和 calibration identity 升为 typed 字段。
- 将 source QC、semantic QC 与 policy verdict 分开。
- 增加 clock reset/gap、missing topic、tracking loss 和 validity mask fixture。
- 为同步策略建立 registry，但只实现当前样本确实需要的策略。

完成标准：第 3 层输出不需要 vendor decoder 即可被 reader 解释，并完整保留来源时间
与语义证据。

### C. 实现第 4 层最小闭环

- 先实现 `archival` 与 `exploration` purpose profile 和 PurposeRun manifest。
- 让缺少 calibration 等 finding 根据用途得到独立 verdict。
- 保留 learning-readiness、retargeting 和 control-evaluation interface；不提前实现模型
  训练、IK 或机器人控制。

完成标准：同一 normalized run 可生成至少两个互不覆盖的本地 purpose run，且每个
run 有配置、结构化状态、QC、provenance 和可复现测试。
