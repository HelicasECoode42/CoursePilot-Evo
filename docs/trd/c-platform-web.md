# 子 TRD C｜Java Tool API、存储与 Vue 单页（12 人日）

**目标：**把 A/B 的数据和规则通过版本化 HTTP API 提供给 D，并给学生一个能演示完整场景的 Web 页面。展示层明确是**网页前端，不是微信小程序**。

## 技术与文件

Java 21、Spring Web、Bean Validation、Spring Data JPA、MySQL 8、Flyway、JUnit；前端 Vue 3 + Vite + Fetch。建议负责 `java-environment/.../api/`、`persistence/`、`db/migration/` 和 `web/src/`。不在 Controller 里重复 B 的规则。

## 做法

1. Docker Compose 启动 MySQL；Flyway 建 `snapshot/course/requirement/completed_course/verification_result` 表。开发演示允许虚构学生 session，不实现学校统一认证。
2. 实现 `GET /api/v1/snapshots`、`GET /api/v1/courses`、`POST /api/v1/requirements/audit`、`POST /api/v1/recommendations/validate`。全部带 `schemaVersion/requestId/snapshotId/status/provenance`；缺数据用 `UNKNOWN`，参数错用 4xx，服务故障用 5xx。
3. 第 2 周先用固定 JSON 让 API 可调；再接 A/B 的真实实现。生成或手写 OpenAPI 样例，给 D `httpx` 客户端照着调用。
4. Vue 单页做四块：路径与快照选择、已修课编辑、自然语言目标、结果卡片。结果卡片分“已核验/建议/未知”，每条已核验事实显示来源工作表/行。用户请求时显示加载与错误重试。
5. 浏览器只调 D 的 FastAPI `POST /api/v1/planning`，不直接调用 LLM；快照列表可以经 Python 代理。把 Agent Trace 做折叠面板，不把模型完整思维链展示给用户。

## 验收

Java API 能用固定 fixture 和真实快照各跑一次；无效路径、错快照、空课程代码有清晰错误。网页能完成“选路径→填已修→提问→展示核验/未知→改目标再问”；手机浏览器正常换行。没有班次时不出现课表日历或“周五空课成功”。

**学习入口：**[Spring REST](https://github.com/spring-guides/gs-rest-service)、[Spring Data JPA Guide](https://github.com/spring-guides/gs-accessing-data-jpa)、[Vue 官方 create-vue](https://github.com/vuejs/create-vue)。
