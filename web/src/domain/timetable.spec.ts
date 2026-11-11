import { describe, expect, it } from "vitest";
import type { Meeting } from "../contracts";
import {
  buildTimetable,
  compactWeeksText,
  meetingsText,
  shortMeetingsText,
} from "./timetable";

const WEEKS = Array.from({ length: 16 }, (_, index) => index + 1);

describe("meetingsText", () => {
  it("writes a meeting as weekday, section range and week range", () => {
    const meeting: Meeting = {
      dayOfWeek: 1,
      sectionStart: 1,
      sectionEnd: 2,
      weeks: WEEKS,
    };
    expect(meetingsText([meeting])).toBe("周一 第1-2节 · 第1–16周");
  });

  it("uses a single section label when start and end are the same", () => {
    const meeting: Meeting = {
      dayOfWeek: 3,
      sectionStart: 5,
      sectionEnd: 5,
      weeks: [2, 4],
    };
    expect(meetingsText([meeting])).toBe("周三 第5节 · 第2、4周");
  });

  it("says the time is unconfirmed when there is nothing readable", () => {
    expect(meetingsText([])).toBe("上课时间未能确认");
    expect(
      meetingsText([
        { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: [] },
      ]),
    ).toBe("上课时间未能确认");
  });

  it("never hides an unreadable meeting behind the readable ones", () => {
    const text = meetingsText([
      { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: WEEKS },
      { dayOfWeek: 2, sectionStart: 1, sectionEnd: 2, weeks: [] },
    ]);
    expect(text).toBe("周一 第1-2节 · 第1–16周；另有一段时间无法确认");
  });
});

describe("buildTimetable 未排进课表的原因", () => {
  it("没有选定班次时，用 Java 给出的真实原因代替通用说明", () => {
    const view = buildTimetable(
      [
        {
          courseCode: "08306029",
          classId: null,
          offering: null,
          missing: "NOT_SELECTED",
        },
      ],
      { "08306029": "可选班次都与学生设定的必避时段冲突" },
    );
    expect(view.gaps).toEqual([
      {
        courseCode: "08306029",
        classId: null,
        message: "08306029：可选班次都与学生设定的必避时段冲突，未纳入课表。",
      },
    ]);
  });

  it("没有原因时仍然给出通用说明", () => {
    const view = buildTimetable([
      {
        courseCode: "CS101",
        classId: null,
        offering: null,
        missing: "NOT_SELECTED",
      },
    ]);
    expect(view.gaps[0].message).toContain("还没有选定班次");
  });

  describe("week view and compact week text", () => {
    it("compactWeeksText writes runs as 1-8周 and joins gaps with 、", () => {
      expect(compactWeeksText([1, 2, 3, 4, 5, 6, 7, 8])).toBe("1-8周");
      expect(compactWeeksText([1, 2, 3, 4, 10])).toBe("1-4、10周");
      expect(compactWeeksText([])).toBe("");
    });

    it("only keeps meetings whose weeks overlap the chosen half, and keeps the placement count", () => {
      const first: Meeting = {
        dayOfWeek: 1,
        sectionStart: 1,
        sectionEnd: 2,
        weeks: [1, 2, 3, 4, 5, 6, 7, 8],
      };
      const last: Meeting = {
        dayOfWeek: 2,
        sectionStart: 3,
        sectionEnd: 4,
        weeks: [9, 10, 11, 12, 13, 14, 15, 16],
      };
      const offering = {
        courseCode: "CS102",
        classId: "CS102-01",
        teacherKey: null,
        teacherText: "测试教师（合成）",
        credits: 3,
        capacity: 60,
        meetingTextRaw: "测试时间",
        meetings: [first, last],
        parseStatus: "PARSED" as const,
        sourceRefId: "source:CS102-01",
      };
      const sources = [
        { courseCode: "CS102", classId: "CS102-01", offering, missing: null },
      ];

      const all = buildTimetable(sources);
      expect(all.cells.has("1-1")).toBe(true);
      expect(all.cells.has("2-3")).toBe(true);

      const front = buildTimetable(sources, {}, { weekView: "FIRST_8" });
      expect(front.cells.has("1-1")).toBe(true);
      expect(front.cells.has("2-3")).toBe(false);
      expect(front.gaps).toEqual([]);
      expect(front.placedCount).toBe(1);

      const back = buildTimetable(sources, {}, { weekView: "LAST_8" });
      expect(back.cells.has("1-1")).toBe(false);
      expect(back.cells.get("2-3")?.[0].weeks).toEqual(last.weeks);

      const second = {
        ...sources[0],
        courseCode: "CS103",
        classId: "CS103-01",
        offering: { ...offering, meetings: [{ ...first, weeks: last.weeks }] },
      };
      const disjoint = buildTimetable([...sources, second]);
      expect(disjoint.cells.get("1-1")).toHaveLength(2);
      expect(disjoint.overlapCells.has("1-1")).toBe(false);
      second.offering.meetings = [first];
      expect(buildTimetable([...sources, second]).overlapCells.has("1-1")).toBe(
        true,
      );
    });
  });
});

describe("shortMeetingsText", () => {
  it("writes a course row time compactly and writes the shared week range once", () => {
    const meetings: Meeting[] = [
      { dayOfWeek: 2, sectionStart: 7, sectionEnd: 8, weeks: WEEKS.slice(8) },
      { dayOfWeek: 3, sectionStart: 5, sectionEnd: 6, weeks: WEEKS.slice(8) },
    ];
    expect(shortMeetingsText(meetings)).toBe("周二7-8 周三5-6 · 9-16周");
  });

  it("labels each segment when the weeks differ", () => {
    const meetings: Meeting[] = [
      {
        dayOfWeek: 1,
        sectionStart: 1,
        sectionEnd: 1,
        weeks: [1, 2, 3, 4, 5, 6, 7, 8],
      },
      { dayOfWeek: 4, sectionStart: 3, sectionEnd: 4, weeks: [9, 10] },
    ];
    expect(shortMeetingsText(meetings)).toBe(
      "周一1（1-8周） 周四3-4（9-10周）",
    );
  });

  it("never draws an unreadable segment as if it were clear", () => {
    const meetings: Meeting[] = [
      { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: WEEKS },
      { dayOfWeek: 9, sectionStart: 1, sectionEnd: 2, weeks: WEEKS },
    ];
    expect(shortMeetingsText(meetings)).toBe(
      "周一1-2 · 1-16周；另有时段无法确认",
    );
    expect(shortMeetingsText([meetings[1]])).toBe("时间未能确认");
  });
});
