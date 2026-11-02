# 25 · 怎么证明我们干了这些

> 这份文件只回答一个问题：每一条「我们做到了」后面，证据在哪、怎么自己跑一遍。
> 数字都是 2026-10-29 本机实测，不是估计。跑不出来的、没做到的，写在最后一节。

## 0. 为什么需要这份文件

「单元测试全绿」不等于「产品能用」。这个仓库出现过：几百条绿测试同时存在
7 处接线断裂、一张空课表、一条走不通的培养方案选择，以及一个 lint、
typecheck、build 全过但一打开就白屏的 TDZ 错误。

所以每条能力都要有三样东西：**可跑的命令**、**可核对的产物**、**明确的边界**。

---

## 1. 一条命令能跑出来的基线

```bash
.venv/bin/python scripts/check_contracts.py          # 契约与正负例
python3 scripts/self_check.py                        # 仓库文本与披露检查
cd agent-runtime && ../.venv/bin/python -m pytest -q  # 网关与 Runner
cd web && npm run test:unit && npm run typecheck && npm run lint
cd java-environment && ./mvnw test -Denforcer.skip=true
cd java-environment/importer && ../mvnw test -Denforcer.skip=true
```

2026-10-29 实测结果：

| 模块 | 结果 |
|---|---|
| contracts | PASS：3 份 schema/OpenAPI，22 条正负例 |
| self_check | PASS：453 个 Git 跟踪文件 |
| agent-runtime | 206 passed；ruff 0.15.1 check + format 全过 |
| web | vitest 26 文件 343 passed；vue-tsc 无错；eslint + prettier 过；demo HTML 26 passed |
| java-environment | 198 passed, 0 errors, BUILD SUCCESS |
| java importer | 21 passed, BUILD SUCCESS |
| **合计** | **794 条自动化测试**（206 + 343 + 26 + 198 + 21） |

本机环境注意：只装了 JDK 25，`java_home -v 21` 也返回 25，而根 pom 的
enforcer 要求 `[21,22)`，所以本机跑测试要加 `-Denforcer.skip=true`。
CI 用 temurin 21，不需要这个开关。

### 1.1 这个基线今天才变成真的

在 2026-10-29 之前，`scripts/check_modules.py` 退出码是 1，原因一直没查清。
今天查清了：Java 测试直接连主配置里的开发库
`jdbc:h2:file:./data/coursepilot`，而本机同时在跑 `spring-boot:run`
（PID 74266，监听 8081）占着这个文件。H2 文件锁是进程独占，于是
`AuditResultAssemblerTest` 的 Spring 上下文起不来，19 个用例全 Error，
198 条跑完报 BUILD FAILURE。

修法是加 `java-environment/src/test/resources/application.properties`，
测试改用内存库。反向验证：

- 删掉该文件 → `Tests run: 198, Errors: 19`，BUILD FAILURE
- 加回来 → `Tests run: 198, Errors: 0`，BUILD SUCCESS
- 两次之间 `data/coursepilot.mv.db` 的 md5 都是 `e0f1505...`，
  说明测试已经不再写开发库（修之前是会写的，这是比不稳定更严重的一条）

**更正一处**：commit `2e24b8c` 的信息把机制写成「Spring 上下文缓存互相抢锁」。
实际确认的是开发服务占着文件锁。为什么同一次运行里别的 `@SpringBootTest`
没一起失败，还没查清楚——机制未完全确认，但修法与反向验证都成立。

---

## 2. 真实学校数据：哪些拿到了，哪些没有

学生要的三类学校数据，现状不一样，不能笼统说「接入了教务系统」。

| 数据 | 来源 | 状态 |
|---|---|---|
| 培养方案 | A1 导入器读真实表格 | ✅ 已导入 |
| 学业进度 | 浏览器扩展读学业情况页面 | ✅ 已接通 |
| 开课班次（谁上、周几第几节、第几周） | 选课系统 | ❌ 拿不到 |

### 2.1 培养方案（实测，服务 8081 查得）

快照 `SRC_8659e495...`，`sourceKind=CURRICULUM_FILE`，
`sourceValidation=UNVERIFIED`，显示名「计算机科学与技术（直招）」。

- 课程记录 **105 行**，不同课程号 **95 个**
- 学分为 null 的记录 **0 条**（区间号展开后每门学分已按用户确认的数值补齐）
- 要求类别 5 类：公共基础课 36 / 专业选修课 34 / 学科基础课 19 /
  实践教学环节 14 / 高年级研讨课 2

105 比 95 多出的 10 行是同编号不同学期的课（体育、英语这类）。
`CurriculumCourse` 的唯一键因此从 `(snapshot, courseCode)` 改成
`(snapshot, courseCode, name)`，否则这些课会互相覆盖、丢课。

`sourceValidation` 是 `UNVERIFIED` 不是 `VERIFIED`：上传者贴
`BROWSER_SNAPSHOT` 标签不能让它自动变成已核验。这是有意保留的。

### 2.2 学业进度

路径（每一段都在代码里）：

```
extract.js（只读页面上已渲染的文字）
  → background.js
  → bridge.js（只在 127.0.0.1:5173 / localhost:5173 注入）
  → window.postMessage（校验 event.source 与 origin）
  → RecordsView.vue
  → 网关 PUT /api/v1/school-progress
  → Java SchoolProgressService
  → records.submit(...)        ← SchoolProgressService.java:98
  → Transcript
  → AuditResultAssembler（学业核对读的就是这张表）
```

扩展的边界可以直接在代码里核对：全部 `.js` 文件里没有 `password`、
`document.cookie`、`fetch(`、`eval`、`innerHTML`；`manifest.json` 的权限
只有 `activeTab` / `scripting` / `storage`，没有 `host_permissions`，
所以扩展自己不往任何地方上传。

```bash
grep -niE "password|cookie|fetch\(|eval|innerHTML" browser-adapter/academic-progress/*.js
# 期望：无输出
```

状态只取页面上明确的文字、`title`、`aria-label`、`alt`，取不到就是
`UNKNOWN`，不按成绩栏反推「已通过」。

### 2.3 开课班次：确实没有

实测（95 个真实课程号逐个查 `/api/v1/offerings`）：

```
真实培养方案不同课程号: 95
  有 2025-FALL 班次的: 0
  有评价记录的: 39
```

唯一的班次快照是 `OFFER_2025_FALL`，`sourceKind=SYNTHETIC`，
只覆盖演示课 CS101 / CS102 / CS103。

「这学期谁上、周几第几节、第几周」只在选课开放时才在选课页面上公开，
现在拿不到。所以：

- **课表和时间冲突检测的算法是真的**（ConflictChecker 有 11 条测试，
  在真实数据上也触发过冲突），
- **但演示只能跑在合成班次上**。
- 任何界面都不能说「这是你下学期的真实课表」。

选课开放后的补法已经想好：扩展读学业情况页面用的是同一套「只读已渲染
文字」的做法，加一个 content script 匹配选课页即可，不需要改契约。

### 2.4 评价

258 条真实评价（152 条冬季学期 + 106 条院系），匹配到真实培养方案里的
**39 门课**（实测）。教师真名只留在 `data/private/`，不进公开仓库。

评价只给**条数和原文引用**，不算均分、不给星级。因为「高绩点」「签到松」
「工作量」「授课评价」不是一回事，混成一个分数就是编造。

---

## 3. AI 真的用上了这些事实

`agent-runtime` 的 Runner 不是把课程列表塞进 prompt 让模型自由发挥：

- `_collect_reviews` 按动机决定是否查评价（`REVIEW_DRIVEN_MOTIVES`），
  查询次数受 `max_tool_calls` 预算约束
- payload 带 `courses` 与 `reviewEvidence`
  （`queriedCourseCodes` / `notQueriedCourseCodes` / `untrustedQuotedText`）
- 解释文案由 `_explain(verdict, cited, facts)` 按**实际引用到的**事实生成，
  不是固定句子
- `CandidateGuard` **不读**这些事实：评价再好也不能放宽候选校验

预算（docs/04 §3）：输入 8000 / 输出 2000 token，6 次工具调用，
3 次模型调用，45 秒。`model_client` 显式传 `max_tokens`——
原先只在事后 `record_tokens`，不传上限等于让上游自己决定花多少钱。

会话级还有 `SessionSpendLedger`（40000 / 10000 / 10000）。

### 3.1 建会话限流

`POST /api/v1/sessions` 不要认证也没有配额，而每建一个会话，
`SessionStore` / `IdempotencyStore` / `SessionPlanStore` 都会在进程内存里
多一条且不自动清理——一个循环就能把网页对所有人打挂。

现在：同一地址五分钟最多 10 次，超额 429 `RATE_LIMITED`；
跟踪的键本身也有上限（默认 10000），换 IP 刷也撑不爆字典。

反向验证（6 条用例，`agent-runtime/tests/test_rate_limit.py`）：

- 把「拒绝也记额度」改回去 → 2 条红
- 去掉键数量上限 → 1 条红
- 还原后 `cmp` 字节一致，6 条全绿

局限写在模块文档里，不藏着：分桶键是 `request.client.host`，放在反向代理
后面会退化成一个全局配额。建会话这一步还没有可信身份，暂时没有更好的键。

---

## 4. 提交历史本身就是证据

2026-10-29 把 108 个未提交文件分成 7 个功能批次提交，每条信息里都写了
**跑了什么检查**和**哪些缺口没修**：

```bash
git log --oneline feat/b-contract-endpoints ~12
git show --stat <sha>        # 看某一批改了什么
```

提交信息里出现「已知缺口」「待裁决」「未修」的地方，是故意留的，
不是忘了写。

---

## 5. 没做到的（不要在演示里绕过去）

1. **开课班次没有真实来源** → 课表与时间冲突只能在合成班次上演示。
   见 2.3。
2. **`Transcript.revise` 是子表整体替换**（`completedCourses.clear()`），
   再导一次学校数据会清掉学生手填的行。与 AGENTS.md「学业记录只补缺」冲突。
   需要先定合并语义，没动。
3. **`web/src/domain/credit-plan.ts` 在前端枚举学分组合**，判断哪些组合
   「刚好补齐」缺口，并按 `category` 决定哪门课算进哪个缺口。服务端没有对应
   实现。与「不复制学分/时间规则」冲突——类别归属这个假设已经被导入时发现的
   未建模规则（多修的通识课可跨类认定）证伪过。两条路还没定：搬到 Java，
   或留在前端但把说法改成「这几门学分之和等于当前缺口，是否满足要求以
   Java 核对为准」。
4. **四个评价字段两份契约不对齐**：`reviewBasisStatus`、
   `courseSourceRefIds`、`rationaleSource`、`reviewEvidenceRefs`
   只在 `domain.schema.json` 里定义，`planning.openapi.json` 里 0 处引用。
   ```bash
   for f in reviewBasisStatus courseSourceRefIds rationaleSource reviewEvidenceRefs; do
     printf "%-20s planning=%s domain=%s\n" "$f" \
       "$(grep -c $f contracts/planning.openapi.json)" \
       "$(grep -c $f contracts/schemas/domain.schema.json)"
   done
   ```
5. **`/api/v1/offerings` 的 `courseCode` 契约写的是选填，实现要求必填**
   （不带就返回 400 `MISSING_PARAMETER`）。实测发现，未修。
6. **真实模型两次规划都返回 `MODEL_INVALID_OUTPUT`**（一次缺 content、
   一次不是 JSON）。`choices` 形状那个已经修过，但输出稳定性还没解决。
7. **浏览器扩展没有自动化测试**，只在真实页面上手动验证过一次。
8. **`GET /api/v1/career-directions` Java 和网关都实现了，网页还没用上。**
9. **课程大纲/教材内容没有数据源**。用户的判断是对的：这类内容不是
   本校专有的，可以做一张人工整理的课程知识表，但还没做。
10. **gold / held-out 标注没做完**，D 模块的评测还不能算有基线。

---

## 6. 演示时的红线

警告框在演示里可以收起来，这不是问题。真正不能碰的只有一条：

**在没有真实班次、没有核验来源的情况下，界面不能说「已核验」「无冲突」
「这是你下学期的课表」。** 说「这是用合成班次演示冲突检测」是诚实的，
说「你这学期不冲突」是编的。
