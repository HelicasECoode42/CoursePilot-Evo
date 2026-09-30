# 五人协作与 PR 工作流

仓库：[HelicasECoode42/CoursePilot-Evo](https://github.com/HelicasECoode42/CoursePilot-Evo)，当前公开。项目规范与演示可公开，私人数据和验收答案不进 Git。当前成员姓名/账号待收集，不能假装已经邀请。

## 1. 入组与分工

将 [CSV 模板](team/team-signup-template.csv) 导入金山表格，填写称呼、GitHub 用户名/主页、模块第一/第二志愿、技术基础、每周投入和时间限制。不要收密码、邮箱登录码、手机号或学号。根据志愿、可用时间与模块依赖确定 A–E，不只按先到先得。

统筹填写最终模块与邀请状态；取得用户名后在仓库 Settings → Collaborators 发邀请。队友接受后才获得写权限，不能只把链接发给对方就当完成。填写后的名单保留在共享表格或 data/private，不提交公开仓库。当前只提供模板，没有创建金山云表格。

## 2. 任务到 PR

每批领一个能验收的小任务，短分支例如 feat/a-import、feat/b-time-parser、feat/c-planning、feat/d-gate、feat/e-questions。main 保持可集成，不直接推未复核的个人功能。

同步 main→建分支→实现最小切片→自查/受影响测试→提交→开 PR→填写模板→指定队友复核→修正→合并。冲突解决后再次运行相关检查，不因曾经通过就免检。

接口修改先改 contracts/Schema/fixture，再同步提供方和消费者。规则/快照/预算变化会影响基线，标明哪些结果不再可比。一个 PR 聚焦一个目标；HTML 示例与开发合同可分 commit，方便审查和回滚。

## 3. 审查与自动检查

普通 PR 至少一名队友；接口 PR 由提供者与至少一个消费者复核；时间/规则与评分 gate 请 B/D 检查。PR [模板](../.github/pull_request_template.md)要求差异、验证、风险和自查；适用项实际做完再勾，不适用注明理由。

CI 检查契约、正反例、基础披露/文档链接和已建立的模块构建/测试。只提供 README 的骨架明确 SKIP，不算服务测试通过。GitHub Actions 无模型/学校凭据，采用内容只读权限、固定官方 Actions SHA，不用 pull_request_target 执行 PR 代码。

分支保护/强制审核是否启用以设置为准。当前不在文档里冒称已设置；成员确定后可配置 required review + project-checks。CODEOWNERS 等真实用户名后填写，不能预填假账号。

## 4. 发布边界

只 stage 任务内文件，提交前检查 staged diff 与 self_check --staged。不能 git add 整个桌面目录。学校原始文件、用户成绩、.env、Cookie、私有 runs/held-out/gold 不推公开仓库。误传密钥先撤销/轮换；只删工作区不能消除历史泄露。

用户界面不展示调试堆栈和内部报告；老师报告是受限路由，不将隐藏题面公开放进静态 HTML。

参考：[邀请协作者](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)、[分支保护](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。
