import { describe, expect, it, vi } from "vitest";
import type { Course } from "../contracts";
import { resolveCourseQuery } from "./course-query";

function course(courseCode: string, name: string): Course {
  return {
    courseCode,
    name,
    credits: 2,
    category: "专业选修课",
    sourceRefIds: [],
  };
}

describe("resolveCourseQuery", () => {
  it("课程号格式正确时直接用，不查目录", async () => {
    const search = vi.fn();
    expect(await resolveCourseQuery("CS103", search)).toEqual({
      ok: true,
      code: "CS103",
    });
    expect(search).not.toHaveBeenCalled();
  });

  it("中文课程名唯一匹配时换成课程号，不把中文原文发出去", async () => {
    const search = vi.fn(async () => [course("CS102", "数据库")]);
    expect(await resolveCourseQuery("数据库", search)).toEqual({
      ok: true,
      code: "CS102",
    });
    expect(search).toHaveBeenCalledWith("数据库");
  });

  it("目录里没有时说明，并请学生输入课程号", async () => {
    const result = await resolveCourseQuery("不存在的课", async () => []);
    expect(result).toEqual({
      ok: false,
      message:
        "课程目录里没有找到「不存在的课」。请输入课程名或课程号，从列表中选择课程。",
      candidates: [],
    });
  });

  it("多门同名匹配时列出课程号让学生选，不猜", async () => {
    const result = await resolveCourseQuery("数据", async () => [
      course("CS102", "数据库"),
      course("CS201", "数据结构"),
    ]);
    expect(result).toEqual({
      ok: false,
      message:
        "「数据」对应 2 门课，请从下面选择：CS102 数据库、CS201 数据结构",
      candidates: [course("CS102", "数据库"), course("CS201", "数据结构")],
    });
  });

  it("没有可查的目录时请学生输入课程名或课程号", async () => {
    const result = await resolveCourseQuery("数据库", null);
    expect(result).toEqual({
      ok: false,
      message: "请输入课程名或课程号，从列表中选择课程。",
      candidates: [],
    });
  });

  it("多门匹配时把候选课程原样交给页面点选", async () => {
    const result = await resolveCourseQuery("数据", async () => [
      course("CS102", "数据库"),
      course("CS201", "数据结构"),
    ]);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.candidates.map((c) => c.courseCode)).toEqual([
        "CS102",
        "CS201",
      ]);
    }
  });

  it("忽略不合格式的课程号，不会把它们当作候选", async () => {
    const result = await resolveCourseQuery("数据库", async () => [
      course("_bad", "数据库"),
      course("CS102", "数据库"),
    ]);
    expect(result).toEqual({ ok: true, code: "CS102" });
  });
});
