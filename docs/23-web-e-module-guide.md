# E 模块（学生网页与老师报告）指南

写给全组。读完能知道：E 做了什么、怎么跑起来、代码在哪、改的时候要守什么规矩、现在做到哪一步、还差什么。

模块的完整业务定义在 [E 模块 TRD](trd/e-web-integration.md)，这份是上手说明，不替代它。

## 一、E 负责什么

学生看到的全部界面，加上老师看运行报告的那一页。

**E 不做业务判断。** 学分够不够、课表冲不冲突、方案能不能通过，全部由 Java 核验、Python 转交。E 的职责是**把结论如实显示出来**，特别是把「通过」「有冲突」「无法确认」三种状态分清楚，不把未知显示成通过。

Web 只调 Python，不直连 Java。

## 二、怎么跑起来

Node 要 **22 或更高**（`web/package.json` 的 `engines`）。

```bash
cd web
npm install

# 演示模式：用合成数据，不需要任何后端。看界面、做交互验收用这个。
npm run dev:fixture

# 真实模式：需要 Python 网关在跑
npm run dev
```

打开 http://127.0.0.1:5173

演示模式靠 `vite --mode fixture` 开启，不是 `.env` 文件——仓库的 `.gitignore` 排除了 `.env.*`，用 `.env` 的做法提交不进来，别人 clone 下去跑不了。

### 检查

```bash
npm run test:unit    # 单元测试 + demo HTML 结构检查
npm run lint         # ESLint + Prettier
npm run typecheck    # vue-tsc
```

**单元测试证明不了界面对不对。** jsdom 不算布局、不渲染颜色，测不出拖拽手感、配色和溢出。TRD 写死了这条：「不能仅 node 语法检查声称视觉通过」。改了界面就要起 `npm run dev:fixture` 实际点一遍，PR 里附桌面和窄屏截图。

这不是形式主义。这轮开发里，190 条单元测试全绿的情况下，浏览器里一眼看出三个问题：比较页在应用里**根本没有入口**、教师卡片里的中文**竖着排**、演示模式下换班次功能**压根出不来**。

## 三、代码在哪

```
web/src/
  contracts.ts            从 contracts/schemas/domain.schema.json 推出来的类型
  api/
    client.ts             真实 HTTP 客户端。统一的 request()、信封校验、错误分类
    fixture-client.ts     合成数据客户端，实现同一个接口
    fixture-client.spec.ts  钉住 fixture 必须符合契约
    index.ts              按 VITE_COURSEPILOT_MODE 选实现
  domain/                 纯逻辑，不碰 DOM，最好测
    question-flow.ts      问题顺序、PlanningDraft 结构
    planning-request.ts   把草稿构造成契约的 PlanningRequest
    schedule-grid.ts      课表格子 ↔ BLOCK_DAY/BLOCK_SECTION/BLOCK_SLOT 归一化
    answer-display.ts     展示门禁：什么情况下才允许显示为「通过」
    class-preferences.ts  上课与考核偏好 → softPreferences
  stores/planning.ts      会话、草稿、请求状态
  views/
    QuestionView.vue      E1 目标引导（八步）
    RecordsView.vue       E2 学业资料
    ResultView.vue        E2 结果页 + 搜班次/替换/重验
    TeacherView.vue       E3 比较课程与教师
    ReportView.vue        老师运行报告（受限）
  styles.css              全部样式。不写行内 style
```

路由在 `web/src/router/index.ts`。

## 四、改 E 的时候要守什么

这几条不是风格偏好，是会被测试和验收挡住的硬要求。

### 1. 契约是唯一真源

字段名、必填项、枚举值、数组上限一律以 `contracts/` 为准。拿不准就去读 `domain.schema.json`，不要猜，更不要自己发明字段。

需要新接口时，**先改契约再写代码**，并且契约要和提供方（Python/Java）一起合入。单独提一条只改契约的分支会让 `agent-runtime/tests/test_openapi_contract.py` 挂掉——它要求契约里每个端点在实现里都存在。

### 2. 未知不是通过

缺班次、缺时间、缺资料一律显示为「无法确认」，**不能显示成绿色通过，也不能当成「没有冲突」**。

判断集中在 `domain/answer-display.ts` 的 `describeVerification`，**复用它，不要另写一套**。规则是：只有 `verdict: VALID` **且** `scope: REAL_TIMETABLE` 才允许绿色；`SIMULATION` 和 `COURSE_ONLY` 都要降级显示。答复里带 `FAKE_MODEL` / `FAKE_TOOL` 标记时也降级。

### 3. 不编造数据

没有年份就写「年份未知」，没有评价就写「没有找到评价」，不要写成「评价良好」。没有真实班次就显示未知，不要凑一个看起来合理的时间。

演示数据必须显著标为合成，`verification.scope` 固定 `SIMULATION`，不能标成 `REAL_TIMETABLE`。

### 4. 外部文本不可信

评价、教师姓名、模型输出一律用 `{{ }}` 插值渲染，**绝对不要 `v-html`**。

### 5. 每题都向全部学生展示

E1 的九步问题对所有学生一样，每题都能留空跳过。**动机不决定问哪些题**，只表达在意什么和优先顺序。改动机不清空任何已填答案，构造请求时也不按动机过滤已填字段。

### 6. 不写行内样式

新样式加到 `styles.css`，复用已有 class。注意：**有可展开内容的列表不要用 `.choice-grid`**，它是两列的，展开的内容会被压到一百多像素宽，中文会竖着排。

### 7. 可访问性

展开/收起用 `aria-expanded`，选项按钮用 `aria-pressed`，不可选的用 `disabled` 而不是只去掉点击。详情关闭后焦点要回到打开它的按钮。标题带 `tabindex="-1"`，页面切换后把焦点移上去。

## 五、现在做到哪一步

| | 功能 | 状态 | 说明 |
| --- | --- | --- | --- |
| E-F1 | 查看和补充学业资料 | 已实现 | `RecordsView.vue` |
| E-F2 | 引导学生表达需求 | 已实现 | 九步、可留空、课表网格、明确排序 |
| E-F3 | 比较课程与教师 | 已实现，未联调 | `TeacherView.vue`，选择进 `pinnedTeacherCoursePairs` |
| E-F4 | 理解和调整推荐 | 已实现，未联调 | `ResultView.vue`，含搜班次/替换/整份重验 |
| E-F5 | 处理加载与失败 | 部分 | 401/503/重复点击/迟到响应有覆盖；404 只在报告页测了 |
| E-F6 | 展示老师实验报告 | 已实现，不可用 | 见下方「已知问题」 |
| E-F7 | 保证页面可操作 | 部分 | 窄屏和焦点有做；键盘全链路未系统验过 |

**「已实现，未联调」不等于交付完成。** TRD 写明「fixture 不算真实接入」。E-F3 和 E-F4 目前全部基于合成数据与 mock 跑通，真实链路还缺：

- Java 的 `POST /api/v1/plans/validate`（#30）——没有它，换班次后的整份核验验不了真
- Java 的教师与课程评价实体（#31）——没有它，比较页没有真实数据
- A 的评价资料（A-F4）——同上

## 六、已知问题

### 老师报告页在真实环境下打不开

契约里 `getRunReport` 的 security 是 `sessionBearer` **和** `adminKey` 两个同时要，而浏览器前端按设计不持有管理密钥，也不该持有（[基础设施与协作](04-infrastructure-workflow.md)：密钥仅在环境变量）。

所以这一页在真实模式下会一直显示「需要管理权限」。页面行为是对的——权限由服务端强制，不做隐藏式控制（[TRD](03-trd.md)：报告要管理权限，不能只隐藏按钮）——但**老师需要一条不经过学生前端的访问通道**，这个还没有。要和 C 一起定。

### `searchReviews` 不过滤合成来源

`listCurricula` 那条路径会拒绝合成来源，但评价这条没有同样的门禁。真实服务若返回合成评价，页面会把它当真实证据显示。该在 C 挡还是 E 挡还没定。

### 比较页的分歧判断有限

只能按匹配档、来源类型、维度覆盖面判断证据之间是否一致，**判断不了维度结论的正负**——`ReviewNote` 没有极性字段。

## 七、常见问题

**页面说「请先在规划页开始会话」？**
直接输网址打开是整页加载，内存里的会话是空的。学生答案和会话本来就只在内存里、刷新即清空（这是 TRD 要求的）。要从首页点进去。

**改了界面但浏览器没变？**
Vite 的热更新会重置组件内的本地状态（比如比较页的教师显示名），但存进 store 的草稿会保留。看到显示名变成 `teacher-xxx` 这种原始 key 是正常的回退——页面不编造名字。

**`npm run lint` 在我机器上一堆错？**
先看 `node -v`。低于 22 会装出不同版本的依赖，报一堆和代码无关的格式问题。

**我要加一个新接口怎么办？**
先在 `contracts/planning.openapi.json` 里定好形状、补正反例，和提供方一个 PR 合入，再写前端。顺序反过来必踩坑。
