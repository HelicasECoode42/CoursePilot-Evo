# Web 视觉与交互规范（从现有页面反推）

本文把 [HTML 原型](../demo/coursepilot-guided-demo.html) 和 [Vue 实现](../web/src/styles.css) 已经成立的做法固定下来，供后续 E2、E3 新增页面照着做。真源仍是 HTML 原型；本文是概括，不是新设计。

## 设计令牌

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--ink` | `#18312b` | 正文与标题墨色 |
| `--soft` | `#65736d` | 次级说明、标签、禁用态 |
| `--green` | `#226c50` | 主色：主按钮、选中边框、链接、进度条 |
| `--wash` | `#f2f7f4` | 选中底色、pill 底色 |
| `--line` | `#e1e8e3` | 1px 细线与未选中边框 |
| 页面底色 | `#fff` | 纯白，不使用灰底 |
| 焦点环 | `3px solid #69a98b`，`outline-offset:4px` | 所有可聚焦元素 |
| 主按钮 hover | `#18543d` | — |
| 提示（中性） | 底 `#f8faf8`，字 `--soft` | `.hint` |
| 提示（需注意） | 底 `#fff8ed`，字 `#875817` | `.hint.amber`，用于"缺资料""虚构演示" |
| 待确认徽标 | 底 `#fff5e5`，字 `#936329` | `.pending`，用于"真实时间待确认" |

字体 `"PingFang SC","Microsoft YaHei",sans-serif`，`font-synthesis:none`。不引入 Web Font。

## 版式

- 内容区 `width:min(640px, calc(100% - 40px))`，居中，`margin:32px auto 20px`。
- 顶栏 `height:78px`，`max-width:1100px`，左 logo + 「CoursePilot」+ 12px 次级标注，右侧一个文本按钮。
- `h1` `clamp(28px,4vw,36px)`，`font-weight:600`，`letter-spacing:-1px`，`text-wrap:balance`。
- `h2` 21px/600；正文 `line-height:1.7`；导语 `.intro` 14px `--soft`，下边距 26px。
- 进度条：左侧阶段名 13px `--soft`，右侧 `90px × 3px` 轨道，绿色填充。**轨道不随步数变长**。
- 页脚 11px `#6d7a73` 居中，写免责说明。

## 组件

**选项按钮** `.option`：`<button>` + `aria-pressed`，不是 `<input type=radio>`。两列网格 `1fr 1fr`，间距 10px，`min-height:77px`，`border-radius:12px`，1px `--line` 边框。左侧 19px 圆形 `.selection`；选中时填绿 + 白色 `✓`，边框转绿、底色转 `--wash`。hover 时边框 `#91b59f`、底 `#fbfdfb`。内部 `strong`（16px/550）+ `small`（12px `--soft`）。

**时间格子** `.timeOptions`：复用 `.option`，三列，`min-height:62px`，居中，勾选圈缩到 15px。窄屏两列。

**底部控制条** `.controls`：左「返回」文本按钮（`.back`，无边框、`--soft`、disabled 时 `visibility:hidden`），右绿色主按钮（`.next`，`padding:13px 25px`，`border-radius:9px`，`min-width:125px`）。按钮文案随页面变化（如「确认顺序并继续」「只看虚构演示候选」）。

**摘要表** `.summary-row`：`grid-template-columns:140px minmax(0,1fr)`，行间 1px 下边线，13px；标签 `--soft`，值可换行（`overflow-wrap:anywhere`）。窄屏首列收到 105px。

**pill** `.pill`：`--wash` 底、绿字、12px、`border-radius:6px`，用于回看已选项。

**候选卡** `.candidate`：`grid-template-columns:1fr auto`，顶部 1px 分隔线，不用卡片阴影。左侧课程名 17px/550 + 灰色 meta + 理由；右侧 `.pending` 徽标。窄屏退为单列。

**详情弹层** `.detail` / `.sheet`：全屏遮罩 `#17302650`，内容 `min(520px,100%)`、`max-height:85dvh`、`border-radius:16px`、`padding:27px`。这是**唯一允许用阴影**的地方（`0 25px 80px #0d261e30`）。打开时主区与顶栏 `inert`，焦点移到「关闭」；关闭后焦点回到原触发按钮（按 `data-review` / `data-action` / `id` 定位稳定锚点，重渲染后仍能找回）。

**证据块** `.evidence`：左侧 2px `#c8d9ce` 竖线 + 13px 文字，用于展示评价原文和来源行。

## 不要做的

- 不加外层大圆角阴影卡片（弹层除外）。
- 不加渐变、不加动效（`prefers-reduced-motion` 已全局关动画）。
- 不用 `v-html` / `innerHTML` 渲染评价或模型文本（HTML 原型里统一走 `escape()`）。
- 不因为新增内容把进度条、内容区宽度或字号整体放大。
- 不向学生展示 Java / Harness / Prompt / Trace 等工程词。

## 交互约定

- 一次一问，只挂载当前问题；`h1` 带 `tabindex="-1"`，切页后聚焦它并 `scrollTo(0,0)`。
- 顶部有「跳到当前问题」skip link。
- 返回保留内存答案；取消某目标时清除该分支答案。
- 门禁式确认（目标排序、虚构演示同意）未勾选时，主按钮点击只给 13px `#8b4b24` 的提示文字，不跳页。
- 窄屏断点 `max-width:540px`：顶栏降到 67px、隐藏副标注、选项两列不变但内边距与字号缩小、时间格子转两列、候选卡转单列。桌面与 375px 都不能横向溢出。
