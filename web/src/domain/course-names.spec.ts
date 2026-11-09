import { describe, expect, it } from "vitest";
import type { Course } from "../contracts";
import {
  buildCourseFactIndex,
  buildCourseNameIndex,
  describeSelectedCourse,
  limitCourseCodes,
} from "./course-names";

const course = (courseCode: string, name: string): Course => ({
  courseCode,
  name,
  credits: 3,
  category: "公共基础课",
  sourceRefIds: ["ref"],
  suggestedTerm: null,
});

describe("课程名查表", () => {
  it("一号一名时直接给名字", () => {
    const index = buildCourseNameIndex([
      course("00864096", "工程制图与计算机绘图基础"),
    ]);
    expect(index["00864096"]).toBe("工程制图与计算机绘图基础");
  });

  it("同号不同名时标注还有几门，不假装只有一门", () => {
    // 体育1-6、英语1-6 在真实培养方案里就是同号不同名。
    const index = buildCourseNameIndex([
      course("008532xx", "体育1"),
      course("008532xx", "体育2"),
      course("008532xx", "体育3"),
    ]);
    expect(index["008532xx"]).toBe("体育1 等 3 门同号课程");
  });

  it("同号同名重复出现不算多门", () => {
    const index = buildCourseNameIndex([
      course("01014125", "微积分(1-3)"),
      course("01014125", "微积分(1-3)"),
    ]);
    expect(index["01014125"]).toBe("微积分(1-3)");
  });
});

describe("长列表折叠", () => {
  const codes = Array.from({ length: 16 }, (_, i) => `C${i + 1}`);

  it("超过上限时只给前几门，并说清还有几门", () => {
    const result = limitCourseCodes(codes, 5, false);
    expect(result.shown).toHaveLength(5);
    expect(result.hiddenCount).toBe(11);
  });

  it("展开后全给，hiddenCount 归零", () => {
    expect(limitCourseCodes(codes, 5, true)).toEqual({
      shown: codes,
      hiddenCount: 0,
    });
  });

  it("没超过上限时不折叠", () => {
    expect(limitCourseCodes(["A", "B"], 5, false)).toEqual({
      shown: ["A", "B"],
      hiddenCount: 0,
    });
  });
});

describe("已选课程标签", () => {
  it("有名字时写成「课程名（课程号）· 学分」，课程号只出现一次", () => {
    const label = describeSelectedCourse("08305092", {
      name: "Java程序设计",
      credits: 3,
    });
    expect(label).toBe("Java程序设计（08305092）· 3 学分");
    expect(label.split("08305092")).toHaveLength(2);
  });

  it("学分未知时照实写「学分未知」", () => {
    expect(
      describeSelectedCourse("08305092", {
        name: "Java程序设计",
        credits: null,
      }),
    ).toBe("Java程序设计（08305092）· 学分未知");
  });

  it("查不到名字时只给课程号并注明名称未加载，不重复课程号", () => {
    const label = describeSelectedCourse("08305092", null);
    expect(label).toBe("课程号 08305092（名称未加载）");
    expect(label.split("08305092")).toHaveLength(2);
  });
});

describe("课程事实合并", () => {
  it("先来的来源优先，名字与学分取自同一来源", () => {
    const index = buildCourseFactIndex([
      [{ courseCode: "A1", name: "目录名", credits: 2 }],
      [{ courseCode: "A1", name: "学校名", credits: 5 }],
    ]);
    expect(index.get("A1")).toEqual({ name: "目录名", credits: 2 });
  });

  it("空白名字不算名字，会落到后面的来源", () => {
    const index = buildCourseFactIndex([
      [{ courseCode: "A2", name: "   ", credits: 1 }],
      [{ courseCode: "A2", name: "学校名", credits: null }],
    ]);
    expect(index.get("A2")).toEqual({ name: "学校名", credits: null });
  });

  it("所有来源都没有名字时不给事实", () => {
    const index = buildCourseFactIndex([
      [{ courseCode: "A3", name: null, credits: 2 }],
    ]);
    expect(index.has("A3")).toBe(false);
  });
});
