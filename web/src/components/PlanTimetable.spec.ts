import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { CourseOffering, Meeting } from "../contracts";
import type { TimetableSource } from "../domain/timetable";
import PlanTimetable from "./PlanTimetable.vue";

const WEEKS = Array.from({ length: 16 }, (_, index) => index + 1);
const MON_1_2: Meeting = {
  dayOfWeek: 1,
  sectionStart: 1,
  sectionEnd: 2,
  weeks: WEEKS,
};
const THU_7_8: Meeting = {
  dayOfWeek: 4,
  sectionStart: 7,
  sectionEnd: 8,
  weeks: WEEKS,
};

/** 测试用班次（合成数据）：只关心时间与解析状态。 */
function offering(
  courseCode: string,
  classId: string,
  meetings: Meeting[],
  parseStatus: CourseOffering["parseStatus"] = "PARSED",
): CourseOffering {
  return {
    courseCode,
    classId,
    teacherKey: null,
    teacherText: "测试教师（合成）",
    credits: 3,
    capacity: 60,
    meetingTextRaw: meetings.length > 0 ? "测试时间" : "时间待定",
    meetings,
    parseStatus,
    sourceRefId: `source:${classId}`,
  };
}

function placed(courseCode: string, item: CourseOffering): TimetableSource {
  return { courseCode, classId: item.classId, offering: item, missing: null };
}

/** 取某个「星期-节次」格子的文字。sr-only 的 caption 不在 tbody 里，不会干扰。 */
function cellText(
  wrapper: ReturnType<typeof mount>,
  section: number,
  day: number,
): string {
  const row = wrapper.findAll("tbody tr")[section - 1];
  // 第 0 列是节次表头，星期从第 1 列开始。
  return row.findAll("td")[day - 1].text();
}

describe("PlanTimetable", () => {
  it("draws a PARSED meeting in the matching weekday and section cells", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [placed("CS102", offering("CS102", "CS102-01", [MON_1_2]))],
      },
    });

    // 周一第1、2节有课；其他格子为空。
    expect(cellText(wrapper, 1, 1)).toContain("CS102");
    expect(cellText(wrapper, 2, 1)).toContain("CS102-01");
    expect(cellText(wrapper, 3, 1)).toBe("");
    expect(cellText(wrapper, 1, 2)).toBe("");
    expect(wrapper.find(".timetable-detail").text()).toContain(
      "测试教师（合成）",
    );
    expect(wrapper.find(".timetable-detail").text()).toContain("第1–16周");
  });

  it("keeps UNPARSED and INVALID offerings out of the grid with a clear note", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [
          placed("CS103", offering("CS103", "CS103-03", [], "UNPARSED")),
          placed("CS104", offering("CS104", "CS104-01", [THU_7_8], "INVALID")),
        ],
      },
    });

    expect(wrapper.find("table").exists()).toBe(false);
    const gaps = wrapper.find(".timetable-gaps");
    expect(gaps.exists()).toBe(true);
    expect(gaps.text()).toContain(
      "CS103（班次 CS103-03）：这门课的时间无法解析，未纳入课表。",
    );
    expect(gaps.text()).toContain(
      "CS104（班次 CS104-01）：这门课的时间无法解析，未纳入课表。",
    );
  });

  it("does not draw a non-PARSED offering even when it still carries meetings", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [
          placed("CS105", offering("CS105", "CS105-01", [MON_1_2], "INVALID")),
          placed("CS102", offering("CS102", "CS102-01", [THU_7_8])),
        ],
      },
    });

    // 只有 PARSED 的 CS102 进入格子；CS105 的 INVALID 时间不能冒充课表。
    expect(cellText(wrapper, 1, 1)).toBe("");
    expect(cellText(wrapper, 7, 4)).toContain("CS102");
    expect(wrapper.find(".timetable-gaps").text()).toContain("CS105");
  });

  it("does not draw a meeting whose sections fall outside the 1-12 grid", () => {
    const beyond: Meeting = {
      dayOfWeek: 2,
      sectionStart: 11,
      sectionEnd: 14,
      weeks: WEEKS,
    };
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [placed("CS108", offering("CS108", "CS108-01", [beyond]))],
      },
    });

    expect(wrapper.find("table").exists()).toBe(false);
    expect(wrapper.find(".timetable-gaps").text()).toContain(
      "CS108（班次 CS108-01）：有一段时间节次超出第1–12节，无法画出，未纳入课表。",
    );
  });

  it("says a course with no read offering is not in the timetable", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [
          {
            courseCode: "CS106",
            classId: "CS106-01",
            offering: null,
            missing: "NOT_READ",
          },
          {
            courseCode: "CS107",
            classId: null,
            offering: null,
            missing: "NOT_SELECTED",
          },
        ],
      },
    });

    expect(wrapper.find(".timetable-gaps").text()).toContain(
      "CS106（班次 CS106-01）：这门课的时间没能从班次资料中读到，未纳入课表。",
    );
    expect(wrapper.find(".timetable-gaps").text()).toContain(
      "CS107：还没有选定班次，时间未知，未纳入课表。",
    );
  });

  it("warns that the timetable is unverified when scope is not REAL_TIMETABLE", () => {
    const sources = [placed("CS102", offering("CS102", "CS102-01", [MON_1_2]))];
    for (const scope of ["COURSE_ONLY", "SIMULATION"] as const) {
      const wrapper = mount(PlanTimetable, { props: { scope, sources } });
      expect(wrapper.text()).toContain(
        "此课表来自未经核验的班次资料，不代表真实课表，不构成无冲突证明。",
      );
    }

    const real = mount(PlanTimetable, {
      props: { scope: "REAL_TIMETABLE", sources },
    });
    expect(real.text()).not.toContain("未经核验的班次资料");
  });

  it("renders an empty list without errors", () => {
    const wrapper = mount(PlanTimetable, {
      props: { scope: "REAL_TIMETABLE", sources: [] },
    });

    expect(wrapper.find("table").exists()).toBe(false);
    expect(wrapper.text()).toContain("课表为空");
  });

  it("keeps two overlapping courses in the same cell instead of hiding one", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [
          placed("CS102", offering("CS102", "CS102-01", [MON_1_2])),
          placed("CS103", offering("CS103", "CS103-01", [MON_1_2])),
        ],
      },
    });

    expect(cellText(wrapper, 1, 1)).toContain("CS102");
    expect(cellText(wrapper, 1, 1)).toContain("CS103");
    expect(wrapper.find("td.timetable-cell--multi").exists()).toBe(true);
  });
});
