import { describe, expect, it } from "vitest";
import { availabilityLabel, sortByAvailability } from "./offering-availability";

describe("本学期开课判断", () => {
  it("says not offered for a confirmed zero section count", () => {
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
