import { describe, expect, it } from "vitest";
import type { ReviewNote } from "../contracts";
import {
  summarizeReviewsByDimension,
  teacherReviewNotes,
  unboundReviewNotes,
} from "./review-summary";

const note = (overrides: Partial<ReviewNote>): ReviewNote => ({
  reviewNoteId: "review-1",
  courseCode: "CS101",
  teacherKey: null,
  termId: null,
  sourceKind: "USER_IMPORT",
  publishedAt: null,
  sourceUrl: null,
  excerpt: "课程评价摘录",
  dimensions: ["GRADING"],
  matchStatus: "COURSE_ONLY",
  sourceRefId: "source:pdf:p2",
  ...overrides,
});

describe("review dimension summaries", () => {
  it("counts records per course and dimension and keeps source evidence", () => {
    const summaries = summarizeReviewsByDimension(
      [
        note({ reviewNoteId: "one" }),
        note({
          reviewNoteId: "two",
          sourceKind: "SYNTHETIC",
          dimensions: ["GRADING", "EXAM"],
        }),
        note({ reviewNoteId: "other-course", courseCode: "CS102" }),
      ],
      "CS101",
    );

    expect(summaries).toEqual([
      expect.objectContaining({
        dimension: "GRADING",
        count: 2,
        syntheticCount: 1,
        notes: expect.arrayContaining([
          expect.objectContaining({
            reviewNoteId: "one",
            sourceRefId: "source:pdf:p2",
          }),
        ]),
      }),
      expect.objectContaining({
        dimension: "EXAM",
        count: 1,
        syntheticCount: 1,
      }),
    ]);
    expect(summaries.some((summary) => "score" in summary)).toBe(false);
  });

  it("returns no dimensions when the course has no review records", () => {
    expect(summarizeReviewsByDimension([], "CS101")).toEqual([]);
  });
});

describe("按老师拆分评价", () => {
  const note = (
    reviewNoteId: string,
    teacherKey: string | null,
    courseCode = "SE201",
  ) =>
    ({
      reviewNoteId,
      courseCode,
      teacherKey,
      termId: null,
      sourceKind: "USER_IMPORT",
      publishedAt: null,
      sourceUrl: null,
      excerpt: "x",
      dimensions: ["WORKLOAD"],
      matchStatus: teacherKey ? "COURSE_TEACHER_MATCHED" : "COURSE_ONLY",
      sourceRefId: `source:${reviewNoteId}`,
    }) as ReviewNote;

  const notes = [
    note("a", "chen-sb"),
    note("b", "teng-zm"),
    note("c", null),
    note("d", "chen-sb", "OTHER"),
  ];

  it("老师名下只有 teacherKey 完全相同、课程相同的评价", () => {
    expect(
      teacherReviewNotes(notes, "SE201", "chen-sb").map((n) => n.reviewNoteId),
    ).toEqual(["a"]);
    expect(
      teacherReviewNotes(notes, "SE201", "teng-zm").map((n) => n.reviewNoteId),
    ).toEqual(["b"]);
  });

  it("未绑定老师的评价只出现在课程整体部分，不归到任何老师", () => {
    expect(
      unboundReviewNotes(notes, "SE201").map((n) => n.reviewNoteId),
    ).toEqual(["c"]);
    expect(teacherReviewNotes(notes, "SE201", "chen-sb")).not.toContainEqual(
      expect.objectContaining({ reviewNoteId: "c" }),
    );
  });
});
