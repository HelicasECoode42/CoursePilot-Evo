# 本地运行与 GitHub 仓库核对

核对日期：2026-11-01。代码审核由 Luna 执行，主 Agent 检查 Actions 日志、启动服务并进行浏览器与 HTTP 验收。

2026-11-02 更新：[PR #51](https://github.com/HelicasECoode42/CoursePilot-Evo/pull/51) 已合并到 `main`，合并提交为 `d6380364375f835da3abb6e04cc7a0e6c4d48a87`。下文版本差异与失败记录对应修复前的检查。合并前的同一分支提交已通过[项目检查](https://github.com/HelicasECoode42/CoursePilot-Evo/actions/runs/41365658939)和[集成检查](https://github.com/HelicasECoode42/CoursePilot-Evo/actions/runs/41365772637)。

## 版本

- 本地基线：`feat/b-contract-endpoints`，`7f6bb436ace6f50c4b70f73389095c8bc5d32394`。
- 所查 Actions 的 main：`ebe49cd7dfb309200b4fe48abee329fa72bd63b9`。
- 本地基线比该 main 多 40 个提交。学校进度导入、AI 对话、界面与运行保护等改动尚未全部进入 main。没有合并或推送。
- 本轮开始时工作区干净；本轮修改仅为 README 和本核对文档。

## GitHub Actions

[运行 41285884865](https://github.com/HelicasECoode42/CoursePilot-Evo/actions/runs/41285884865) 的 `stack-integration` 最终为 failure。

| 检查 | 日志结果 | 判断 |
| --- | --- | --- |
| 服务启动 | Java、API、Web READY | 仅就绪检查通过 |
| 学业记录 | 503 TOOL_UNAVAILABLE | 已在 main 隔离复现：Java 缺少 POST 端点，405 异常落入通用处理成为 500，Python 映射为 503 |
| 核对与规划异常覆盖 | 404 NOT_VISIBLE | 记录写入失败后未获得有效记录，检查仍有使用示例 ID 的路径 |
| 非法输入 | 实际 422 INVALID_INPUT，脚本期待 ERROR | 检查器判定未跟随契约；本地版本已经接受 INVALID_INPUT |
| 浏览器 | api_down 失败或 BLOCKED、unknown BLOCKED | 编排缺少对应隔离上游，且页面操作需按当前导航复核；尚未通过 |

日志中的“全链路检查步骤 success”不能代表整体通过：子步骤设置了 continue-on-error，最终门禁读取 outcome 后失败。检查脚本没有把失败改为通过。

本地 API 子进程已经有配置文件变量注入；main 中缺少此映射。不过该次 CI 已通过 workflow 环境变量提供 Java URL 和密钥，不能仅凭映射缺失认定其为本次 503 原因。后续使用 main 原始 Java 代码、独立 8088 端口和内存数据库复现，原始响应为 500 INTERNAL_ERROR，message 为 HttpRequestMethodNotSupportedException: Request method POST is not supported；该 main 未包含 AcademicRecordController。临时复现服务已停止。

## 本地验收

服务使用本机已有私有配置，仅监听回环地址：Java 8081、Python 8000、Web 5173；没有开启公网隧道。启动需要允许本机端口监听的执行环境。

浏览器实际完成：首页 → 连接学业资料 → 学校导入弹窗 → 我的学业 → 真实模型咨询 → 加入待选 → 七步引导 → 确认页 → 返回对话。确认页显示 Java程序设计(实践) 08306099 为已选课程。

本轮浏览器会话没有导入个人学校资料。模型明确说明缺少学业记录、无法排除已修；推荐课程显示学分与理由，未查询评价的课程显示“尚未查询评价”。没有把此会话称为完整的个人规划验收。

独立 HTTP 验收会话使用空课程记录并明确 transcriptComplete=false：学业记录写入 201，真实模型规划 200 / RECOMMENDATIONS，返回 Java程序设计(实践)、软件测试、软件项目管理三门课；核验 UNKNOWN。删除首门课程返回 200，新 planId 与原方案不同，结果不含目标课程，保留两门。该路径经真实 Java 和数据库，不使用学生个人成绩。网页本身不允许提交空记录，因此此部分为 HTTP 验收。

本轮共调用真实模型两次：网页咨询一次、HTTP 正式规划一次。规划用量为 input 2768、output 1123，工具调用 6 次，耗时 9571ms。没有自动重试。

| 本地检查 | 结果 |
| --- | --- |
| Java 全量测试 | 205 通过，0 失败、0 错误；独立内存库 |
| Python Agent | 255 通过；此前本次进度复查运行，代码未变 |
| Web | 439 通过，独立 HTML 26 通过；类型检查、构建通过；此前本次进度复查运行，代码未变 |
| integration | 97 通过；需要允许创建本机临时 HTTP 服务 |
| benchmark | 56 通过、1 跳过 |

首次从仓库根目录联合执行 integration/benchmark 时导入路径不符，未完成收集；改为各模块目录入口。integration 首次执行因环境禁止绑定端口产生 10 个 setup error，允许本机监听后全量通过。上述环境问题未作为代码缺陷处理。

## 已确认问题与后续顺序

1. 先统一本地分支与 main 的交付版本，再在同一提交上执行全部门禁。
2. 修复集成检查的依赖步骤、输入状态判定和浏览器场景编排，保留对真实失败的断言。
3. 使用学生实际导入数据验收“进度 → 对话 → 采用 → 正式方案 → 删除”，核对多记录时学校进度与选中记录的对应关系。
4. 补充真实目标学期开课来源后验收换班与课表。目前课程层建议可运行，缺少班次时不能给出确定时间结论。
5. 量化真实模型成功率、证据引用与建议质量；评测、自进化及老师报告仍需补齐。

学校导入的 transcriptComplete=false 是现有契约边界；不能仅凭学校汇总推定课程明细完整。学校报告的类别缺口与本地规则核对需分别展示来源。

## README 调整

根 README 更新了实际流程、真实课程层建议与真实班次的区别，并链接本核对。Web README 更新为当前七步引导与聊天入口，修正“真实模式只能使用 VERIFIED 培养方案”的旧描述。真实模型启用仍需要本机模型配置；未配置时使用带 FAKE_MODEL 标记的实现。

## Checkpoint

修改前：`refs/checkpoints/coursepilot/20261101T133212079673Z-readme-review-before`，提交 `04df0ae6c27bd9d9c327bc0667e292ddcaaab73a`。Checkpoint 不改变分支或工作区，排除被忽略的配置和数据库。

后续已完成上述 CI 检查修复与独立浏览器验收，详细结果见[CI 与学生网页验收](checkpoints/ci-and-web-acceptance-2026-11-01.md)。旧运行保留原失败结果，修复后的检查见本文开头链接。
