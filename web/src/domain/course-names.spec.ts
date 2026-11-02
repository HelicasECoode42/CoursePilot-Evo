import { describe, expect, it } from "vitest";
import type { Course } from "../contracts";
import {
  buildCourseNameIndex,
  describeCourse,
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

  it("查不到名字就只给课程号，不编一个名字出来", () => {
    expect(describeCourse("UNKNOWN", () => null)).toBe("UNKNOWN");
  });

  it("查得到就拼成「课程号 · 课程名」", () => {
    expect(describeCourse("CS101", () => "Java 程序设计")).toBe(
      "CS101 · Java 程序设计",
    );
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
