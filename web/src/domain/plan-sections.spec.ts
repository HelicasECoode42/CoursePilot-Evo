import { describe, expect, it } from "vitest";
import type { Issue, PlanSection, PlanValidation } from "../contracts";
import {
  hasSections,
  sectionTone,
  unmodeledRuleCount,
  unmodeledRuleLine,
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

  it("shows only the rule count, without sheet locators", () => {
    expect(unmodeledRuleLine(UNMODELED)).toBe("有 2 条培养方案说明需人工确认");
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
