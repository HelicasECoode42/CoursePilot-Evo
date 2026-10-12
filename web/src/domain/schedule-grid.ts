import type { PlanningDraft } from "./question-flow";

export const WEEKDAY_NAMES = [
  "周一",
  "周二",
  "周三",
  "周四",
  "周五",
  "周六",
  "周日",
] as const;
export const SCHEDULE_DAYS: readonly number[] = [1, 2, 3, 4, 5, 6, 7];
export const SCHEDULE_SECTIONS: readonly number[] = [
  1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
];

export type ScheduleStrength = "must" | "prefer";
export type ScheduleAction = "paint" | "erase";
export interface ScheduleSlot {
  dayOfWeek: number;
  section: number;
}
export interface NormalizedSchedule {
  blockedDays: number[];
  blockedSections: number[];
  blockedSlots: ScheduleSlot[];
}

type ScheduleLists = Pick<PlanningDraft, "mustSlots" | "preferSlots">;

const SLOT_KEY = /^([1-7])-(1[0-2]|[1-9])$/;

export function slotKey(dayOfWeek: number, section: number): string {
  return `${dayOfWeek}-${section}`;
}

export function parseSlotKey(key: string): ScheduleSlot | null {
  const match = SLOT_KEY.exec(key);
  return match
    ? { dayOfWeek: Number(match[1]), section: Number(match[2]) }
    : null;
}

export function dayKeys(dayOfWeek: number): string[] {
  return SCHEDULE_SECTIONS.map((section) => slotKey(dayOfWeek, section));
}

export function sectionKeys(section: number): string[] {
  return SCHEDULE_DAYS.map((dayOfWeek) => slotKey(dayOfWeek, section));
}

function listFor(lists: ScheduleLists, strength: ScheduleStrength): string[] {
  return strength === "must" ? lists.mustSlots : lists.preferSlots;
}

/** Erase when the cell already carries this strength, otherwise paint it. */
export function slotAction(
  lists: ScheduleLists,
  key: string,
  strength: ScheduleStrength,
): ScheduleAction {
  return listFor(lists, strength).includes(key) ? "erase" : "paint";
}

/** Erase a whole line only when every cell already carries this strength. */
export function lineAction(
  lists: ScheduleLists,
  keys: readonly string[],
  strength: ScheduleStrength,
): ScheduleAction {
  const current = new Set(listFor(lists, strength));
  return keys.every((key) => current.has(key)) ? "erase" : "paint";
}

function sortSlotKeys(keys: Iterable<string>): string[] {
  return [...keys]
    .map((key) => parseSlotKey(key))
    .filter((slot): slot is ScheduleSlot => slot !== null)
    .sort((a, b) => a.dayOfWeek - b.dayOfWeek || a.section - b.section)
    .map((slot) => slotKey(slot.dayOfWeek, slot.section));
}

/**
 * Pure update of both strength lists. Painting "must" removes the cell from
 * "prefer" and the reverse; erasing removes it from both. Invalid keys are
 * ignored and the result is kept in canonical day/section order.
 */
export function applyScheduleAction(
  lists: ScheduleLists,
  keys: readonly string[],
  strength: ScheduleStrength,
  action: ScheduleAction,
): ScheduleLists {
  const touched = new Set(keys.filter((key) => parseSlotKey(key) !== null));
  const mustSlots = new Set(lists.mustSlots);
  const preferSlots = new Set(lists.preferSlots);
  for (const key of touched) {
    if (action === "erase") {
      mustSlots.delete(key);
      preferSlots.delete(key);
    } else if (strength === "must") {
      preferSlots.delete(key);
      mustSlots.add(key);
    } else {
      mustSlots.delete(key);
      preferSlots.add(key);
    }
  }
  return {
    mustSlots: sortSlotKeys(mustSlots),
    preferSlots: sortSlotKeys(preferSlots),
  };
}

function runsOf(numbers: readonly number[]): number[][] {
  const runs: number[][] = [];
  numbers.forEach((value) => {
    const last = runs[runs.length - 1];
    if (last && last[last.length - 1] === value - 1) last.push(value);
    else runs.push([value]);
  });
  return runs;
}

function dayPhrase(days: readonly number[]): string {
  return runsOf(days)
    .flatMap((run) =>
      run.length >= 3
        ? [
            `${WEEKDAY_NAMES[run[0] - 1]}至${WEEKDAY_NAMES[run[run.length - 1] - 1]}`,
          ]
        : run.map((day) => WEEKDAY_NAMES[day - 1]),
    )
    .join("、");
}

function sectionPhrase(sections: readonly number[]): string {
  const out: string[] = [];
  const singles: number[] = [];
  let singleSlot = -1;
  runsOf(sections).forEach((run) => {
    if (run.length >= 2) {
      out.push(`第${run[0]}–${run[run.length - 1]}节`);
    } else {
      if (singleSlot < 0) {
        singleSlot = out.length;
        out.push("");
      }
      singles.push(run[0]);
    }
  });
  if (singleSlot >= 0) out[singleSlot] = `第${singles.join("、")}节`;
  return out.join("、");
}

/** Human-readable summary of selected cells, with whole-day/section folding. */
export function summarizeSlots(keys: readonly string[]): string {
  const chosen = new Set(keys.filter((key) => parseSlotKey(key) !== null));
  if (chosen.size === 0) return "未设置";
  const has = (dayOfWeek: number, section: number) =>
    chosen.has(slotKey(dayOfWeek, section));
  const fullDays = SCHEDULE_DAYS.filter((dayOfWeek) =>
    SCHEDULE_SECTIONS.every((section) => has(dayOfWeek, section)),
  );
  const fullSections = SCHEDULE_SECTIONS.filter((section) =>
    SCHEDULE_DAYS.every((dayOfWeek) => has(dayOfWeek, section)),
  );
  const parts = fullDays.map(
    (dayOfWeek) => `${WEEKDAY_NAMES[dayOfWeek - 1]}（整天）`,
  );
  fullSections.forEach((section) => parts.push(`每天第${section}节`));

  const groups = new Map<string, { sections: number[]; days: number[] }>();
  SCHEDULE_DAYS.forEach((dayOfWeek) => {
    if (fullDays.includes(dayOfWeek)) return;
    const sections = SCHEDULE_SECTIONS.filter(
      (section) => !fullSections.includes(section) && has(dayOfWeek, section),
    );
    if (sections.length === 0) return;
    const signature = sections.join(",");
    if (!groups.has(signature)) groups.set(signature, { sections, days: [] });
    groups.get(signature)!.days.push(dayOfWeek);
  });
  groups.forEach(({ days, sections }) =>
    parts.push(`${dayPhrase(days)} ${sectionPhrase(sections)}`),
  );
  return parts.join("、");
}

/**
 * Collapse selected cells into the contract's three kinds, in order:
 * full days first, then full sections over the remaining cells, then the
 * leftover single cells. Step two deliberately runs on what is left.
 */
export function normalizeScheduleKeys(
  keys: readonly string[],
): NormalizedSchedule {
  const remaining = new Set(keys.filter((key) => parseSlotKey(key) !== null));
  const blockedDays = SCHEDULE_DAYS.filter((dayOfWeek) =>
    dayKeys(dayOfWeek).every((key) => remaining.has(key)),
  );
  blockedDays.forEach((dayOfWeek) =>
    dayKeys(dayOfWeek).forEach((key) => remaining.delete(key)),
  );
  const blockedSections = SCHEDULE_SECTIONS.filter((section) =>
    sectionKeys(section).every((key) => remaining.has(key)),
  );
  blockedSections.forEach((section) =>
    sectionKeys(section).forEach((key) => remaining.delete(key)),
  );
  const blockedSlots = sortSlotKeys(remaining).map((key) => parseSlotKey(key)!);
  return { blockedDays, blockedSections, blockedSlots };
}
