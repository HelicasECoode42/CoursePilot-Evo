# System 1：Java Environment / Truth / Verifier（部分实现）

Java 21、Spring Boot、Apache POI、Spring Data JPA、MySQL/Flyway、JUnit 5。首版处理通过自动校验门槛的培养计划和 `SYNTHETIC` 班次 fixture，提供课程/要求/学分/冲突算法/计划核验/偏好指标和 typed Tool API；面向学生没有真实班次时返回 UNKNOWN。按 `../docs/trd/a-data.md`、`../docs/trd/b-verifier.md` 与[实施方案](../docs/10-java-import-and-rules.md)开发，未来浏览器采集边界见 `../docs/09-browser-adapter.md`。

当前已实现：课程/班次查询、时间解析与冲突判断、学业核对
（`POST /api/v1/requirements/audit`）、培养快照列表（`GET /api/v1/curriculum-snapshots`）、
服务密钥与对象级授权。**尚未实现**：`POST /api/v1/plans/validate`、教师与课程评价实体、
学业记录聚合实体（所以 `listAcademicRecords` 目前返回空 items 并以 UNKNOWN 说明缺口）、
各 `import` 端点、MySQL/Flyway（当前是 H2）。现有数据全是 `SYNTHETIC` 演示种子，
没有真实教学计划或真实班次。

## 本地启动

需要 JDK 21 或更高。先设服务密钥，再起服务：

```bash
# macOS / Linux（zsh、bash）
COURSEPILOT_SERVICE_KEY=local-dev-key ./mvnw spring-boot:run
```

```powershell
# Windows PowerShell —— 上面那种「变量=值 命令」的写法在 PowerShell 里不认
$env:COURSEPILOT_SERVICE_KEY = "local-dev-key"
.\mvnw.cmd spring-boot:run
```

服务起在 `http://127.0.0.1:8081`。

`COURSEPILOT_SERVICE_KEY` 是必填的。`/api/v1/**` 要求请求头 `X-Service-Key`
与它一致（契约 `java.openapi.json` 的 `security: serviceKey`），**没配时整个
`/api/v1` 一律返回 503 而不是放行**——没有密钥就分辨不出调用方，放行等于默认开放。
密钥只从环境变量读，仓库里不放默认值（`../docs/04-infrastructure-workflow.md`）。
`local-dev-key` 只是本地占位，别写进代码、配置文件或提交信息。

调接口时三个头一起带。`X-Subject-Id` 是调用方代为断言的主体，Java 信任它的前提
是 `X-Service-Key` 已经证明调用方是已认证的 Python 服务（`../docs/16-engineering-and-debugging.md`）：

```bash
curl -H 'X-Service-Key: local-dev-key' \
     -H 'X-Subject-Id: S001' \
     -H 'X-Request-Id: req-1' \
     http://127.0.0.1:8081/api/v1/curriculum-snapshots
```

## 测试

```bash
./mvnw -B test
```

测试**不需要**设环境变量：用到 HTTP 的测试自己用 `@TestPropertySource` 指定密钥和
内存库，不碰 `./data` 下的文件库。跑测试前确认没有 `spring-boot:run` 在跑，
否则文件库会被占住导致上下文启动失败。

## 排查

H2 控制台默认关闭——它在同一端口上提供免认证的任意 SQL 执行，等于绕过对象级授权
直接读整张成绩表。临时需要时用命令行参数打开，不要写回仓库：

```bash
COURSEPILOT_SERVICE_KEY=local-dev-key ./mvnw spring-boot:run \
  -Dspring-boot.run.jvmArguments="-Dspring.h2.console.enabled=true"
```

日志只记录定位 ID、阶段、状态与耗时，不记密钥、成绩与请求体；用 `requestId` /
`traceId` 对齐一次调用。

A 模块的本地 `.xlsx` 培养计划导入器说明见 [`importer/README.md`](importer/README.md)。
