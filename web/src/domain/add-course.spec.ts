import { describe, expect, it } from "vitest";
import { addCourseMessage } from "./add-course";

describe("add-course error messages", () => {
  it("turns the known 422 codes into plain Chinese", () => {
    expect(addCourseMessage("COURSE_ALREADY_IN_PLAN")).toBe(
      "这门课已在方案里。",
    );
    expect(addCourseMessage("COURSE_ALREADY_TAKEN")).toBe(
      "你已修过或正在修这门课，不能再加入方案。",
    );
    expect(addCourseMessage("PLAN_FULL")).toContain("方案已满");
    expect(addCourseMessage("OFFERING_SNAPSHOT_MISSING")).toContain("开课资料");
  });

  it("returns null for unknown or missing codes so the caller can fall back", () => {
    expect(addCourseMessage("SOMETHING_NEW")).toBeNull();
    expect(addCourseMessage(null)).toBeNull();
  });
});
