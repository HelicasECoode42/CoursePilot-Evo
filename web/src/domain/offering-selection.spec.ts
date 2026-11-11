import { describe, expect, it } from "vitest";
import {
  defaultOfferingSnapshotId,
  isOfferingUsable,
  isOfficialUnverified,
  offeringBanner,
  planUsesSimulation,
  planningModeFor,
  type OfferingCandidate,
} from "./offering-selection";

/** 合成的开课快照摘要（测试数据，非真实班次）。 */
function snap(
  snapshotId: string,
  sourceKind: OfferingCandidate["sourceKind"],
  sourceValidation: OfferingCandidate["sourceValidation"],
  createdAt = "2026-09-01T00:00:00Z",
): OfferingCandidate {
  return {
    snapshotId,
    kind: "OFFERING",
    state: "PUBLISHED",
    sourceKind,
    sourceValidation,
    createdAt,
  };
}

const VERIFIED = snap("off-verified", "BROWSER_SNAPSHOT", "VERIFIED");
const OFFICIAL = snap("off-official", "OFFICIAL_DOCUMENT", "UNVERIFIED");
const DEMO = snap("off-demo", "SYNTHETIC", "SYNTHETIC");
const UNVERIFIED_BROWSER = snap(
  "off-browser",
  "BROWSER_SNAPSHOT",
  "UNVERIFIED",
);

describe("defaultOfferingSnapshotId", () => {
  it("prefers a verified offering over an official timetable", () => {
    expect(defaultOfferingSnapshotId([OFFICIAL, VERIFIED], "http")).toBe(
      "off-verified",
    );
  });

  it("falls back to the official timetable when nothing is verified", () => {
    expect(
      defaultOfferingSnapshotId([UNVERIFIED_BROWSER, OFFICIAL], "http"),
    ).toBe("off-official");
  });

  it("never auto-picks a synthetic offering in real (http) mode", () => {
    expect(defaultOfferingSnapshotId([DEMO], "http")).toBeNull();
    expect(
      defaultOfferingSnapshotId([DEMO, UNVERIFIED_BROWSER], "http"),
    ).toBeNull();
  });

  it("picks the synthetic offering only in simulation or fixture mode", () => {
    expect(defaultOfferingSnapshotId([DEMO], "simulation")).toBe("off-demo");
    expect(defaultOfferingSnapshotId([DEMO], "fixture")).toBe("off-demo");
  });

  it("among equal sources picks the newest createdAt", () => {
    const older = snap(
      "off-old",
      "BROWSER_SNAPSHOT",
      "VERIFIED",
      "2026-08-01T00:00:00Z",
    );
    const newer = snap(
      "off-new",
      "BROWSER_SNAPSHOT",
      "VERIFIED",
      "2026-09-15T00:00:00Z",
    );
    expect(defaultOfferingSnapshotId([older, newer], "http")).toBe("off-new");
    expect(defaultOfferingSnapshotId([newer, older], "http")).toBe("off-new");
  });

  it("ignores unpublished or non-offering items and returns null when none usable", () => {
    const rejected = { ...VERIFIED, state: "REJECTED" as const };
    const curriculum = { ...VERIFIED, kind: "CURRICULUM" as const };
    expect(
      defaultOfferingSnapshotId([rejected, curriculum], "http"),
    ).toBeNull();
    expect(defaultOfferingSnapshotId([], "simulation")).toBeNull();
  });

  it("does not treat an unverified browser snapshot as usable in real mode", () => {
    expect(isOfferingUsable(UNVERIFIED_BROWSER, "http")).toBe(false);
  });
});

describe("planningModeFor", () => {
  it("derives SIMULATION from a synthetic snapshot and REAL otherwise", () => {
    expect(planningModeFor("simulation", DEMO)).toBe("SIMULATION");
    expect(planningModeFor("simulation", VERIFIED)).toBe("REAL");
    expect(planningModeFor("http", OFFICIAL)).toBe("REAL");
  });

  it("keeps fixture as a global override to SIMULATION", () => {
    expect(planningModeFor("fixture", VERIFIED)).toBe("SIMULATION");
    expect(planningModeFor("fixture", null)).toBe("SIMULATION");
  });

  it("without a selected snapshot uses the client mode", () => {
    expect(planningModeFor("http", null)).toBe("REAL");
    expect(planningModeFor("simulation", null)).toBe("SIMULATION");
  });
});

describe("offeringBanner", () => {
  it("says synthetic data for a SYNTHETIC snapshot", () => {
    expect(offeringBanner(DEMO)).toEqual({
      tone: "synthetic",
      text: "课表为模拟数据",
    });
  });

  it("says the official timetable is pending manual verification", () => {
    expect(offeringBanner(OFFICIAL)).toEqual({
      tone: "official",
      text: "课表来自学校公布的课程表（2026-2027 秋季），尚在人工核验",
    });
  });

  it("hides the note for a verified snapshot (no verifier or date in the summary)", () => {
    expect(offeringBanner(VERIFIED)).toBeNull();
  });

  it("shows nothing when no snapshot is selected", () => {
    expect(offeringBanner(null)).toBeNull();
  });
});

describe("学校课表待核验与方案模拟判断", () => {
  it("只有 OFFICIAL_DOCUMENT 且 UNVERIFIED 才算学校课表待核验", () => {
    expect(
      isOfficialUnverified({
        snapshotId: "o",
        kind: "OFFERING",
        state: "PUBLISHED",
        sourceKind: "OFFICIAL_DOCUMENT",
        sourceValidation: "UNVERIFIED",
        createdAt: "2026-11-01T00:00:00Z",
      }),
    ).toBe(true);
    expect(isOfficialUnverified(null)).toBe(false);
    expect(
      isOfficialUnverified({
        snapshotId: "v",
        kind: "OFFERING",
        state: "PUBLISHED",
        sourceKind: "OFFICIAL_DOCUMENT",
        sourceValidation: "VERIFIED",
        createdAt: "2026-11-01T00:00:00Z",
      }),
    ).toBe(false);
  });

  it("方案判决为 REAL_TIMETABLE 或 COURSE_ONLY 时不算模拟，即使模拟客户端也一样", () => {
    expect(planUsesSimulation(["REAL_TIMETABLE", "COURSE_ONLY"])).toBe(false);
    expect(planUsesSimulation([])).toBe(false);
    expect(planUsesSimulation(["REAL_TIMETABLE", "SIMULATION"])).toBe(true);
  });
});
