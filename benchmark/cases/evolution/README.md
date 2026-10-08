# evolution 题面

本目录只放**对 Evolver 可见**的题面。命名 `G<组号>-<三位序号>.json`（例：`G1-001.json`）。

判据字段与模板见 `../../docs/07-benchmark-protocol.md` 与 case 模板（先存于仓库外 `_D1_plan/templates/`）。

held-out 与 gold **不在本仓库**：存放在工作区之外的独立根，运行评测时才注入。
理由：工作区内的文件即使写进 .gitignore，仍可被 `git add -f` 带走（Issue #1 的场景）。
