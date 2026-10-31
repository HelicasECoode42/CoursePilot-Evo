import { describe, expect, it } from "vitest";
import type { Course } from "../contracts";
import {
  coursesSuggestedBeforeYear,
  describeYearSuggestionGap,
} from "./academic-year";

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

describe("解释为什么一门都没列出来", () => {
  it("有课可列时不报任何原因", () => {
    const courses = [course("A", "第一学年 第1学期")];
    expect(describeYearSuggestionGap(courses, 3)).toEqual({ kind: "none" });
  });

  it("整份方案都没有建议学期时，说的是方案缺数据，不是这个年级没课", () => {
    // 实测：SYN_0263… 这份快照 105 门课的 suggestedTerm 全是 null，
    // 于是选哪个年级都是 0 门。这跟「大一没有更早的学年」是两回事。
    const courses = [course("A", null), course("B", null), course("C", null)];
    expect(describeYearSuggestionGap(courses, 3)).toEqual({
      kind: "no-suggested-term",
    });
    expect(describeYearSuggestionGap(courses, 1)).toEqual({
      kind: "no-suggested-term",
    });
  });

  it("大一本来就没有更早的学年，这是定义如此", () => {
    const courses = [course("A", "第一学年 第1学期")];
    expect(describeYearSuggestionGap(courses, 1)).toEqual({
      kind: "first-year",
    });
  });

  it("有建议学期但这个年级之前没有可用基础课，单独是一种原因", () => {
    const courses = [course("A", "第三学年 第7学期")];
    expect(describeYearSuggestionGap(courses, 2)).toEqual({
      kind: "nothing-before-year",
    });
  });
});
