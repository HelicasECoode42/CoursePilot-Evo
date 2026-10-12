import { describe, expect, it } from "vitest";
import { emptyPlanningDraft } from "./question-flow";
import {
  applyScheduleAction,
  dayKeys,
  lineAction,
  normalizeScheduleKeys,
  parseSlotKey,
  sectionKeys,
  slotAction,
  summarizeSlots,
} from "./schedule-grid";

const allKeys = (): string[] => {
  const keys: string[] = [];
  for (let day = 1; day <= 7; day += 1) {
    for (let section = 1; section <= 12; section += 1) {
      keys.push(`${day}-${section}`);
    }
  }
  return keys;
};

describe("schedule grid keys", () => {
  it('accepts only 星期 1-7 and 节次 1-12 in the "星期-节次" form', () => {
    expect(parseSlotKey("1-1")).toEqual({ dayOfWeek: 1, section: 1 });
    expect(parseSlotKey("7-12")).toEqual({ dayOfWeek: 7, section: 12 });
    expect(parseSlotKey("0-1")).toBeNull();
    expect(parseSlotKey("8-1")).toBeNull();
    expect(parseSlotKey("1-13")).toBeNull();
    expect(parseSlotKey("1-01")).toBeNull();
  });
});

describe("summarizeSlots", () => {
  const days = (from: number, to: number) => {
    const keys: string[] = [];
    for (let day = from; day <= to; day += 1) keys.push(`${day}-1`, `${day}-2`);
    return keys;
  };

  it("folds consecutive weekdays and sections into ranges", () => {
    expect(summarizeSlots(days(1, 5))).toBe("周一至周五 第1–2节");
  });

  it("lists non-consecutive weekdays that share one section", () => {
    expect(summarizeSlots(["6-5", "7-5"])).toBe("周六、周日 第5节");
  });

  it("lists separated sections in one weekday without a range", () => {
    expect(summarizeSlots(["3-1", "3-3"])).toBe("周三 第1、3节");
  });

  it("names a fully selected weekday as a whole day", () => {
    expect(summarizeSlots(dayKeys(1))).toBe("周一（整天）");
  });

  it("names a fully selected section as every day", () => {
    expect(summarizeSlots(sectionKeys(1))).toBe("每天第1节");
  });

  it("reports an empty selection as 未设置", () => {
    expect(summarizeSlots([])).toBe("未设置");
  });
});

describe("normalizeScheduleKeys", () => {
  it("turns a fully selected weekday into one BLOCK_DAY", () => {
    expect(normalizeScheduleKeys(dayKeys(3))).toEqual({
      blockedDays: [3],
      blockedSections: [],
      blockedSlots: [],
    });
  });

  it("turns a fully selected section into one BLOCK_SECTION", () => {
    expect(normalizeScheduleKeys(sectionKeys(4))).toEqual({
      blockedDays: [],
      blockedSections: [4],
      blockedSlots: [],
    });
  });

  it("keeps scattered cells as BLOCK_SLOT entries", () => {
    expect(normalizeScheduleKeys(["3-2", "1-1"])).toEqual({
      blockedDays: [],
      blockedSections: [],
      blockedSlots: [
        { dayOfWeek: 1, section: 1 },
        { dayOfWeek: 3, section: 2 },
      ],
    });
  });

  it("never produces BLOCK_DAY and BLOCK_SECTION for the same full selection", () => {
    const result = normalizeScheduleKeys(allKeys());
    expect(result).toEqual({
      blockedDays: [1, 2, 3, 4, 5, 6, 7],
      blockedSections: [],
      blockedSlots: [],
    });
  });

  it("runs the section step on the cells left after whole days are removed", () => {
    // Day 1 is full, section 2 is full on all days: the section step sees only 6 days left.
    const keys = [...dayKeys(1), ...sectionKeys(2)];
    const result = normalizeScheduleKeys(keys);
    expect(result.blockedDays).toEqual([1]);
    expect(result.blockedSections).toEqual([]);
    expect(result.blockedSlots).toHaveLength(6);
    expect(result.blockedSlots.every((slot) => slot.section === 2)).toBe(true);
  });

  it("ignores keys outside the grid", () => {
    expect(normalizeScheduleKeys(["0-1", "8-1", "1-13", "2-2", "2-2"])).toEqual(
      {
        blockedDays: [],
        blockedSections: [],
        blockedSlots: [{ dayOfWeek: 2, section: 2 }],
      },
    );
  });
});

describe("applyScheduleAction", () => {
  it("keeps must and prefer exclusive when a cell changes strength", () => {
    const base = emptyPlanningDraft();
    const asPrefer = applyScheduleAction(base, ["2-3"], "prefer", "paint");
    expect(asPrefer).toEqual({ mustSlots: [], preferSlots: ["2-3"] });
    const asMust = applyScheduleAction(asPrefer, ["2-3"], "must", "paint");
    expect(asMust).toEqual({ mustSlots: ["2-3"], preferSlots: [] });
  });

  it("erases a cell from both strengths", () => {
    const lists = { mustSlots: ["2-3"], preferSlots: ["4-4"] };
    expect(applyScheduleAction(lists, ["2-3", "4-4"], "must", "erase")).toEqual(
      { mustSlots: [], preferSlots: [] },
    );
  });

  it("does not clear the other strength when one is edited", () => {
    const lists = { mustSlots: ["1-1"], preferSlots: ["2-2"] };
    expect(applyScheduleAction(lists, ["1-1"], "must", "erase")).toEqual({
      mustSlots: [],
      preferSlots: ["2-2"],
    });
  });

  it("ignores invalid keys and keeps canonical day/section order", () => {
    const next = applyScheduleAction(
      emptyPlanningDraft(),
      ["5-2", "bad", "9-1", "1-1"],
      "must",
      "paint",
    );
    expect(next.mustSlots).toEqual(["1-1", "5-2"]);
  });
});

describe("paint decisions", () => {
  it("erases a cell only when it already has the requested strength", () => {
    const lists = { mustSlots: ["1-1"], preferSlots: ["1-2"] };
    expect(slotAction(lists, "1-1", "must")).toBe("erase");
    expect(slotAction(lists, "1-1", "prefer")).toBe("paint");
    expect(slotAction(lists, "1-2", "prefer")).toBe("erase");
  });

  it("clears a whole line only when every cell already has the strength", () => {
    const keys = dayKeys(2);
    const full = { mustSlots: keys, preferSlots: [] };
    const partial = { mustSlots: keys.slice(1), preferSlots: [] };
    expect(lineAction(full, keys, "must")).toBe("erase");
    expect(lineAction(partial, keys, "must")).toBe("paint");
  });
});
