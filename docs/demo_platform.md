# 一个月 Demo Platform：本地实验入口

这个 Demo 是 Phase 1 处理核心外的一层薄界面。它不复制 raw、不实现云上传，也不把
human/device trajectory 宣称为 robot action。每个 recording 必须显式声明
`human_wearable`、`teleop_device_only` 或 `teleop_robot`。

## 快速运行

在已安装项目开发依赖的环境中：

```powershell
python demo/generate_sample.py
python -m demo.app --workspace .local/demo-platform
```

脚本会同时生成 `.local/demo-sample/fixture.mcap` 和合法的
`.local/demo-sample/folder_bundle_v1/`。打开 `http://127.0.0.1:8765`，任选其一登记；
对应输入类型选 `mcap` 或 `folder_bundle_v1`，采集模式选 `human_wearable`，然后点击
“启动处理”。页面会显示 processing stages、QC 和 processed manifest；完整产物保存在
`.local/demo-platform/projects/project-demo/recordings/<recording-id>/runs/<run-id>/`。

Demo workspace 只保存 catalog 和新的 run 产物。表单中的原始路径仅被引用和读取，
不会被移动、重命名或覆盖。每次处理生成新的随机 `run-id`，因此不会覆盖旧 run。

## 输入能力

- `mcap`：调用现有 `process_recording`，当前只有能被注册 inspector/profile/decoder
  确认的 GenRobot RealOmin 型 MCAP 能完成完整处理。source profile 确认出的 collection
  mode 必须与用户声明一致。
- `folder_bundle_v1`：通过平台已注册 adapter 完成 MP4、pose CSV、gripper CSV 和
  calibration JSON 的 normalization、同步、episode、QC 与 manifest。`recording.json`
  必须显式提供 collection mode、语义证据、clock domain、单位和 frame。

网页只调用 `PlatformService`；以后增加其他 adapter 时，网页与 catalog 合同无需重写。
当前 bundle 边界是：

```text
recording/
  recording.json
  video.mp4
  imu.csv
  pose.csv
  gripper.csv
  calibration.json
```

具体必选字段、timestamp/clock domain、frame/unit 和 action semantics 应由正式 source
profile 定义，而不是由 Demo 页面硬编码。

## 当前限制

- 这是单机、单用户、同步执行的实验入口；没有登录、队列、取消和重试。
- 浏览器表单使用本地路径，不负责上传大文件。
- catalog 使用 JSON 文件，不是 Phase 2 数据库。
- `teleop_robot` 仍需 source profile 和同步 robot feedback 证据；用户选择不能替代证据。
- folder bundle 当前只支持已定义的 v1 CSV/JSON 合同，不支持任意厂商目录结构。

## 第一批界面

Demo 首批固定为六个工作区：`Overview`、`New Ingest`、`Transfer / Integrity`、
`Recording Detail`、`Pipeline Run` 和 `QC & Artifacts`。Transfer 页面当前只展示本地
source reference、对象清单与 checksum，不声称已经完成云上传。

## 后续计划（本批不实现）

- Phase 2：upload、断点续传、对象存储、后台队列、retry/cancel 与 catalog 查询。
- Phase 3：稳定 dataset schema、annotation、statistics/split 与 frozen release。
- Phase 4：客户 scope、rights gate、安全交付、验收与撤销。
- ROS Bag、live capture、vendor private、LeRobot 与 RLDS 继续保留 adapter 接口；只有
  完成 `probe/describe/process` 合同和语义验证后才标记为 implemented。
