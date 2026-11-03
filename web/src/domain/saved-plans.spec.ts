import { describe, expect, it } from "vitest";
import {
  SAVED_PLANS_KEY,
  SAVED_PLANS_LIMIT,
  buildSavedPlan,
  deleteSavedPlan,
  loadSavedPlans,
  parseSavedPlans,
  saveNewPlan,
  type SavedPlan,
  type SavedPlanInput,
} from "./saved-plans";

/** 内存版存储：与 Storage 的两个方法同形。 */
function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
  };
}

const THROWING = {
  getItem: () => {
    throw new Error("denied");
  },
  setItem: () => {
    throw new Error("quota");
  },
};

const INPUT: SavedPlanInput = {
  planId: "plan-a",
  planNumber: 1,
  edited: false,
  courses: [
    {
      courseCode: "CS102",
      name: "程序设计基础",
      credits: 3,
      tag: "必修",
      classId: "CS102-01",
      teacherText: "测试教师（合成）",
      timeText: "周一 第1-2节 · 第1–16周",
      meetings: [
        { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: [1, 2] },
      ],
    },
  ],
  verdict: { scope: "REAL_TIMETABLE", verdict: "VALID", label: "通过" },
  planningContext: {
    targetTerm: "NEXT_SEMESTER",
    timetableReferenceSnapshotId: "offering-1",
    timetableReferenceTermId: "2026-2027-1",
    timetableSourceValidation: "UNVERIFIED",
  },
};

function plan(id: string): SavedPlan {
  return buildSavedPlan(INPUT, id, new Date("2026-11-03T08:00:00Z"));
}

describe("buildSavedPlan", () => {
  it("copies only the whitelisted fields, never grades or extra result data", () => {
    const dirty = {
      ...INPUT,
      grade: 95,
      token: "secret",
      courses: [{ ...INPUT.courses[0], grade: 88, courseReviews: ["x"] }],
      planningContext: {
        ...INPUT.planningContext!,
        rawPrompt: "full prompt",
      },
    } as unknown as SavedPlanInput;

    const saved = buildSavedPlan(
      dirty,
      "saved-1",
      new Date("2026-11-03T08:00:00Z"),
    );
    const text = JSON.stringify(saved);

    expect(text).not.toContain("grade");
    expect(text).not.toContain("secret");
    expect(text).not.toContain("courseReviews");
    expect(text).not.toContain("rawPrompt");
    expect(saved.savedAt).toBe("2026-11-03T08:00:00.000Z");
    expect(saved.courses[0].meetings).toEqual([
      { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: [1, 2] },
    ]);
  });

  it("copies meetings so later edits to the input do not change the saved copy", () => {
    const saved = plan("saved-copy");
    INPUT.courses[0].meetings[0].weeks.push(99);
    expect(saved.courses[0].meetings[0].weeks).toEqual([1, 2]);
    INPUT.courses[0].meetings[0].weeks.pop();
  });
});

describe("saved plan storage", () => {
  it("saves new copies first and reads them back", () => {
    const storage = memoryStorage();
    const first = saveNewPlan(plan("a"), storage);
    const second = saveNewPlan(plan("b"), storage);

    expect(first.ok && second.ok).toBe(true);
    const loaded = loadSavedPlans(storage);
    expect(loaded.map((item) => item.id)).toEqual(["b", "a"]);
    expect(storage.data.has(SAVED_PLANS_KEY)).toBe(true);
  });

  it("refuses to save past the limit instead of dropping an older copy", () => {
    const full = Array.from({ length: SAVED_PLANS_LIMIT }, (_, index) =>
      plan(`old-${index}`),
    );
    const storage = memoryStorage({ [SAVED_PLANS_KEY]: JSON.stringify(full) });

    const outcome = saveNewPlan(plan("new"), storage);

    expect(outcome).toMatchObject({ ok: false, reason: "LIMIT" });
    expect(loadSavedPlans(storage)).toHaveLength(SAVED_PLANS_LIMIT);
    expect(loadSavedPlans(storage).some((item) => item.id === "new")).toBe(
      false,
    );
  });

  it("reports a storage failure without throwing", () => {
    const outcome = saveNewPlan(plan("x"), THROWING);
    expect(outcome).toMatchObject({ ok: false, reason: "STORAGE", plans: [] });
  });

  it("reads as empty when storage is missing, blocked or holds broken JSON", () => {
    expect(loadSavedPlans(null)).toEqual([]);
    expect(loadSavedPlans(THROWING)).toEqual([]);
    expect(
      loadSavedPlans(memoryStorage({ [SAVED_PLANS_KEY]: "{not json" })),
    ).toEqual([]);
    expect(saveNewPlan(plan("y"), null)).toMatchObject({
      ok: false,
      reason: "STORAGE",
    });
  });

  it("drops malformed entries instead of rendering them", () => {
    const good = plan("good");
    const parsed = parseSavedPlans([
      good,
      { id: "bad", savedAt: "x" },
      { ...good, id: "bad-course", courses: [{ courseCode: 3 }] },
      null,
    ]);
    expect(parsed.map((item) => item.id)).toEqual(["good"]);
    expect(parseSavedPlans({ not: "an array" })).toEqual([]);
  });

  it("deletes one copy and keeps the rest", () => {
    const storage = memoryStorage();
    saveNewPlan(plan("a"), storage);
    saveNewPlan(plan("b"), storage);

    const remaining = deleteSavedPlan("a", storage);

    expect(remaining.map((item) => item.id)).toEqual(["b"]);
    expect(loadSavedPlans(storage).map((item) => item.id)).toEqual(["b"]);
  });

  it("keeps the list unchanged when deleting cannot be written back", () => {
    const storage = memoryStorage();
    saveNewPlan(plan("a"), storage);
    const blocked = {
      getItem: storage.getItem,
      setItem: THROWING.setItem,
    };

    expect(deleteSavedPlan("a", blocked).map((item) => item.id)).toEqual(["a"]);
  });
});
