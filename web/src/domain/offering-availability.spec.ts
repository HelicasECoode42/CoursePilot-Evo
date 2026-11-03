import { describe, expect, it } from "vitest";
import type { CourseOffering } from "../contracts";
import {
  availabilityFromOfferings,
  availabilityLabel,
  sortByAvailability,
} from "./offering-availability";

// 形状与 GET /api/v1/offerings 的 items 一致，课程号与班次号均为虚构。
function offering(courseCode: string, classId: string): CourseOffering {
  return {
    courseCode,
    classId,
    teacherKey: null,
    teacherText: "示例教师",
    credits: 2,
    capacity: null,
    meetingTextRaw: "示例时间",
    meetings: [],
    parseStatus: "UNPARSED",
    sourceRefId: "fixture:offering:1",
  };
}

describe("本学期开课判断", () => {
  it("counts distinct classes for the course and ignores other courses", () => {
    const items = [
      offering("SYN1", "SYN1-01"),
      offering("SYN1", "SYN1-02"),
      offering("SYN1", "SYN1-02"),
      offering("SYN2", "SYN2-01"),
    ];
    expect(availabilityFromOfferings(items, "SYN1")).toEqual({
      state: "OFFERED",
      sections: 2,
    });
  });

  it("says not offered only when the status was OK and no class matched", () => {
    expect(availabilityFromOfferings([], "SYN9")).toEqual({
      state: "NOT_OFFERED",
    });
    expect(availabilityLabel({ state: "NOT_OFFERED" })).toBe("本学期未开");
  });

  it("sorts offered first, unknown in the middle, not offered last, keeping order inside a group", () => {
    const courses = [
      { courseCode: "A" },
      { courseCode: "B" },
      { courseCode: "C" },
      { courseCode: "D" },
      { courseCode: "E" },
    ];
    const lookup: Record<string, Parameters<typeof availabilityLabel>[0]> = {
      A: { state: "NOT_OFFERED" },
      B: { state: "OFFERED", sections: 1 },
      C: { state: "UNKNOWN", reason: "班次资料读取失败" },
      D: { state: "OFFERED", sections: 3 },
    };
    expect(
      sortByAvailability(courses, (code) => lookup[code]).map(
        (c) => c.courseCode,
      ),
    ).toEqual(["B", "D", "C", "E", "A"]);
  });
});
