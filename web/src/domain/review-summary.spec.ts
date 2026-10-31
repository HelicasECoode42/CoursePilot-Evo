import { describe, expect, it } from "vitest";
import type { ReviewNote } from "../contracts";
import { summarizeReviewsByDimension } from "./review-summary";

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
