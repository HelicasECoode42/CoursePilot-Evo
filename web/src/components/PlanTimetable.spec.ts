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
    expect(wrapper.find(".timetable-cards").text()).toContain(
      "测试教师（合成）",
    );
    expect(wrapper.find(".timetable-cards").text()).toContain("第1–16周");
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

describe("PlanTimetable detail cards", () => {
  it("shows the course name, real teacher and a human-readable time instead of raw meeting text", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [placed("CS102", offering("CS102", "CS102-01", [MON_1_2]))],
        courseNames: { CS102: "程序设计基础（测试）" },
      },
    });

    const card = wrapper.get("li.timetable-card");
    expect(card.text()).toContain("程序设计基础（测试）");
    expect(card.text()).toContain("CS102");
    expect(card.text()).toContain("测试教师（合成）");
    expect(card.text()).toContain("周一 第1-2节 · 第1–16周");
    expect(card.text()).toContain("CS102-01");
    expect(card.text()).not.toContain("{第");
  });

  it("falls back to the course code when no course name is known", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [placed("CS102", offering("CS102", "CS102-01", [MON_1_2]))],
      },
    });

    expect(wrapper.get("li.timetable-card strong").text()).toBe("CS102");
  });
});

describe("PlanTimetable unplaced courses", () => {
  it("lists courses without a usable section in a side list titled 未排进课表", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [
          placed("CS101", offering("CS101", "CS101-01", [MON_1_2])),
          {
            courseCode: "CS102",
            classId: null,
            offering: null,
            missing: "NOT_SELECTED",
          },
        ],
      },
    });
    const side = wrapper.find(".timetable-gaps");
    expect(side.find("h4").text()).toBe("未排进课表");
    expect(side.text()).toContain(
      "CS102：还没有选定班次，时间未知，未纳入课表。",
    );
    expect(wrapper.find(".timetable-layout--split").exists()).toBe(true);
  });

  it("does not split the layout when nothing is placed", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        sources: [
          {
            courseCode: "CS102",
            classId: null,
            offering: null,
            missing: "NOT_SELECTED",
          },
        ],
      },
    });
    expect(wrapper.find(".timetable-gaps").exists()).toBe(true);
    expect(wrapper.find(".timetable-layout--split").exists()).toBe(false);
  });

  it("格子显示课程名、老师与周次，不只显示课程号", () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        courseNames: { CS102: "数据库" },
        sources: [
          placed(
            "CS102",
            offering("CS102", "CS102-01", [
              {
                dayOfWeek: 1,
                sectionStart: 1,
                sectionEnd: 2,
                weeks: WEEKS.slice(0, 8),
              },
            ]),
          ),
        ],
      },
    });
    const chip = wrapper.find("td .timetable-chip");
    expect(chip.find("strong").text()).toBe("数据库");
    expect(chip.text()).toContain("测试教师（合成）");
    expect(chip.text()).toContain("1-8周");
    expect(chip.text()).toContain("CS102-01");
  });

  it("前八周 / 后八周切换按周次过滤格子，明细仍按整学期", async () => {
    const wrapper = mount(PlanTimetable, {
      props: {
        scope: "REAL_TIMETABLE",
        courseNames: { CS102: "数据库" },
        sources: [
          placed(
            "CS102",
            offering("CS102", "CS102-01", [
              {
                dayOfWeek: 1,
                sectionStart: 1,
                sectionEnd: 2,
                weeks: WEEKS.slice(0, 8),
              },
              {
                dayOfWeek: 4,
                sectionStart: 7,
                sectionEnd: 8,
                weeks: WEEKS.slice(8),
              },
            ]),
          ),
        ],
      },
    });
    const button = (label: string) =>
      wrapper
        .findAll("button.timetable-weeks__btn")
        .find((item) => item.text() === label)!;
    expect(button("全学期").attributes("aria-pressed")).toBe("true");
    expect(cellText(wrapper, 1, 1)).toContain("数据库");
    expect(cellText(wrapper, 7, 4)).toContain("数据库");

    await button("前八周（1-8）").trigger("click");
    expect(button("前八周（1-8）").attributes("aria-pressed")).toBe("true");
    expect(cellText(wrapper, 1, 1)).toContain("数据库");
    expect(cellText(wrapper, 7, 4)).toBe("");

    await button("后八周（9-16）").trigger("click");
    expect(cellText(wrapper, 1, 1)).toBe("");
    expect(cellText(wrapper, 7, 4)).toContain("9-16周");
    // 明细卡片不受周次视图影响。
    expect(wrapper.find(".timetable-cards").text()).toContain("第1–8周");
  });
});
