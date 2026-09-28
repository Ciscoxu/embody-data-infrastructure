# Python 文件用途说明

本文解释 `src/embody_data/` 下各 Python 文件的职责、主要输入输出和模块边界。
阅读代码时建议从 `__main__.py`、`cli/main.py` 和 `processing.py` 开始，再沿四层
Pipeline 进入具体模块。

## 顶层入口与公共基础

### `src/embody_data/__init__.py`

定义 Python package 的基础信息和版本号。其他模块通过这里读取 `__version__`，用于
provenance、acquisition status 和 purpose run 元数据。它不承担 Pipeline 编排。

### `src/embody_data/__main__.py`

支持 `python -m embody_data`。文件只把执行转交给 `cli.main.main()`，不包含业务逻辑。

### `src/embody_data/processing.py`

Phase 1 四层 Pipeline 的主编排入口。

- 输入：Raw recording、独立输出目录、processing config。
- 顺序：inspect/profile decision → adapter dispatch → decode/normalize → sync →
  calibration → episode → QC → manifest/provenance。
- 输出：`data/processed/<run>/` 下的标准化 streams、assets、metadata、QC 和 masks。
- 根据 inspection 得到的 Source Profile 动态读取 container、encoding、collection mode、
  trajectory semantics 和 semantic assumptions，不绑定特定厂商或容器。
- 兼容入口：`process_genrobot_mcap()` 保留旧调用方式，内部转向通用
  `process_recording()`。

该文件负责调用阶段，不应包含厂商 Protobuf 字段解析、具体 QC 规则或云存储逻辑。

### `src/embody_data/config.py`

读取 JSON、TOML，以及安装 YAML extra 后的 YAML 配置。负责格式校验和结构化配置
错误，不解释 source、sync 或 purpose 的业务含义。

### `src/embody_data/errors.py`

定义 `EmbodyDataError`，统一携带稳定 error code、用户可读消息和结构化 details。
CLI 和各处理阶段通过它返回可机器消费的失败原因。

### `src/embody_data/status.py`

定义 operation state 和时间戳模型，用于记录 running、succeeded、failed 等状态。
状态文件是输出契约的一部分，不替代 QC。

### `src/embody_data/logging.py`

配置普通/verbose 日志，并提供结构化事件日志辅助函数。日志用于诊断，不作为正式
数据产物或成功判据。

## CLI

### `src/embody_data/cli/__init__.py`

标识 CLI package。目前不承载业务逻辑。

### `src/embody_data/cli/main.py`

定义 `embody-data` 命令行解析和顶层异常边界。

- `source-list`、`acquire` 调用 acquisition。
- `inspect` 调用 ingestion。
- `process` 调用 `processing.process_recording()`。
- `purpose` 调用 `purpose.run_purpose()`。
- `validate`、`describe` 读取现有结构化产物。

它负责参数和退出码，不应直接实现 decoder、同步算法或 QC 规则。

## 数据获取：`acquisition/`

### `src/embody_data/acquisition/__init__.py`

公开导出 Hugging Face 文件列举和获取函数。

### `src/embody_data/acquisition/huggingface.py`

负责 RealOmin gated dataset 的有限额、本地、可恢复 acquisition。

- 列举远程 MCAP 和 revision。
- 按显式路径、文件数量和总字节数选择样本。
- 支持 dry-run、resume 和 SHA-256。
- 输出 `acquisition_status.json`。
- 将权限问题记录为 `blocked_auth`。

该模块只负责把 source object 安全落到 `data/raw/`，不解码 recording，也不把 token
写入配置或 manifest。

## 第 1 层：来源发现与分类

### `src/embody_data/ingestion/__init__.py`

公开导出 inspector registry/dispatch、通用 `inspect_raw()` 和当前 MCAP inspector。

### `src/embody_data/ingestion/base.py`

定义可扩展的 inspection 边界：

- `InspectionAdapter` 负责基于 source 内容判断是否匹配并执行专用 inspection；
- `register_inspector()` 注册 inspector；
- `resolve_inspector()` 检测无匹配和多匹配并返回结构化错误；
- `inspect_recording()` 是 processing 使用的格式无关入口。

### `src/embody_data/ingestion/inspect.py`

对普通文件或目录执行轻量 inventory。

- 遍历文件并计算 SHA-256。
- 生成 `RawManifest`、checksum 和 operation status。
- 不完整解码媒体或消息 payload。

### `src/embody_data/ingestion/mcap_inspect.py`

对 MCAP 做流式 discovery，并生成第 1 层核心产物。

- `McapInspectionAdapter` 通过 MCAP magic bytes 匹配内容，不依赖文件扩展名。
- 收集 schema、topic、message count、时间范围和频率。
- 汇总 log、publish、header timestamp 与 clock evidence。
- 调用 source profile 内容指纹判断。
- 输出 `source_inventory.json`、`profile_decision.json`、`topic_summary.json` 等。

未知 MCAP 保持 `unknown_mcap`，不会继承 GenRobot 的 collection mode 或 rights。

### `src/embody_data/metadata/__init__.py`

公开导出 metadata typed models，供 ingestion、processing 和下游代码使用。

### `src/embody_data/metadata/models.py`

定义来源发现阶段的类型化数据契约：

- `RawManifest` / `FileRecord`；
- `SourceInventory` / `SourceStreamInventory`；
- `ProfileDecision` / `ProfileCandidate`；
- `CollectionModeDecision` / `ClassificationEvidence`；
- `ClockEvidence` / `RightsMetadata`。

这里只描述事实和决定结果，不执行文件扫描或厂商字段解析。

### `src/embody_data/metadata/source_profiles.py`

定义 source profile 及其分类证据。

- `SourceProfile` 同时保存 container、encoding、collection mode、轨迹语义、语义假设和
  rights 默认值。
- profile matcher 通过 registry 根据 container、schema encoding 和 stream 内容生成候选。
- `resolve_source_profile()` 为 processing 和 ingestion 提供统一解析入口。
- 对 confirmed、ambiguous、unknown profile 做明确决策。
- 只有已确认的 RealOmin profile 才声明 `human_wearable`。

## 第 2 层：来源适配与解码

### `src/embody_data/decode/__init__.py`

公开 adapter registry、decode request、MCAP reader 和已注册的 GenRobot adapter。
导入该模块时会完成首个 adapter 的注册。

### `src/embody_data/decode/base.py`

定义通用 decoder/adapter 边界。

- `AdapterKey` 使用 container、encoding、source profile 选择 adapter。
- `DecodeRequest` 描述 raw path、输出目录、stream 过滤和时间范围。
- `register_adapter()`、`resolve_adapter()`、`dispatch_decode()` 管理 dispatch。
- 未注册组合返回结构化 `decoder_not_found`。

新增来源优先扩展这里的 registry，而不是在 `processing.py` 中堆叠文件名判断。

### `src/embody_data/decode/mcap.py`

负责 MCAP transport 和 embedded schema 解码。

- 流式迭代消息，避免一次性载入整个 recording。
- 支持 topic 和 log-time 范围过滤。
- 保留 channel/schema、log time、publish time。
- 提取可用的 header timestamp、sequence ID 和 frame ID。

该文件不知道 GenRobot topic 的业务语义。

### `src/embody_data/decode/genrobot.py`

实现 `genrobot_realomin_mcap` adapter。

- 使用 MCAP embedded Protobuf schema 解码。
- 按 source profile 选择支持的 topic。
- 将 camera payload 写为 H.264 asset，并在 JSONL 中保存 offset/length 引用。
- 标准化 IMU、magnetic encoder、pose 和 camera calibration。
- 保留 vendor message、所有来源时间戳和结构化 decode failures。
- 可选使用 PyAV 做有限 H.264 解码验证。

它不执行同步、episode 切分、用途策略或 action retargeting。

## 第 3 层：通用语义处理核心

### `src/embody_data/representation/__init__.py`

公开通用 stream/record 类型和 GenRobot topic mapping 函数。

### `src/embody_data/representation/stream.py`

定义 vendor-neutral `StreamDescriptor` 和 `NormalizedRecord`。

每条流显式携带 modality、unit、dtype、shape、clock domain、collection mode、semantic
role、frame、transform direction、calibration ID、validity、confidence 和来源字段。

### `src/embody_data/representation/genrobot.py`

把 GenRobot topic 映射到通用 descriptor。

- camera → visual observation；
- IMU → observation；
- magnetic encoder → `observed_human_motion`；
- VIO EEF pose → `observed_device_pose`。

这里明确阻止 topic 中的 `robot0` / `robot1` 被误解释为机器人执行证据。

### `src/embody_data/sync/__init__.py`

公开时间同步接口 `synchronize()`。

### `src/embody_data/sync/alignment.py`

建立 source timestamp 到 reference timeline 的 nearest mapping。

- 保留原始时间戳，不覆盖 source data。
- 输出 reference index、reference timestamp、error 和 valid 标志。
- 统计 coverage、duplicate、non-monotonic、gap 和频率。

当前没有自动估算跨时钟 offset/drift。

### `src/embody_data/calibration/__init__.py`

公开 calibration validation 接口。

### `src/embody_data/calibration/validation.py`

验证相机内外参数组长度、有限数值、四元数归一化和 transform direction。缺失或未知
信息形成结构化 finding，不会自动填入单位矩阵。

### `src/embody_data/episode/__init__.py`

公开当前 episode derivation 策略。

### `src/embody_data/episode/recording.py`

把一个完整 recording 建成候选 episode，并记录边界策略和假设。它适用于当前
RealOmin MVP，但不是所有 ROS Bag 或长视频来源的通用切分规则。

### `src/embody_data/qc/__init__.py`

公开 source QC、semantic QC、aggregate report 和 validity mask 接口。

### `src/embody_data/qc/report.py`

生成分层 QC：

- Source QC：decode failure、时间戳、同步覆盖率、视频可用性。
- Semantic QC：required modality、pose、gripper range、frame 和 calibration。
- Aggregate QC：保留两类 findings，并生成整体 verdict。

QC 只报告事实与严重性，不静默删除数据。

### `src/embody_data/qc/masks.py`

按 stream 和 source sample 生成 validity mask。当前整合同步阈值失败和 source 明确
标记的 invalid 状态，并保留 reason codes。

## 第 4 层：用途策略

### `src/embody_data/purpose/__init__.py`

公开 purpose profile、run model 和 `run_purpose()`。

### `src/embody_data/purpose/models.py`

定义 `PurposeKind`、`PurposeProfile` 和 `PurposeRun`。

- 支持 `archival`、`exploration` 枚举。
- 为 learning readiness、retargeting、control evaluation 保留明确名称。
- 校验 purpose config，并对无效配置返回结构化错误。

### `src/embody_data/purpose/runner.py`

从既有 processed dataset 生成独立 PurposeRun。

- `archival` 生成完整文件 inventory、size 和 SHA-256。
- `exploration` 生成 preview index 和数值摘要。
- 保留 normalized QC findings，并按用途产生独立 disposition/verdict。
- 记录 provenance，证明没有重新解码 raw，也没有修改 processed run。
- 未实现用途返回 `purpose_unsupported`。

## 本地存储与 Reader

### `src/embody_data/storage/__init__.py`

公开 `ProcessedReader`、`PurposeReader` 和 purpose layout。这里只暴露本地接口，不
绑定云 provider。

### `src/embody_data/storage/layout.py`

定义一个 processed run 需要创建的本地目录，包括 streams、assets、episodes、derived、
calibration、metadata、QC 和 validity masks。

### `src/embody_data/storage/reader.py`

读取 `processed_manifest.json`，列举 stream、迭代 JSONL record，并读取 episode。
下游使用它时无需导入 MCAP 或 GenRobot decoder。

### `src/embody_data/storage/purpose.py`

定义 PurposeRun 的目录布局和 `PurposeReader`，用于读取 purpose manifest、QC、status、
provenance 和 artifact paths。

## 测试文件

### `tests/fixtures/genrobot_fixture.py`

在测试期间生成小型 synthetic Protobuf MCAP。它代替大型 gated source，用于验证正常
记录、错误 payload、筛选和端到端行为。

### `tests/unit/`

- `test_acquisition.py`：远程选择、限制、resume 和状态。
- `test_config.py`：配置加载和错误处理。
- `test_decode_registry.py`：adapter 注册、dispatch 和选择性解码。
- `test_genrobot_profile.py`：RealOmin human-wearable 语义。
- `test_purpose.py`：purpose profile、QC 和 unsupported purpose。
- `test_source_discovery.py`：内容签名 inspector dispatch、profile registry/decision 和 inventory。
- `test_status.py`：结构化 operation status。
- `test_sync_calibration_qc.py`：时间映射、calibration、分层 QC 和 masks。

### `tests/integration/`

- `test_inspect_cli.py`：CLI inspect 和结构化 discovery 产物。
- `test_genrobot_pipeline.py`：Synthetic MCAP 完整 processed flow。
- `test_four_layer_cli.py`：四层 dispatch、QC、mask 和 purpose CLI。
- `test_purpose_runs.py`：同一 processed run 派生隔离的 archival/exploration runs。

## 推荐阅读顺序

```text
__main__.py
  -> cli/main.py
  -> processing.py
  -> ingestion/base.py
  -> ingestion/mcap_inspect.py
  -> metadata/source_profiles.py
  -> decode/base.py
  -> decode/genrobot.py
  -> representation/stream.py
  -> sync/alignment.py
  -> calibration/validation.py
  -> episode/recording.py
  -> qc/report.py + qc/masks.py
  -> storage/reader.py
  -> purpose/runner.py
```

如果新增一种原始容器或来源，依次扩展 `ingestion/base.py` 的 inspector、
`metadata/source_profiles.py` 的 profile/matcher、`decode/base.py` 的 adapter，以及对应
representation mapper；不要在 `processing.py` 中增加格式分支。如果新增一种下游用途，
优先阅读 `storage/reader.py`、`purpose/models.py` 和 `purpose/runner.py`。
