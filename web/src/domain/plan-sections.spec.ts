import { describe, expect, it } from "vitest";
import type { Issue, PlanSection, PlanValidation } from "../contracts";
import {
  hasSections,
  sectionLines,
  sectionTone,
  unmodeledRulesNote,
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

  it("keeps the unmodeled-rule locators from Java and adds the manual-check note for CURRICULUM", () => {
    const curriculum = section({
      scope: "CURRICULUM",
      verdict: "UNKNOWN",
      unknownChecks: [UNMODELED],
    });
    const lines = sectionLines(curriculum, () => "不应使用");
    expect(lines).toHaveLength(1);
    expect(lines[0].text).toContain("测试表!A7");
    expect(unmodeledRulesNote(curriculum)).toBe(
      "这些培养方案规则需要人工确认，系统暂不自动判断。",
    );
  });

  it("adds no unmodeled note to the timetable section or to other curriculum unknowns", () => {
    expect(
      unmodeledRulesNote(
        section({ scope: "TIMETABLE", unknownChecks: [UNMODELED] }),
      ),
    ).toBeNull();
    expect(
      unmodeledRulesNote(
        section({
          scope: "CURRICULUM",
          verdict: "UNKNOWN",
          unknownChecks: [
            {
              code: "CREDITS_UNKNOWN",
              message: "x",
              field: null,
              retryable: false,
            },
          ],
        }),
      ),
    ).toBeNull();
  });

  it("detects whether a validation carries sections", () => {
    const base = { sections: undefined } as unknown as PlanValidation;
    expect(hasSections(base)).toBe(false);
    expect(hasSections({ ...base, sections: [] })).toBe(false);
    expect(hasSections({ ...base, sections: [section({})] })).toBe(true);
  });
});
