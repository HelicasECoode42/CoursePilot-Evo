# 五人 GitHub 协作约定

> 2026-09-30 核对：仓库 [HelicasECoode42/CoursePilot-Evo](https://github.com/HelicasECoode42/CoursePilot-Evo) **已创建并推送 `main`，当前 GitHub 显示为 Public**。四位成员尚待提供 GitHub 用户名并邀请取得写入权限；分支保护规则尚未启用。不要推断可见性为何变化。

## 建仓方案

仓库名 `CoursePilot-Evo`，归 `HelicasECoode42` 账号，**当前 Public**，由独立 CoursePilot 本地项目创建，与 DOVideo 上游仓库无关。已核对 `git ls-files`：`data/raw/` 的原始 `.xls`、第三方 UserScript、教务 Cookie/Token、学号成绩和模型密钥未被跟踪。仓库内容目前公开可读；用户提供四名成员的 GitHub 用户名后发邀请，他们接受后才有协作写入权限。

## 五周最小工作流

1. `main` 只放通过集成检查的内容。每人从 `main` 建 `feat/data-import`、`feat/java-verifier`、`feat/agent`、`feat/benchmark`、`feat/web` 等短分支，每个任务用 Pull Request 合并。
2. 第一周先合并共享 Schema/DTO/Tool API/Trace/版本契约。接口变更先改契约及样例，再改实现。A/B、C/D、D/E 按已有 TRD 协同，不各自造同名对象。
3. 每个 PR 说明修改、测试证据和数据真实性边界；至少请一名同学检查关键规则与跨模块接口。若账号套餐支持相应保护规则，可在设置中要求 PR 审核和检查通过；未启用前不要声称仓库已强制保护。[GitHub 官方说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。
4. 培养计划导入与时间解析用黄金样例和反例自动回归；任何未知格式返回 UNKNOWN/ImportIssue。真实班次暂不可验证，不能让模拟 fixture 被当作开课事实。
5. 每周固定一次 Web→Python→Java 端到端演示；W4 冻结评测集合，W5 只在隔离 held-out 通过时晋级 Harness 版本。遇到冲突由相应模块负责人更新共享契约并通知全组。

GitHub 官方文档说明个人仓库可邀请协作者；具体权限和保护功能取决于账号/仓库设置：[邀请协作者](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)。
