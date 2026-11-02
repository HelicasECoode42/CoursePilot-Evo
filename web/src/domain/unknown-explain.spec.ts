import { describe, expect, it } from "vitest";
import type { Issue } from "../contracts";
import {
  explainUnknownIssue,
  isVerificationLevelUnknown,
  UNKNOWN_EXPLANATIONS,
} from "./unknown-explain";

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
