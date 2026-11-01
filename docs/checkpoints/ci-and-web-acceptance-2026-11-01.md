# CI 与学生网页验收

日期：2026-11-01。Luna 修改集成检查和两处页面状态；主 Agent 独立复核并执行浏览器验收。另一名 Luna 只读复核，不参与实现。

## 失败原因

用户指定运行：41285884865，main 提交 ebe49cd7dfb309200b4fe48abee329fa72bd63b9。

已使用该提交的 Java 原始代码、独立 8088 端口和内存数据库复现：POST /api/v1/academic-records 返回 500，Issue 为 INTERNAL_ERROR，原因为 HttpRequestMethodNotSupportedException。main 未包含 AcademicRecordController；POST 不受支持的异常被通用处理返回 500，Python ToolClient 将其映射为 503 TOOL_UNAVAILABLE。本地分支已包含学业记录聚合与端点，写入可返回 201。复现服务已停止。

另有检查器问题：输入校验仍按旧 Envelope 状态判断、记录写入失败后继续使用示例记录 ID、浏览器断网/未知场景缺少隔离路由、首页操作仍按旧按钮定位。CI 没有配置真实模型，需显式执行受控模型回归，不能将其视为真实模型质量验收。

## 页面修复

- 学业文件保存成功后，提示保存课程数与分类数，关闭导入弹窗并显示学校进度。
- 保存中与失败提示仍位于打开的 modal 内；成功提示位于弹窗外。保存成功但核对失败单独说明，不宣称核对已完成。
- 删除最后一门课后隐藏课表和班次加载提示，展示空方案状态。

## 独立浏览器验收

保留用户的 Java8081/Python8000/Web5173 会话。受控验收单独使用 Python8002/Web5177，Java 继续使用真实 HTTP 与 H2；未调用付费模型。

使用明确标记为 SYNTHETIC 的学校进度文件与 PLAN_CS_2025 合成培养方案：专业选修样本要求8、已获4、剩余4，CS101标记PASSED。该文件仅用于验证导入协议与交互，不是学生真实学业资料。

已操作并观察：

1. 首页进入连接流程，选择合成培养方案后上传样本。
2. PUT school-progress 和 POST audit 均返回200；学校分类与8/4/4学分原值显示在页面。
3. 完成目标、偏好、兴趣、教师、时间、优先级及资料确认引导。
4. 进入学分选课，已通过CS101不在可选列表中；手选CS102，确认页保留所选课程。
5. 受控模型生成方案，结果页显示CS102、课程卡片与UNKNOWN原因，并标注演示模型。
6. 从网页删除最后一门课，POST remove-course 返回200，新方案为空，旧核验不作为当前判决显示；修复后空方案无课表加载提示。
7. 重复上传相同文件后仍只有一条已选记录、一个课程行；显示保存成功提示，弹窗自动关闭。

本轮文件导入与扩展回传共用保存函数，但没有重新登录学校验证扩展采集与跨标签页回传。真实模型咨询与正式规划的两次实测见 docs/34，本轮受控回归不增加真实模型成功次数。

## 恢复

修改前 checkpoint：refs/checkpoints/coursepilot/20261101T135040700103Z-ci-repair-before，8e244c4a5a45172f1dfac208d78d858a18adc313。运行配置、数据库及临时验收资料不纳入代码 checkpoint。

## 正式构建

以 VITE_API_BASE_URL=/ 构建，使用 vite preview 监听本机5181，代理到已有Python8000。浏览器进入 /me 后成功建立会话、读取计算机科学与技术（直招）真实培养文件目录并展示对话入口；控制台无 error。该检查没有调用模型。临时预览服务已停止，原5173服务保留。

## 自动化结果

最终受控服务回归使用 API8002、Java8081、Web5177，显式 PLAN_CS_2025 / SIMULATION / PIN_COURSE CS102；原真实模型API8000未参与此回归。没有停止或重启原服务。

| 检查 | 结果 |
| --- | --- |
| integration 全量单元与集成测试 | 110 passed |
| 主链路：会话、记录、核对、规划、重规划幂等 | PASS 5/5 |
| 异常覆盖：核对、无班次时间结论、非法输入、无权限 | PASS 4/4 |
| 实际 Chromium 浏览器回归 | PASS 7/7 |
| Web 全量 | 440 Vitest、26 独立 HTML 测试通过；两份 HTML 检查通过 |
| Web 静态检查与构建 | lint、typecheck、build 通过；最终记录条数文案另有6项定向测试通过 |
| Python/Java 业务代码 | 本轮未改；同一代码此前复查255/205项通过 |
| 契约 | 3份Schema/OpenAPI、引用、25个正反例通过 |

浏览器七项包含文档、入口脚本、挂载、隔离断网提示、完整引导提交后的 UNABLE_TO_VERIFY、受控正常引导及390px窄屏。断网用浏览器路由中止API请求，未停止真实Python；两种受控响应均使用独立随机端口。已安装官方Playwright1.52所需的Chromium headless shell完成实跑。

检查器修改保留默认严格模式：FAKE_MODEL仍判DEGRADED；只有显式 --controlled-model 才按受控接线回归判定，而且方案必须含明确选择的课程。该参数不证明真实模型质量，也不会把CLARIFY/UNABLE_TO_VERIFY判为主链路成功。浏览器的未知结果是单独的预期业务场景。

CI workflow 已改为显式受控模型回归，但修改尚未推送，GitHub 原运行仍为 failure。此处通过的是本地最终代码与实际服务，不声称远端已重跑通过。

实跑日志（本机临时文件）：/private/tmp/coursepilot-stack-check-final.log、coursepilot-smoke-check-final.log、coursepilot-web-check-final.log、coursepilot-integration-final-tests.log。日志不纳入公开提交。修改与证据随后保存为代码checkpoint，原学业数据和密钥仍由忽略目录保存。

最终代码 checkpoint：refs/checkpoints/coursepilot/20261101T141848521923Z-ci-web-accepted，90cddf8537e6ac9f7ac44a3fa01c61264c80b52e。临时8002/5177/5181/8088验收服务均已停止，原8081/8000/5173保留。
