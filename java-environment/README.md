# System 1：Java Environment / Truth / Verifier（部分实现）

Java 21、Spring Boot（已引入 Web、Spring Data JPA、Validation；源码中尚无 `@Valid`/`@NotNull` 等校验注解在用）、H2 文件库（`./data`）、JUnit 5（经 spring-boot-starter-test）。Apache POI 5.5.1 用于 XLSX 导入；尚未引入 MySQL 驱动或 Flyway。首版**目标**是处理通过自动校验门槛的培养计划和 `SYNTHETIC` 班次 fixture，提供课程/要求/学分/冲突算法/计划核验/偏好指标和 typed Tool API；面向学生没有真实班次时返回 UNKNOWN。这是模块范围，不是当前能力——实际完成到哪一步见下一段。按 `../docs/trd/a-data.md`、`../docs/trd/b-verifier.md` 与[实施方案](../docs/10-java-import-and-rules.md)开发，未来浏览器采集边界见 `../docs/09-browser-adapter.md`。

当前已实现：课程/班次查询（`GET /api/v1/courses`、`GET /api/v1/offerings`）、时间解析与冲突判断、学业核对
（`POST /api/v1/requirements/audit`）、服务密钥与对象级授权。培养计划 XLSX 导入器可在显式开启的本地演示模式下
通过 `POST /api/v1/curriculum-snapshots/import` 发布为 `SYNTHETIC/SYNTHETIC`，不支持真实来源发布。另有三个 `/api/v1/verification/*` 接口
（`credit-gap`、`parse-time`、`conflicts`）已实现，但未在 `contracts/java.openapi.json` 中声明，属于契约外的既有接口。
**尚未实现**：`POST /api/v1/plans/validate`、教师与课程评价实体、
班次/评价导入、MySQL/Flyway（当前是 H2）。现有数据全是 `SYNTHETIC` 演示种子，
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

### 本地 synthetic 培养计划导入

导入接口默认关闭。仅在本机演示时设置独立管理员密钥并显式启用；上传内容一律标记为 `SYNTHETIC`，客户端不能指定 `sourceKind` 或 `sourceValidation`。接口只接受 loopback 调用，同时仍要求 `X-Service-Key` 和 `X-Admin-Key`。上传限制为 10 MiB，仅接受 `.xlsx`；有未解释规则或当前模型无法表示的行会拒绝发布。真实资料的来源核验、独立基线和 VERIFIED 发布流程尚未实现。

```bash
COURSEPILOT_SERVICE_KEY=local-dev-key \
COURSEPILOT_ADMIN_KEY=local-admin-key \
COURSEPILOT_SYNTHETIC_IMPORT_ENABLED=true \
./mvnw spring-boot:run
```

另一终端用本地生成或明确授权的演示工作簿调用：

```bash
curl -X POST 'http://127.0.0.1:8081/api/v1/curriculum-snapshots/import' \
  -H 'X-Service-Key: local-dev-key' \
  -H 'X-Admin-Key: local-admin-key' \
  -H 'X-Subject-Id: teacher:demo' \
  -H 'X-Request-Id: curriculum-import-1' \
  -F 'schemaVersion=1.0' \
  -F 'trackId=cs-general' \
  -F 'file=@./path/to/synthetic-curriculum.xlsx'
```

响应的 `provenance[0].kind` 为 `SYNTHETIC`；响应中的 `snapshotId` 可用于 `GET /api/v1/curriculum-snapshots` 和 `GET /api/v1/courses?curriculumSnapshotId=...`。相同内容的重复导入复用原快照。

调接口时三个头一起带。`X-Subject-Id` 是调用方代为断言的主体，Java 信任它的前提
是 `X-Service-Key` 已经证明调用方是已认证的 Python 服务（`../docs/16-engineering-and-debugging.md`）：

```bash
curl -H 'X-Service-Key: local-dev-key' \
     -H 'X-Subject-Id: S001' \
     -H 'X-Request-Id: req-1' \
     http://127.0.0.1:8081/api/v1/courses
```

### 本地私有教师评价导入

`data/private/a3/review-import/delivery/` 中的 ReviewImport JSON 与姓名 sidecar 可在本机按
`reviewNoteId`、`sourceRefId`、`courseCode` 三字段联接。合并脚本只把姓名写入可选的
`teacherDisplayName` 显示字段；不会生成 `teacherKey` 或改变 JSON 内的 `matchStatus`。
输入文件应留在 `data/private`，输出文件也只写在该目录中：

```bash
python3 java-environment/scripts/prepare_review_import.py \
  --reviews data/private/a3/review-import/delivery/review-import-faculty-history.json \
  --sidecar data/private/a3/review-import/delivery/teacher-display-sidecar.csv \
  --output data/private/a3/review-import/delivery/review-import-faculty-history-with-display-names.json
```

对 `review-import-winter.json` 重复运行并更换输入、输出文件名。本地启动服务时绑定 loopback 地址，
分别对每个不超过 200 条的 JSON 文件调用导入端点；导入需要服务密钥、管理员密钥和主体头：

```bash
COURSEPILOT_SERVICE_KEY=local-dev-key \
COURSEPILOT_ADMIN_KEY=local-admin-key \
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.address=127.0.0.1
```

另一终端调用：

```bash
curl -X POST 'http://127.0.0.1:8081/api/v1/reviews/import' \
  -H 'Content-Type: application/json' \
  -H 'X-Service-Key: local-dev-key' \
  -H 'X-Admin-Key: local-admin-key' \
  -H 'X-Subject-Id: teacher:local-review-import' \
  -H 'X-Request-Id: review-import-faculty-1' \
  --data-binary @data/private/a3/review-import/delivery/review-import-faculty-history-with-display-names.json
```

旧 JSON 不带 `teacherDisplayName` 时仍可导入。按课程查询结果会返回该显示字段；课程级或未核验评价仍
按其 `matchStatus` 展示为受限证据，姓名文本不用于教师绑定。

## 测试

```bash
./mvnw -B test
```

测试**不需要**设环境变量：用到 HTTP 的测试自己用 `@TestPropertySource` 指定密钥和
内存库，不碰 `./data` 下的文件库。跑测试前确认没有 `spring-boot:run` 在跑，
否则文件库会被占住导致上下文启动失败。

## 排查

### `./mvnw` 起不来

先跑这一条，它同时告出 Maven 和 JDK 两个版本（Windows 用 `.\mvnw.cmd -v`）：

```bash
./mvnw -v
```

JDK 24 以上会先刷几行 `WARNING:`，不影响构建，往下看 `Java version:` 那行就行。

对照下面三种情况。这三种都跟 macOS / Windows 无关，别按操作系统找原因。

**一、`release version 21 not supported`**

`Java version:` 那行低于 21。pom 里是 `<java.version>21</java.version>`，JDK 17
编不了。只看你默认的 JDK 是哪个：装一个 21 或更高的，再把 `JAVA_HOME` 指过去——
`mvnw` 优先用 `JAVA_HOME`，没有才用 PATH 上的 `java`。

```bash
# macOS / Linux
/usr/libexec/java_home -V                           # macOS：列出本机所有 JDK
export JAVA_HOME=$(/usr/libexec/java_home -v 21)    # 取 21 及以上里最新的那个
./mvnw -v                                           # 确认 Java version 变了
```

```powershell
# Windows PowerShell —— 路径换成你自己的安装位置
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
.\mvnw.cmd -v
```

上面两种写法都只在当前终端有效。长期生效：macOS / Linux 写进 `~/.zshrc`，
Windows 在「系统属性 → 环境变量」里设。

**二、卡在下载，或者报下载失败**

本模块的 wrapper 是 `distributionType=only-script`（见
`.mvn/wrapper/maven-wrapper.properties`），仓库里不放 Maven 本体，第一次运行要从
`repo.maven.apache.org` 下 Maven 3.9.6。下成功后缓存在下面这个目录，之后不再联网：

```bash
ls ~/.m2/wrapper/dists/apache-maven-3.9.6
```

Windows 是 `%USERPROFILE%\.m2\wrapper\dists\apache-maven-3.9.6`。目录不存在就是
还没下成功。到国外慢的话换个镜像源重跑一次：

```bash
MVNW_REPOURL=https://maven.aliyun.com/repository/public ./mvnw -v
```

这个变量只管 Maven 本体的下载。依赖包要换源得配 `~/.m2/settings.xml`，那是各人
本机的事，不进仓库。

**三、`Permission denied`**

只会出现在 macOS / Linux，`mvnw` 丢了可执行位。main 上它是 100755，照常检出不会
碰到；自己建的分支或在 Windows 上改过这个文件才可能出现：

```bash
git update-index --chmod=+x java-environment/mvnw
```

### 两条跟版本无关的

测试报上下文启动失败，先看是不是有 `spring-boot:run` 没停——文件库被占住了，
见上面「测试」一节。

`/api/v1` 全部返回 503，是没设 `COURSEPILOT_SERVICE_KEY`，不是服务挂了，
见上面「本地启动」一节。

### H2 控制台

H2 控制台默认关闭——它在同一端口上提供免认证的任意 SQL 执行，等于绕过对象级授权
直接读整张成绩表。临时需要时用命令行参数打开，不要写回仓库：

```bash
COURSEPILOT_SERVICE_KEY=local-dev-key ./mvnw spring-boot:run \
  -Dspring-boot.run.jvmArguments="-Dspring.h2.console.enabled=true"
```

### 日志

日志只记录定位 ID、阶段、状态与耗时，不记密钥、成绩与请求体；用 `requestId` /
`traceId` 对齐一次调用。

A 模块的本地 `.xlsx` 培养计划导入器说明见 [`importer/README.md`](importer/README.md)。
