# 学习仓库：每人只读与自己模块相关的部分

| 成员 | 官方仓库 | 建议先看的内容与用途 |
| --- | --- | --- |
| A | [Apache POI](https://github.com/apache/poi)、[Spring 文件上传](https://github.com/spring-guides/gs-uploading-files) | HSSF/WorkbookFactory 读取旧 `.xls`、文件上传边界；重点保留课程编号前导零 |
| B | [Spring PetClinic](https://github.com/spring-projects/spring-petclinic)、[Spring REST Guide](https://github.com/spring-guides/gs-rest-service) | 领域服务与 API 分层、DTO/测试写法；不照搬业务规则 |
| C | [Spring Data JPA Guide](https://github.com/spring-guides/gs-accessing-data-jpa)、[create-vue](https://github.com/vuejs/create-vue) | MySQL 持久化和 Vue/Vite 单页；只做本项目需要的最小页面 |
| D | [FastAPI](https://github.com/fastapi/fastapi)、[pytest](https://github.com/pytest-dev/pytest) | Pydantic 请求/响应、错误处理、假 Tool 测试；先写单 Agent 有界循环 |
| E | [promptfoo](https://github.com/promptfoo/promptfoo) | 任务断言、逐例结果、回归比较；自进化白名单/晋级逻辑仍由本项目自行实现 |

阅读顺序：先看各子 TRD 的输入输出，再找官方仓库的最小示例；不需要从头读完大仓库。参考代码只用于学习和设计，功能完成情况仍以本项目测试/演示为准。
