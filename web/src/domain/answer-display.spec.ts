import { describe, expect, it } from "vitest";
import type { Issue, PlanValidation } from "../contracts";
import { collectUnknowns, describeVerification } from "./answer-display";

const issue = (code: string, message: string): Issue => ({
  code,
  message,
  field: null,
  retryable: false,
});

function validation(overrides: Partial<PlanValidation> = {}): PlanValidation {
  return {
    verifierResultId: "verify-1",
    verdict: "UNKNOWN",
    scope: "COURSE_ONLY",
    curriculumSnapshotId: "curriculum-1",
    offeringSnapshotId: null,
    recordRevision: 1,
    violations: [],
    unknownChecks: [],
    performedChecks: [],
    sourceRefIds: [],
    ...overrides,
  };
}

describe("describeVerification", () => {
  it("only a real-timetable VALID verdict may render as a green pass", () => {
    const view = describeVerification(
      validation({ verdict: "VALID", scope: "REAL_TIMETABLE" }),
    );
    expect(view.tone).toBe("real-pass");
    expect(view.allowGreenPass).toBe(true);
  });

  it("keeps a course-only VALID verdict out of the green state", () => {
    const view = describeVerification(
      validation({ verdict: "VALID", scope: "COURSE_ONLY" }),
    );
    expect(view.tone).toBe("pending");
    expect(view.allowGreenPass).toBe(false);
    expect(view.label).toContain("时间待确认");
  });

  it("labels a simulated pass as simulated, never as the real timetable", () => {
    const view = describeVerification(
      validation({
        verdict: "VALID",
        scope: "SIMULATION",
        offeringSnapshotId: "offering-1",
      }),
    );
    expect(view.tone).toBe("simulated");
    expect(view.allowGreenPass).toBe(false);
    expect(view.detail).toContain("不代表本学期课表");
  });

  it("reports INVALID with the violation messages and no green pass", () => {
    const view = describeVerification(
      validation({
        verdict: "INVALID",
        scope: "REAL_TIMETABLE",
        violations: [issue("TIME_CONFLICT", "周一第1节与必修课冲突")],
      }),
    );
    expect(view.tone).toBe("conflict");
    expect(view.allowGreenPass).toBe(false);
    expect(view.detail).toContain("周一第1节与必修课冲突");
  });

  it("reports UNKNOWN with the unknown checks even when there are no violations", () => {
    const view = describeVerification(
      validation({
        unknownChecks: [issue("OFFERING_UNAVAILABLE", "未取得本学期班次")],
      }),
    );
    expect(view.tone).toBe("pending");
    expect(view.allowGreenPass).toBe(false);
    expect(view.detail).toContain("未取得本学期班次");
  });

  it("falls back to actionable text when the server lists no reason", () => {
    expect(
      describeVerification(validation({ verdict: "INVALID", violations: [] }))
        .detail,
    ).toContain("重新规划");
    expect(
      describeVerification(
        validation({ verdict: "UNKNOWN", unknownChecks: [] }),
      ).detail,
    ).toContain("补齐资料");
  });
});

describe("collectUnknowns", () => {
  it("merges answer-level and verification-level unknowns", () => {
    const merged = collectUnknowns(
      [issue("A", "答复级未知")],
      [
        validation({ unknownChecks: [issue("B", "候选一未知")] }),
        validation({ unknownChecks: [issue("C", "候选二未知")] }),
      ],
    );
    expect(merged.map((item) => item.code)).toEqual(["A", "B", "C"]);
  });

  it("drops duplicates so one gap is not listed twice", () => {
    const merged = collectUnknowns(
      [issue("DUP", "同一件事")],
      [
        validation({ unknownChecks: [issue("DUP", "同一件事")] }),
        validation({ unknownChecks: [issue("DUP", "同一件事")] }),
      ],
    );
    expect(merged).toHaveLength(1);
  });

  it("keeps same-code issues whose messages differ", () => {
    const merged = collectUnknowns(
      [issue("TIME", "周一未知")],
      [validation({ unknownChecks: [issue("TIME", "周二未知")] })],
    );
    expect(merged).toHaveLength(2);
  });
});
