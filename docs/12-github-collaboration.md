# 五人 GitHub 协作约定

> 2026-09-29。**私有远程仓库尚未创建**：本机 `gh` 保存的 GitHub 登录令牌已失效，GitHub 创建页也要求重新登录。不要把本文件当作已经开仓、已邀请成员或已启用保护规则的证明。

## 建仓方案

仓库建议名 `CoursePilot-Evo`，归用户本人账号、**Private**。从当前独立 CoursePilot 项目推送；不关联 DOVideo 上游仓库。推送前检查 `git status`、`git remote -v`、`git ls-files`，确保 `data/raw/` 的原始 `.xls`、第三方 UserScript、教务 Cookie/Token、学号成绩和模型密钥未被跟踪。GitHub 登录恢复后先创建私有仓库、推送 `main`，再由用户提供四名成员的 GitHub 用户名邀请协作；成员接受邀请后才有访问权限。

## 五周最小工作流

1. `main` 只放通过集成检查的内容。每人从 `main` 建 `feat/data-import`、`feat/java-verifier`、`feat/agent`、`feat/benchmark`、`feat/web` 等短分支，每个任务用 Pull Request 合并。
2. 第一周先合并共享 Schema/DTO/Tool API/Trace/版本契约。接口变更先改契约及样例，再改实现。A/B、C/D、D/E 按已有 TRD 协同，不各自造同名对象。
3. 每个 PR 说明修改、测试证据和数据真实性边界；至少请一名同学检查关键规则与跨模块接口。若账号套餐支持相应保护规则，可在设置中要求 PR 审核和检查通过；未启用前不要声称仓库已强制保护。[GitHub 官方说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。
4. 培养计划导入与时间解析用黄金样例和反例自动回归；任何未知格式返回 UNKNOWN/ImportIssue。真实班次暂不可验证，不能让模拟 fixture 被当作开课事实。
5. 每周固定一次 Web→Python→Java 端到端演示；W4 冻结评测集合，W5 只在隔离 held-out 通过时晋级 Harness 版本。遇到冲突由相应模块负责人更新共享契约并通知全组。

GitHub 官方文档说明个人仓库可邀请协作者；私有仓库可供团队协作，但具体权限和保护功能取决于账号/仓库设置：[邀请协作者](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)。
