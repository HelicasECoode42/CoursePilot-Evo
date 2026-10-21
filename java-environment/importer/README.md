# A2: A1 `.xlsx` 培养计划导入器

本模块实现 A2 的 A 侧导入准备流程：限制 `.xlsx` 和 10 MiB 输入、只接收 8 个已知并行路径之一、读取该路径工作表、规范化类别要求/课程明细并保留来源坐标、生成内容哈希幂等键、输出定位型 issue。文件内容被当作不可信数据；不执行公式、宏或外部链接。

## 当前边界

- 这是 Java 21 可运行的导入器与本地诊断 CLI；不是 HTTP 服务。
- `PublishPort` 是 B 事务发布能力的交接接口。当前没有 B 的数据库、身份认证、事务实现，也不声称已经发布快照。
- `.xlsx` 必须使用 A1 标准化工作簿布局，并显式选择一个 ASCII `trackId`；总体页和其他路径不参与该次导入。
- 未知/待确认规则、总计不一致、模板错误、重复课程编号（无论完全相同还是字段冲突）等均阻断发布。当前 A1 文件里的“待拆分复核/冲突待确认”会被阻断，这是设计要求，不代表 A1 清单整理错误。
- 私有/学校原始材料不作为测试 fixture。测试生成虚构 workbook；本地工作簿不参与默认测试。

## 本地运行

Windows PowerShell。从仓库根目录运行下面命令；不填工作簿路径时会弹出文件选择框。`java-environment/importer` 是代码目录，不是课程文件目录：当前工作区的本地 A1 工作簿位于仓库的 `data/curriculum/`。选择框会优先打开该目录，并在文件存在时预选 `2024-computer-college-curricula.xlsx`。

```powershell
.\java-environment\importer\run-importer.ps1 -TrackId 'cs-general'
```

确认选择 A1 标准化 `.xlsx` 后，脚本会先构建，再运行 CLI。仓库根目录可以位于任意盘符；脚本会根据自身位置查找 Maven Wrapper。如果选择框没有预选文件，进入仓库的 `data/curriculum/` 目录选择 A1 工作簿；其他组员若仓库版本中没有该文件，应选择自己取得的标准 `.xlsx`。原始学校文件仍保留在本地；整理后的 A1 清单按仓库规则存放在 `data/curriculum/`。

也可以直接传入本机实际存在的工作簿路径：

```powershell
.\java-environment\importer\run-importer.ps1 -Workbook 'D:\请替换为你自己的真实路径\课程清单.xlsx' -TrackId 'cs-general'
```

不要把示例中的路径文字原样执行。8 个可选 `TrackId` 是 `cs-direct`、`cs-general`、`ai-science-direct`、`ai-science`、`cybersecurity-direct`、`cybersecurity`、`ai-engineering-direct`、`ai-engineering`。

如 PowerShell 提示禁止运行脚本，可在当前进程临时绕过执行策略（不修改系统策略）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\java-environment\importer\run-importer.ps1 -TrackId 'cs-general'
```

CLI 会打印选定路径的记录数、哈希键和 issue 坐标，不输出课程内容；它只准备 draft，不会写入数据库或发布快照。有阻断 issue 时返回非零码是预期的数据校验结果，不是启动错误。

## 在 IntelliJ IDEA 或 VS Code 中运行

两个 IDE 都运行同一份 Java 导入器；解析结果和校验逻辑与 PowerShell 启动相同。IDE 可以保存运行配置、管理 Maven 依赖、设置断点并逐步调试；它不会改变 A2 的输入要求或质量门槛。

**IntelliJ IDEA：**打开 `java-environment/importer/pom.xml` 并作为 Maven 项目导入；Project SDK 设为 Java 21。先在 Maven 面板运行 `Lifecycle > verify`。然后新建 Application 运行配置：Main class 填 `edu.coursepilot.importer.ImporterCli`，Use classpath of module 选 `curriculum-importer`，Program arguments 填你电脑上工作簿的真实完整路径和路径 ID，例如：

```text
"D:\你的实际目录\课程清单.xlsx" cs-general
```

**VS Code：**安装 Extension Pack for Java，打开仓库目录并等待 Java/Maven 项目导入。运行 `ImporterCli` 时，在 Run/Debug Configuration 的 `args` 中填同样的两个参数；也可以在 VS Code 集成终端运行上面的 PowerShell 文件选择器命令。

IDE 运行配置中的工作簿路径只保存在本机 IDE 配置中，不要提交到仓库。B 同学的服务从上传临时文件调用 Java API，不使用此本机运行配置。

## B 同学的服务集成

B 不需要依赖某位组员电脑上的工作簿路径，也不应把 CLI 输出当成接口数据。服务收到已授权的 `.xlsx` 文件后，直接在 Java 中调用导入器 API，获得结构化 `CurriculumDraft`：

```java
var importer = new A1WorkbookImporter();
var draft = importer.prepare(uploadedWorkbookPath, trackId);
if (!draft.publishable()) {
  // 将 draft.issues() 转为接口定义的字段错误响应；不要发布。
}
var result = importer.publish(draft, publishPort);
```

`uploadedWorkbookPath` 是服务接收上传后管理的临时文件路径；`publishPort` 由 B 实现，负责对象级授权后的事务写入、幂等和版本管理。当前 `PublishPort` 只是交接接口，数据库/HTTP API/身份认证仍由 B 实现；契约以 `contracts/` 和对应 TRD 为准。共享代码通过本仓库的 Maven 模块依赖，不共享本机文件路径。

路径 ID 到 A1 工作表的固定映射：`cs-direct`→计科学直招，`cs-general`→计科学，`ai-science-direct`→智能科直招，`ai-science`→智能科，`cybersecurity-direct`→网安全直招，`cybersecurity`→网安全，`ai-engineering-direct`→人智能直招，`ai-engineering`→人智能。
