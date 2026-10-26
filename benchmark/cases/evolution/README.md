# evolution 题面

本目录只放**对 Evolver 可见**的题面。命名 `G<组号>-<三位序号>.json`（例：`G1-001.json`）。

判据字段与模板见 `../../docs/07-benchmark-protocol.md` 与 case 模板（先存于仓库外 `_D1_plan/templates/`）。

held-out 题面在 `../held-out/`（Evolver 不得读取），gold 仍存放在工作区之外的独立根，运行评测时才注入；
边界见 `../held-out/README.md`。
理由：工作区内的文件即使写进 .gitignore，仍可被 `git add -f` 带走（Issue #1 的场景）。

## 命名与引用约定

- 文件名 = `caseId`，形如 `G1-001.json`；`split` 必须与本目录名一致。
- 题面文件**只放题面**：`caseId / groupId / split / curriculumSnapshotId / offeringSnapshotId / inputFixtureRef / userQuery / rubricVersion / notes`。
  `requiredFacts`、`requiredUnknowns`、`requiredClarification`、`forbiddenClaims`、`requiredSourceRefs` 属于判据，
  只放在工作区之外的标注目录，题面里出现即视为答案泄漏（校验器报 E06）。
- `requiredSourceRefs` 的 `refId` 只能用 ASCII（契约模式 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$`），
  中文表名写进 `locator`。工作表编号约定：`cs2024-s1` = 计科学1（非直招），`cs2024-s2` = 计科学2，`cs2024-s3` = 计科学3，
  直招用 `cs2024-d1/d2/d3`。
- 校验：`python benchmark/validate_cases.py`（标注目录默认工作区外的 `restricted/gold`，可用 `--gold-root` 或
  环境变量 `COURSEPILOT_GOLD_ROOT` 指过去）。
- `locator` 必须是**原文全文**，不得节选或改写；核对方式：`python ..\_D1_plan\check_source_cells.py`（在仓库目录下跑）。
