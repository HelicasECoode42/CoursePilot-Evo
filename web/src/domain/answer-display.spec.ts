import { describe, expect, it } from "vitest";
import type { Issue, PlanValidation } from "../contracts";
import {
  collectUnknowns,
  describeVerification,
  hasSimulationMarker,
} from "./answer-display";

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

describe("受控缺口标记的展示门禁", () => {
  it("答复带 FAKE_MODEL 时，即使核验是 VALID+REAL_TIMETABLE 也不给绿色通过", () => {
    const view = describeVerification(
      validation({ verdict: "VALID", scope: "REAL_TIMETABLE" }),
      [issue("FAKE_MODEL", "本轮使用假模型")],
    );
    expect(view.allowGreenPass).toBe(false);
    expect(view.tone).toBe("simulated");
    expect(view.label).toContain("不代表真实核验");
  });

  it("FAKE_TOOL 同样降级", () => {
    const view = describeVerification(
      validation({ verdict: "VALID", scope: "REAL_TIMETABLE" }),
      [issue("FAKE_TOOL", "Java 未接线")],
    );
    expect(view.allowGreenPass).toBe(false);
  });

  it("没有受控缺口标记时，真实通过仍然是绿色", () => {
    const view = describeVerification(
      validation({ verdict: "VALID", scope: "REAL_TIMETABLE" }),
      [issue("TIME", "某节次未知")],
    );
    expect(view.allowGreenPass).toBe(true);
    expect(view.tone).toBe("real-pass");
  });

  it("本来就不该绿的结论不会被标记改写成 simulated", () => {
    const view = describeVerification(
      validation({ verdict: "UNKNOWN", scope: "COURSE_ONLY" }),
      [issue("FAKE_MODEL", "本轮使用假模型")],
    );
    expect(view.allowGreenPass).toBe(false);
    expect(view.tone).toBe("pending");
  });

  it("hasSimulationMarker 只认登记过的标记", () => {
    expect(hasSimulationMarker([issue("FAKE_MODEL", "x")])).toBe(true);
    expect(hasSimulationMarker([issue("FAKE_TOOL", "x")])).toBe(true);
    expect(hasSimulationMarker([issue("OFFERING_UNAVAILABLE", "x")])).toBe(
      false,
    );
    expect(hasSimulationMarker([])).toBe(false);
  });
});
