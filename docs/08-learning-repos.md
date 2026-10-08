# 学习仓库与资料：按模块最小阅读

| 成员 | 一手学习资料 | 先学会的具体动作 |
| --- | --- | --- |
| A 数据 | [Apache POI](https://github.com/apache/poi)、[MDN Web APIs](https://developer.mozilla.org/en-US/docs/Web/API)、[JSON Schema](https://json-schema.org/learn/getting-started-step-by-step) | `WorkbookFactory/DataFormatter` 读旧 `.xls`；浏览器 Blob 导出；字段 Schema 校验。只分析原脚本，不直接运行其自动点击逻辑 |
| B Java | [Spring REST Guide](https://github.com/spring-guides/gs-rest-service)、[Spring Data JPA Guide](https://github.com/spring-guides/gs-accessing-data-jpa)、[Spring PetClinic](https://github.com/spring-projects/spring-petclinic) | DTO/Service/Repository 分层、JUnit、不可变快照与 UNKNOWN 错误封套 |
| C Agent | [FastAPI](https://github.com/fastapi/fastapi)、[Pydantic](https://github.com/pydantic/pydantic)、[httpx](https://github.com/encode/httpx) | 一个有界 Runner、typed 请求/响应、Java Tool 超时处理与 Harness 装载 |
| D 评测 | [GDPevo](https://github.com/Prism-Shadow/GDPevo)、[promptfoo](https://github.com/promptfoo/promptfoo)、[pytest](https://github.com/pytest-dev/pytest) | task group / train-test 分离、逐例断言、失败 Trace、候选回归和 lineage；独立实现本项目门槛 |
| E Web | [Vue 指南](https://vuejs.org/guide/quick-start.html)、[create-vue](https://github.com/vuejs/create-vue)、[Vite](https://github.com/vitejs/vite) | 单页表单、状态与错误展示、JSON 上传预览、版本/来源卡片 |

设计背景：[PhysicalRSI 项目页](https://mmlab.hk/research/PhysicalRSI) 供学习 System 1/2 与经验沉淀；[GDPevo](https://github.com/Prism-Shadow/GDPevo) 供学习 task-group 评测。**仅借鉴方法，不复现其代码、指标或结论。**先读自己子 TRD 的输入输出，再去官方仓库找最小示例，不必通读大项目。

本校参考：[shu-course-data](https://github.com/shuosc/shu-course-data) 的历史 JSON 可供 A/B/D 核对班次格式，抓取流程与限制见[来源说明](09-browser-adapter.md)；[SHU 排课助手](https://github.com/shuosc/shu-scheduling-helper)可供 E 参考课程筛选与课表交互；[ShuYo](https://github.com/shuosc/ShuYo)可参考课表及学业修读查询。使用数据与复用代码分别核对许可，不能把参考仓库的能力当本项目已实现。
