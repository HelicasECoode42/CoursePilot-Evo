import { describe, expect, it } from "vitest";
import type { Course } from "../contracts";
import { coursesSuggestedBeforeYear } from "./academic-year";

const course = (
  code: string,
  term: string | null,
  category = "公共基础课",
): Course => ({
  courseCode: code,
  name: code,
  credits: 3,
  category,
  suggestedTerm: term,
  sourceRefIds: ["source:1"],
});

describe("年级辅助", () => {
  it("仅列出过去年级可明确识别的基础课程，排除选修、占位和待复核安排", () => {
    const courses = [
      course("A", "第一学年 第1学期"),
      course("B", "第二学年 第6学期"),
      course("C", "第三学年 第7学期"),
      course("D", "第一学年 多学期安排（逐项复核）"),
      course("E", "第一学年 第2学期", "专业选修课"),
      course("0000xx", "第一学年 第1学期"),
      course("DUP", "第一学年 第1学期"),
      course("DUP", "第一学年 第2学期"),
      course("UNKNOWN", null),
    ];
    expect(
      coursesSuggestedBeforeYear(courses, 3).map((item) => item.courseCode),
    ).toEqual(["A", "B"]);
    expect(coursesSuggestedBeforeYear(courses, 1)).toEqual([]);
  });
});
