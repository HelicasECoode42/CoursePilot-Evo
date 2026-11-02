import { describe, expect, it } from "vitest";
import type { Issue } from "../contracts";
import {
  explainUnknownIssue,
  isVerificationLevelUnknown,
  sectionNotAssignedReason,
  UNKNOWN_EXPLANATIONS,
  unplacedReasonsFor,
} from "./unknown-explain";
import type { PlanValidation } from "../contracts";

const issue = (code: string, message = "") =>
  ({ code, message, field: null, retryable: false }) as Issue;

describe("未知项文案", () => {
  it("用 Java 实际发出的代码 UNMODELED_CURRICULUM_RULES 给出说明，不再依赖旧代码 UNMODELED_RULE", () => {
    const text = explainUnknownIssue(issue("UNMODELED_CURRICULUM_RULES", "x"));
    expect(text).toContain("培养方案");
    expect(text).not.toContain("有一项课程或班次信息无法确认");
    expect(UNKNOWN_EXPLANATIONS).not.toHaveProperty("UNMODELED_RULE");
  });

  it("PENDING_COURSE 逐门列出课程号与课程名，并说明学生可以做什么", () => {
    const names = { "08305011": "操作系统(1-2)", "08305012": "操作系统(1-2)" };
    const a = explainUnknownIssue(
      issue(
        "PENDING_COURSE",
        "课程 08305011 在修或结果未知，学科基础课 类别的缺口不能确定",
      ),
      names,
    );
    const b = explainUnknownIssue(
      issue(
        "PENDING_COURSE",
        "课程 08305012 在修或结果未知，学科基础课 类别的缺口不能确定",
      ),
      names,
    );
    expect(a).toContain("操作系统(1-2)（08305011）");
    expect(a).toContain("学科基础课类别");
    expect(a).toContain("学业资料");
    expect(b).toContain("08305012");
    expect(a).not.toBe(b);
  });

  it("课程名读不到时只显示课程号，不编造课程名", () => {
    const text = explainUnknownIssue(
      issue(
        "PENDING_COURSE",
        "课程 99999999 在修或结果未知，通识课 类别的缺口不能确定",
      ),
    );
    expect(text.startsWith("99999999 在修")).toBe(true);
  });

  it("PENDING_COURSE 的 message 不符合格式时退回通用说明，而不是报错", () => {
    const text = explainUnknownIssue(issue("PENDING_COURSE", "奇怪的格式"));
    expect(text).toContain("排查详情");
  });

  it("每个已知代码都有可执行的建议（含“可以”或“请”）", () => {
    for (const [code, text] of Object.entries(UNKNOWN_EXPLANATIONS)) {
      expect(text, code).toMatch(/可以|请/);
    }
  });

  it("未知代码给出通用文案", () => {
    expect(explainUnknownIssue(issue("SOMETHING_NEW"))).toContain("排查详情");
  });

  it("换班后只有核验级的未知项被标记为过时，答复级项保留", () => {
    expect(isVerificationLevelUnknown("TIMETABLE_UNVERIFIED")).toBe(true);
    expect(isVerificationLevelUnknown("UNMODELED_CURRICULUM_RULES")).toBe(true);
    expect(isVerificationLevelUnknown("FAKE_MODEL")).toBe(false);
    expect(isVerificationLevelUnknown("PENDING_COURSE")).toBe(false);
  });

  it("班次未核验的说明指向可执行的动作（选定班次并重新核验）", () => {
    const text = explainUnknownIssue(issue("TIMETABLE_UNVERIFIED"));
    expect(text).toContain("选定班次");
    expect(text).toContain("重新核验");
  });
});

describe("未选定班次与真实课表文案", () => {
  it("SECTION_NOT_ASSIGNED 说出课程名、课程号与 Java 给出的真实原因", () => {
    const text = explainUnknownIssue(
      issue(
        "SECTION_NOT_ASSIGNED",
        "课程 08306029：可选班次都与学生设定的必避时段冲突",
      ),
      { "08306029": "数据库原理" },
    );
    expect(text).toContain("数据库原理（08306029）");
    expect(text).toContain("可选班次都与学生设定的必避时段冲突");
    expect(text).not.toContain("还没有选定班次");
  });

  it("SECTION_NOT_ASSIGNED 读不到课程名时只显示课程号", () => {
    const text = explainUnknownIssue(
      issue("SECTION_NOT_ASSIGNED", "课程 08306029：本学期没有开课"),
    );
    expect(text.startsWith("08306029 没有选定班次：本学期没有开课")).toBe(true);
  });

  it("SECTION_NOT_ASSIGNED 格式不符时退回这一代码的静态说明，不报错", () => {
    const text = explainUnknownIssue(
      issue("SECTION_NOT_ASSIGNED", "奇怪的格式"),
    );
    expect(text).toContain("没有选定班次");
    expect(text).toContain("可以");
  });

  it("学校课表待核验时，TIMETABLE_UNVERIFIED 说明正在人工核验，不说「模拟来源」", () => {
    const text = explainUnknownIssue(
      issue("TIMETABLE_UNVERIFIED"),
      {},
      { officialUnverified: true },
    );
    expect(text).toContain(
      "课表来自学校公布的课程表，正在人工核验；核验通过前不能判为通过",
    );
    expect(text).not.toContain("模拟");
    expect(text).not.toContain("没有选定班次");
  });

  it("没有学校课表上下文时，TIMETABLE_UNVERIFIED 不再把原因说成「不是模拟来源」", () => {
    const text = explainUnknownIssue(issue("TIMETABLE_UNVERIFIED"));
    expect(text).not.toContain("不是模拟来源");
    expect(text).toContain("不能判为通过");
  });

  it("学校课表待核验时，CONSTRAINT_UNVERIFIABLE 不说「缺少已核验的班次时间」", () => {
    const official = explainUnknownIssue(
      issue(
        "CONSTRAINT_UNVERIFIABLE",
        "第 0 条硬约束（BLOCK_DAY）需要已验证的班次时间",
      ),
      {},
      { officialUnverified: true },
    );
    expect(official).toContain("学校公布的课程表");
    expect(official).not.toContain("缺少已核验的班次时间");
  });

  it("没有班次来源时，CONSTRAINT_UNVERIFIABLE 才说缺少已核验的班次时间", () => {
    const text = explainUnknownIssue(
      issue(
        "CONSTRAINT_UNVERIFIABLE",
        "第 0 条硬约束（BLOCK_DAY）需要已验证的班次时间",
      ),
    );
    expect(text).toContain("缺少已核验的班次时间");
  });

  it("sectionNotAssignedReason 只解析 SECTION_NOT_ASSIGNED 的课程号与原因", () => {
    expect(
      sectionNotAssignedReason(
        issue(
          "SECTION_NOT_ASSIGNED",
          "课程 08306029：可选班次都与学生设定的必避时段冲突",
        ),
      ),
    ).toEqual({
      courseCode: "08306029",
      reason: "可选班次都与学生设定的必避时段冲突",
    });
    expect(sectionNotAssignedReason(issue("TIMETABLE_UNVERIFIED"))).toBeNull();
  });
});

describe("Java 的 SECTION_UNASSIGNED 与未排进课表的版本来源", () => {
  const validation = (unknownChecks: Issue[]) =>
    ({ unknownChecks, violations: [] }) as unknown as PlanValidation;

  it("SECTION_UNASSIGNED（Java 的分项代码）与 SECTION_NOT_ASSIGNED 同样给出课程名和可执行建议", () => {
    const text = explainUnknownIssue(
      issue(
        "SECTION_UNASSIGNED",
        "课程 08305011 未指定班次，无法核验其时间与班次归属",
      ),
      { "08305011": "操作系统(1-2)" },
    );
    expect(text).toContain("操作系统(1-2)（08305011）");
    expect(text).toContain("没有选定班次");
    expect(text).toContain("重新核验");
    expect(text).not.toContain("这一项暂时无法确认");
  });

  it("SECTION_UNASSIGNED 读不到课程名时只显示课程号", () => {
    const text = explainUnknownIssue(
      issue("SECTION_UNASSIGNED", "课程 08305011 未指定班次，无法核验"),
    );
    expect(text.startsWith("08305011 没有选定班次")).toBe(true);
  });

  it("SECTION_UNASSIGNED 两个代码都视为核验级，换班后过时", () => {
    expect(isVerificationLevelUnknown("SECTION_UNASSIGNED")).toBe(true);
    expect(isVerificationLevelUnknown("SECTION_NOT_ASSIGNED")).toBe(true);
  });

  it("未换班时用答复里 Python 给的具体原因，覆盖判决里 Java 的通用说明", () => {
    const reasons = unplacedReasonsFor(
      [issue("SECTION_NOT_ASSIGNED", "课程 08306029：本学期没有开课")],
      [
        {
          replaced: false,
          verification: validation([
            issue("SECTION_UNASSIGNED", "课程 08306029 未指定班次，无法核验"),
          ]),
        },
      ],
    );
    expect(reasons).toEqual({ "08306029": "本学期没有开课" });
  });

  it("换班后不再读答复里的旧原因，只看当前判决", () => {
    const reasons = unplacedReasonsFor(
      [issue("SECTION_NOT_ASSIGNED", "课程 08306029：本学期没有开课")],
      [
        {
          replaced: true,
          verification: validation([
            issue("SECTION_UNASSIGNED", "课程 08305011 未指定班次，无法核验"),
          ]),
        },
      ],
    );
    expect(reasons).not.toHaveProperty("08306029");
    expect(reasons["08305011"]).toContain("没有为这门课选定班次");
  });

  it("没有判决时，未换班的方案仍能用答复里的原因", () => {
    const reasons = unplacedReasonsFor(
      [issue("SECTION_NOT_ASSIGNED", "课程 08306029：本学期没有开课")],
      [{ replaced: false, verification: null }],
    );
    expect(reasons).toEqual({ "08306029": "本学期没有开课" });
  });
});
