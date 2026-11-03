import { describe, expect, it } from "vitest";
import type { PlanningContext } from "../contracts";
import { planningContextLine, termLabel } from "./planning-context";

const context = (partial: Partial<PlanningContext>): PlanningContext => ({
  targetTerm: "NEXT_SEMESTER",
  timetableReferenceSnapshotId: "offering-snapshot:demo",
  timetableReferenceTermId: "2026-2027-1",
  timetableSourceValidation: "UNVERIFIED",
  ...partial,
});

describe("planning context line", () => {
  it("names the target term and the unverified timetable reference", () => {
    expect(planningContextLine(context({}))).toBe(
      "为下学期规划 · 暂用 2026-2027 秋季课表参考（未核验）",
    );
  });

  it("says the reference term is unknown when the snapshot is unknown", () => {
    expect(
      planningContextLine(
        context({
          timetableReferenceSnapshotId: null,
          timetableReferenceTermId: null,
          timetableSourceValidation: null,
        }),
      ),
    ).toBe("为下学期规划 · 课表参考学期未知");
  });

  it("falls back to the target term alone for an older answer without context", () => {
    expect(planningContextLine(undefined)).toBe("为下学期规划");
    expect(planningContextLine(null)).toBe("为下学期规划");
  });

  it("does not turn a verified reference into anything stronger than its source says", () => {
    expect(
      planningContextLine(context({ timetableSourceValidation: "VERIFIED" })),
    ).toContain("（已核验）");
  });
});

describe("termLabel", () => {
  it("maps the suffix to a season and keeps unknown formats as they are", () => {
    expect(termLabel("2026-2027-2")).toBe("2026-2027 春季");
    expect(termLabel("2025-FALL")).toBe("2025-FALL");
  });
});
