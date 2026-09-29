# 子 TRD E｜Web 工作台、会话与集成（10 人日）

**输入：**冻结的 Tool/PlanningAnswer/CourseOffering DTO 和 A/B/C/D 的固定 fixture。**所有权：**`web/` 的 Vue 3 + Vite 页面与 API client、端到端演示脚本/集成文档；不复制 Java 规则或 Benchmark 评分。首版为响应式**网页**，不做微信小程序。

## 要回答的问题与实现顺序

1. **学生怎么输入？** Vue 单页提供路径选择、已修课程编辑、自然语言目标和本地匿名 session；用 Fetch 调 Python `POST /api/v1/planning`。手机浏览器可用。录入真实学生成绩前需另做账号/隐私设计，课程演示用虚构/授权数据。
2. **班次快照怎么进来？** 首版仅导入清楚标记 `SYNTHETIC` 的测试 JSON，页面显著展示“模拟班次，非真实开课”；未来才接 A 的只读 Adapter，由用户主动导出并预览真实快照。不要求学生把 Cookie/Token 粘贴进页面，不触发官方系统写操作。
3. **怎样清楚显示可信度？** 结果按已核验、建议、未知、系统错误四区展示；SourceRef、`curriculumSnapshotId/offeringSnapshotId`、班次新鲜度、`parseStatus` 可查看。`OFFERING_UNAVAILABLE/SNAPSHOT_STALE` 时不得出现绿色“无冲突”。重规划保留上轮目标和 Trace 链接。
4. **版本如何可见？** 展示当前稳定 `harnessVersion` 与 Benchmark 的候选晋级/回滚摘要；给老师演示 v0/v1/v2 lineage、质量和 Token/工具次数对照图，但不在页面自行重算评分。Trace 只展示脱敏事件和 Tool 引用。

## 交付与验收

先用固定 DTO 完成页面，再接 C 的 FastAPI 和 A/B 的真实导入；完成“选路径→填已修→提问→核验→澄清/改目标→查看来源/版本”全链路。测试无真实班次/模拟快照、Java ERROR、模型超时、上传非法 JSON、未知时间、候选 rollback 的文案与状态。每周保留可演示主线，W5 录制或现场演示成功与失败两个 case。

**依赖：**A 快照格式、B 导入与 Tool、C PlanningAnswer、D 版本报告。**学习入口：**[Vue 官方 create-vue](https://github.com/vuejs/create-vue)、[Vue 文档](https://vuejs.org/guide/quick-start.html)、[Vite](https://github.com/vitejs/vite) 的最小项目。
