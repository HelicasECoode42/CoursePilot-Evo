import { describe, expect, it } from "vitest";
import { courseSourceLabel } from "./course-source";

describe("course source labels", () => {
  it("labels curriculum references as course facts", () => {
    expect(courseSourceLabel("curriculum:plan-2026")).toBe("培养方案资料");
    expect(courseSourceLabel("src:8fd3")).toBe("培养方案资料");
  });

  it("keeps unknown references generic and synthetic references explicit", () => {
    expect(courseSourceLabel("source:fake-w2")).toBe("课程来源资料");
    expect(courseSourceLabel("synthetic:plan-1")).toBe("合成培养方案资料");
  });
});
