# 子 TRD A｜培养计划与浏览器数据适配（12 人日）

**输入：**原始 2024 级 `.xls`（本地 `data/raw/`）、只读检查的 `选课插件v0.6.js`、全组冻结的[CourseOffering Schema](../course-offering-snapshot.schema.json)和[共享契约](../04-infrastructure-workflow.md)。**当前状态：**只有文件和设计，尚无 CoursePilot Adapter/导入器。A 拥有 `java-environment/.../importer/`、Browser Adapter 源码（建议 `browser-adapter/`）、解析/映射测试；不改 B 的规则计算。

## 要回答的问题与做法

1. **培养计划怎样可靠转换？** Java 21 + Apache POI `WorkbookFactory/DataFormatter` 解析选定的一条计算机路径，区分表 1、左右并列表 2、实践表 3；保留课程号前导零、sheet/row/column/hash。组合编号、`8+4`、文字规则进人工审核清单。相同文件/路径/导入器版本幂等。
2. **浏览器实际给哪些班次字段？** 在获得授权的本人选课页，以只读方式人工核对三类响应、分页/空值/学期切换；确认原脚本 `btn_yd.click()` 副作用及疑似 `rawData[x]` 错误。**不要直接运行或复制原脚本作为采集实现。**
3. **如何安全采集？** 编写独立无自动点击、无提交请求的 Adapter，只观察页面已取得的数据，由用户显式导出最小化 JSON；不传 Cookie/Token，不保留完整原始响应。直接 POST localhost 仅在本地浏览器限制和 Origin 校验通过后作为可选方案。
4. **如何规范化？** 映射 `kch_id→courseCode`、`jxb_id→classId`、`jxbxf→credits`、`jxbrs→capacity`、`jsxx→teacherText`、`sksj→meetingTextRaw/meetings`，`xnm/xqm` 必填。单双周、连续/离散周解析失败标 `UNKNOWN_TIME_FORMAT`，不当无冲突。给 B 可重复的虚构 fixture、真实但脱敏且获授权的对照记录和字段异常表。

## 交付与验收

交 `CurriculumSnapshotDraft`、`CourseOfferingSnapshot` JSON、来源字段字典、第一周 `VERIFIED/PARTIAL/UNAVAILABLE` 结论和异常清单。测试至少覆盖 `.xls` 三种表型/前导零/重导幂等，以及 5 种周次写法、混学期拒绝、缺课程号拒绝、未解析时间 UNKNOWN。人工与官方页面对照至少两组冲突/不冲突样例。若页面不可稳定合法采集，保留只读分析与 fixture，不编造已接入。

**依赖：**B 提供导入端点和存储契约；E 提供本地上传 UI。A 不改 Java Verifier 或前端结果文案。**学习入口：**[Apache POI](https://github.com/apache/poi) 的 HSSF/SS；[MDN Web APIs](https://developer.mozilla.org/en-US/docs/Web/API) 的 Blob/下载与浏览器安全模型；[JSON Schema](https://json-schema.org/learn/getting-started-step-by-step) 的结构校验。
