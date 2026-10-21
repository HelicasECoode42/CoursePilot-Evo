# System 1：Java Environment / Truth / Verifier

Java 21、Spring Boot、Apache POI、Spring Data JPA、MySQL/Flyway、JUnit 5。当前仅 A 的 `.xlsx` 培养计划导入器有初始可运行实现；B 的持久化、事务发布、认证、核验与业务 API 尚未实现。导入器只生成 draft 和质量问题，通过 `PublishPort` 接入 B；不会自行保存或声称已发布。首版其余范围和真实班次限制按 `../docs/trd/a-data.md`、`../docs/trd/b-verifier.md` 与[实施方案](../docs/10-java-import-and-rules.md)。

导入器使用说明见 [`importer/README.md`](importer/README.md)。
