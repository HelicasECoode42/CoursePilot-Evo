import { describe, expect, it } from "vitest";
import type { Issue, PlanSection, PlanValidation } from "../contracts";
import {
  hasSections,
  sectionLines,
  sectionTone,
  unmodeledRuleCount,
  verdictBadge,
} from "./plan-sections";

const UNMODELED: Issue = {
  code: "UNMODELED_CURRICULUM_RULES",
  message:
    "本培养方案有 2 条规则系统未建模、不参与核验（原表位置：测试表!A7、测试表!A9）",
  field: "curriculumSnapshotId",
  retryable: false,
};

function section(partial: Partial<PlanSection>): PlanSection {
  return {
    scope: "TIMETABLE",
    verdict: "VALID",
    violations: [],
    unknownChecks: [],
    ...partial,
  };
}

describe("plan verification sections", () => {
  it("maps each verdict to the student-facing badge", () => {
    expect(verdictBadge("VALID")).toBe("通过");
    expect(verdictBadge("INVALID")).toBe("不通过");
    expect(verdictBadge("UNKNOWN")).toBe("无法确认");
  });

  it("never renders VALID as pass unless the whole plan allows a green pass", () => {
    expect(sectionTone("VALID", true)).toBe("pass");
    expect(sectionTone("VALID", false)).toBe("pending");
    expect(sectionTone("UNKNOWN", true)).toBe("pending");
    expect(sectionTone("INVALID", true)).toBe("fail");
  });

  it("lists violations as Java text and unknowns through the explainer", () => {
    const lines = sectionLines(
      section({
        verdict: "INVALID",
        violations: [
          {
            code: "TIME_CONFLICT",
            message: "周一 1-2 节冲突",
            field: "items",
            retryable: false,
          },
        ],
        unknownChecks: [
          {
            code: "TIMETABLE_UNVERIFIED",
            message: "raw",
            field: "items",
            retryable: false,
          },
        ],
      }),
      () => "已翻译的说明",
    );
    expect(lines).toEqual([
      { key: "v0:TIME_CONFLICT", kind: "violation", text: "周一 1-2 节冲突" },
      { key: "u0:TIMETABLE_UNVERIFIED", kind: "unknown", text: "已翻译的说明" },
    ]);
  });

  it("shows only the rule count for unmodeled rules, without sheet locators", () => {
    const curriculum = section({
      scope: "CURRICULUM",
      verdict: "UNKNOWN",
      unknownChecks: [UNMODELED],
    });
    const lines = sectionLines(curriculum, () => "不应使用");
    expect(lines).toHaveLength(1);
    expect(lines[0].text).toBe("有 2 条培养方案说明需人工确认");
    expect(lines[0].text).not.toContain("测试表");
  });

  it("counts unmodeled rules from Java text and falls back to 1", () => {
    expect(unmodeledRuleCount(UNMODELED)).toBe(2);
    expect(unmodeledRuleCount({ ...UNMODELED, message: "未知格式" })).toBe(1);
  });

  it("detects whether a validation carries sections", () => {
    const base = { sections: undefined } as unknown as PlanValidation;
    expect(hasSections(base)).toBe(false);
    expect(hasSections({ ...base, sections: [] })).toBe(false);
    expect(hasSections({ ...base, sections: [section({})] })).toBe(true);
  });
});

describe("分项未知项去重", () => {
  it("lists one line for identical unknown items repeated by the verifier", () => {
    const repeated: Issue = {
      code: "CONSTRAINT_UNVERIFIABLE",
      message: "CONSTRAINT_UNVERIFIABLE: 必避时段缺少已核验班次时间",
      field: "constraints",
      retryable: false,
    };
    const lines = sectionLines(
      section({
        scope: "TIMETABLE",
        verdict: "UNKNOWN",
        unknownChecks: [repeated, { ...repeated }],
      }),
      () => "时间类条件（例如必避时段）无法确认",
    );
    expect(lines.map((line) => line.text)).toEqual([
      "时间类条件（例如必避时段）无法确认",
    ]);
  });

  it("merges items whose different raw messages explain to the same sentence", () => {
    const first: Issue = {
      code: "CONSTRAINT_UNVERIFIABLE",
      message: "约束 A 无法核验",
      field: null,
      retryable: false,
    };
    const second: Issue = { ...first, message: "约束 B 无法核验" };
    const lines = sectionLines(
      section({
        scope: "TIMETABLE",
        verdict: "UNKNOWN",
        unknownChecks: [first, second],
      }),
      () => "时间类条件（例如必避时段）无法确认",
    );
    expect(lines).toHaveLength(1);
  });

  it("keeps distinct unknown items", () => {
    const lines = sectionLines(
      section({
        scope: "TIMETABLE",
        verdict: "UNKNOWN",
        unknownChecks: [
          { code: "A", message: "甲", field: null, retryable: false },
          { code: "B", message: "乙", field: null, retryable: false },
        ],
      }),
      (issue) => issue.message,
    );
    expect(lines.map((line) => line.text)).toEqual(["甲", "乙"]);
  });
});
