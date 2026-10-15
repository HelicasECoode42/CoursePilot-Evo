# 五人分工与模块阅读入口

先读[团队总览](15-team-baseline-and-batches.md)，了解学生流程、评测流程、核心对象与协作关系，再读自己的模块页。模块页前半讲完整业务功能，后半保留 TRD 实现。当前服务尚未实现。

| 模块 | 负责人 | 一句话交付 | 阅读入口 |
| --- | --- | --- | --- |
| A 数据导入与资料整理 | JiangYiLin-Q121 | 让项目能使用正确、统一、有来源的培养计划、已修课程、评价和班次参考资料 | [业务说明与 TRD](trd/a-data.md) |
| B Java 数据与规则核验 | mira-xu | 让系统准确回答课程事实、学生已满足哪些要求，以及推荐方案哪些条件通过、违规或无法确认 | [业务说明与 TRD](trd/b-verifier.md) |
| C 需求理解与智能规划 | goat-yang | 把学生的目标变成有依据、可解释、可修改的课程推荐；信息不足时问清楚，条件无法同时满足时说明取舍 | [业务说明与 TRD](trd/c-agent.md) |
| D 验收、评测与策略改进 | amorfatiii | 证明系统哪些能力可靠，找出重复失败，并用真实评测决定 Agent 策略修改是否应该保留 | [业务说明与 TRD](trd/d-benchmark-rsi.md) |
| E 学生网页与老师报告 | HelicasECoode42 | 让学生顺利完成提供资料、表达目标、理解推荐和修改方案的过程；让老师通过独立入口查看评测与策略改进结果 | [业务说明与 TRD](trd/e-web-integration.md) |

A/B 共享 Java 工程，A 整理输入与导入入口，B 保存资料并维护唯一规则核验。C 管页面网关与 Agent；D 用相同 Agent 评测并决定策略保留/回滚；E 管学生页面和独立老师报告。统筹由 HelicasECoode42 负责。

- 本期做哪部分：[业务任务与周次](19-delivery-plan.md)、[Project](https://github.com/users/HelicasECoode42/projects/1)。
- 怎么领任务/提 PR/复核/登记 Bug：[操作指南](18-team-progress-guide.md)。
- 技术不熟先学什么：[模块学习入口](08-learning-repos.md)。
- 字段与行为怎么衔接：[公共契约](04-infrastructure-workflow.md)、[总体 TRD](03-trd.md)。

账号确认不代表仓库邀请已接受；邀请状态以 GitHub 实际显示为准。公开记录使用账号；原始学校资料、个人成绩和私有评测答案按工程规范留在受控位置。
