/**
 * 方案课表：把已选班次的上课时段画到「星期 × 节次」网格上。
 *
 * 坐标系完全复用 schedule-grid.ts（星期 1-7、节次 1-12、slotKey），不另造一套。
 * 纯函数，无 IO、无框架依赖，可直接单测。
 *
 * 关键门禁：只有 parseStatus 为 PARSED 且时段完整的班次才能进入格子。
 * 无法解析、读不到、超出网格范围的一律不画，并写进 gaps 原样告诉学生。
 * 把「画不出来」当成「没有冲突」是这里最严重的错误。
 */

import type { CourseOffering, Meeting, PlanItem } from "../contracts";
import { SCHEDULE_DAYS, slotKey } from "./schedule-grid";

/** 一门方案课程在课表上的来源。offering 为 null 时 missing 说明为什么画不出来。 */
export interface TimetableSource {
  courseCode: string;
  classId: string | null;
  offering: CourseOffering | null;
  missing: "NOT_SELECTED" | "NOT_READ" | "NOT_FOUND" | null;
}

/** 格子里的一条：某门课的某一段时间。 */
export interface TimetableEntry {
  courseCode: string;
  classId: string;
  teacherText: string;
  meetingTextRaw: string;
  meeting: Meeting;
}

/** 已真正画进课表的班次（每门一条，用于下方的明细列表）。 */
export interface PlacedCourse {
  courseCode: string;
  classId: string;
  teacherText: string;
  meetingTextRaw: string;
  weeksText: string;
}

/** 没有画进课表的原因，直接展示给学生。 */
export interface TimetableGap {
  courseCode: string;
  classId: string | null;
  message: string;
}

export interface TimetableView {
  /** key 为 slotKey(星期, 节次)。同一格多门课时全部保留，不覆盖。 */
  cells: Map<string, TimetableEntry[]>;
  placed: PlacedCourse[];
  gaps: TimetableGap[];
}

/** 班次资料的读取结果；status 为 UNKNOWN 时整张列表都不能当作事实。 */
export interface OfferingListRead {
  status: "OK" | "UNKNOWN";
  items: readonly CourseOffering[];
}

const LAST_SECTION = 12;

/** 把方案课程和班次资料对齐成课表来源。找不到、读不到都要留下原因，不静默跳过。 */
export function resolveTimetableSources(
  items: readonly PlanItem[],
  lists: Readonly<Record<string, OfferingListRead | undefined>>,
): TimetableSource[] {
  return items.map((item) => {
    if (item.classId === null) {
      return {
        courseCode: item.courseCode,
        classId: null,
        offering: null,
        missing: "NOT_SELECTED",
      };
    }
    const list = lists[item.courseCode];
    if (list === undefined || list.status !== "OK") {
      return {
        courseCode: item.courseCode,
        classId: item.classId,
        offering: null,
        missing: "NOT_READ",
      };
    }
    const offering =
      list.items.find((candidate) => candidate.classId === item.classId) ??
      null;
    return {
      courseCode: item.courseCode,
      classId: item.classId,
      offering,
      missing: offering === null ? "NOT_FOUND" : null,
    };
  });
}

/** 时段自身的问题；返回 null 表示可以画。 */
function meetingProblem(meeting: Meeting): string | null {
  if (
    !Number.isInteger(meeting.dayOfWeek) ||
    !SCHEDULE_DAYS.includes(meeting.dayOfWeek)
  ) {
    return "星期数值不在周一至周日之内";
  }
  if (
    !Number.isInteger(meeting.sectionStart) ||
    !Number.isInteger(meeting.sectionEnd) ||
    meeting.sectionStart < 1 ||
    meeting.sectionEnd > LAST_SECTION ||
    meeting.sectionEnd < meeting.sectionStart
  ) {
    return `节次超出第1–${LAST_SECTION}节`;
  }
  if (meeting.weeks.length === 0) return "周次没有确认";
  return null;
}

/** 把连续周次折成「第1–16周」，不连续的用顿号。 */
export function weeksText(weeks: readonly number[]): string {
  if (weeks.length === 0) return "周次未确认";
  const sorted = [...new Set(weeks)].sort((a, b) => a - b);
  const runs: number[][] = [];
  for (const week of sorted) {
    const last = runs[runs.length - 1];
    if (last && last[last.length - 1] === week - 1) last.push(week);
    else runs.push([week]);
  }
  return `第${runs
    .map((run) =>
      run.length >= 2 ? `${run[0]}–${run[run.length - 1]}` : `${run[0]}`,
    )
    .join("、")}周`;
}

export function buildTimetable(
  sources: readonly TimetableSource[],
): TimetableView {
  const cells = new Map<string, TimetableEntry[]>();
  const placed: PlacedCourse[] = [];
  const gaps: TimetableGap[] = [];

  for (const source of sources) {
    const { courseCode, classId, offering } = source;
    const label =
      classId === null ? courseCode : `${courseCode}（班次 ${classId}）`;

    if (offering === null || classId === null) {
      const reason =
        source.missing === "NOT_SELECTED"
          ? "还没有选定班次，时间未知"
          : source.missing === "NOT_FOUND"
            ? "班次不在当前班次资料里"
            : "这门课的时间没能从班次资料中读到";
      gaps.push({
        courseCode,
        classId,
        message: `${label}：${reason}，未纳入课表。`,
      });
      continue;
    }

    // parseStatus 不是 PARSED 时绝不画格子，哪怕 meetings 里碰巧有数据。
    if (offering.parseStatus !== "PARSED" || offering.meetings.length === 0) {
      gaps.push({
        courseCode,
        classId,
        message: `${label}：这门课的时间无法解析，未纳入课表。`,
      });
      continue;
    }

    const placedWeeks: number[] = [];
    for (const meeting of offering.meetings) {
      const problem = meetingProblem(meeting);
      if (problem !== null) {
        gaps.push({
          courseCode,
          classId,
          message: `${label}：有一段时间${problem}，无法画出，未纳入课表。`,
        });
        continue;
      }
      placedWeeks.push(...meeting.weeks);
      const entry: TimetableEntry = {
        courseCode,
        classId,
        teacherText: offering.teacherText,
        meetingTextRaw: offering.meetingTextRaw,
        meeting,
      };
      for (
        let section = meeting.sectionStart;
        section <= meeting.sectionEnd;
        section += 1
      ) {
        const key = slotKey(meeting.dayOfWeek, section);
        cells.set(key, [...(cells.get(key) ?? []), entry]);
      }
    }

    if (placedWeeks.length > 0) {
      placed.push({
        courseCode,
        classId,
        teacherText: offering.teacherText,
        meetingTextRaw: offering.meetingTextRaw,
        weeksText: weeksText(placedWeeks),
      });
    }
  }

  return { cells, placed, gaps };
}
