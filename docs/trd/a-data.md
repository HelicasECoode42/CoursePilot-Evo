# 子 TRD A｜真实 `.xls` 导入与来源（10 人日）

**目标：**把一个确认过的 2024 级计算机科学与技术培养路径变成可查询的课程/要求快照，所有值能定位回工作表和行。当前 `data/raw/` 有用户给的原文件；Java 导入尚未实现。

## 技术与文件

Java 21、Apache POI `WorkbookFactory`/`DataFormatter`、Spring Boot Service、MySQL/Flyway、JUnit 5。建议负责 `java-environment/src/main/java/.../importer/`、`domain/SourceRef.java`、`db/migration/V1__*.sql` 和 importer 测试。不要让 Python 直接读 `.xls`，也不要把解析写进 Controller。

## 做法（按顺序）

1. 与组确认演示路径是 `计科学` 还是 `计科学直招`；这两个路径分别有 3 张表。建立显式映射，特别注意非直招第三张叫 `计科3`。
2. 用 `WorkbookFactory.create(InputStream)` 打开 `.xls`；用 `DataFormatter` 读取编号文本，保留前导零。原文件 SHA-256 构成快照 ID 的一部分。
3. 分三种模板解析：表 1 的分类/课程与尾部文字规则；表 2 左右两组课程；表 3 实践环节。重复表头、合计和备注不当成普通课程。
4. 形成 `CourseDraft(code,title,credits,category,suggestedTerm,sourceRef,reviewStatus)` 与 `RequirementDraft(rawText,sourceRef,reviewStatus)`。`08305011~012`、`8+4`、`详见附表` 均进异常/人工审核清单，不能自动猜值。
5. 人工抽查各表型至少 5 行；经过审核的数据入 MySQL。相同文件/路径重导不重复生成课程，换文件生成新快照。
6. 给 B/C 一份小 JSON fixture、字段字典和“未知/未审核”清单。

## 验收

用本文件核对 `计科学1!F45=24` 专业选修学分、`F48=257` 总计及第 49/53 行文字规则；跨路径课程不能串入。测试覆盖前导零、空格/合并单元格、左右两栏、复合编号、重导幂等和错误文件。对不确定规则返回 `reviewStatus=PENDING`，不自行解释政策。

**学习入口：**[Apache POI](https://github.com/apache/poi) 的 HSSF/SS API 与示例；[Spring 文件上传指南](https://github.com/spring-guides/gs-uploading-files)。先读这些示例，再读完整源码。
