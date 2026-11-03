import type { ReviewNote } from "../contracts";

export type ReviewDimension = ReviewNote["dimensions"][number];

export interface ReviewDimensionSummary {
  dimension: ReviewDimension;
  count: number;
  syntheticCount: number;
  notes: ReviewNote[];
}

const DIMENSION_ORDER: readonly ReviewDimension[] = [
  "GRADING",
  "ATTENDANCE",
  "WORKLOAD",
  "EXAM",
  "GROUP_WORK",
  "PRESENTATION",
  "TEACHING",
  "OVERALL",
];

/** Group the finite review records by course dimension without deriving a score. */
export function summarizeReviewsByDimension(
  notes: readonly ReviewNote[],
  courseCode: string,
): ReviewDimensionSummary[] {
  const courseNotes = notes.filter((note) => note.courseCode === courseCode);
  return DIMENSION_ORDER.flatMap((dimension) => {
    const matching = courseNotes.filter((note) =>
      note.dimensions.includes(dimension),
    );
    if (matching.length === 0) return [];
    return [
      {
        dimension,
        count: matching.length,
        syntheticCount: matching.filter(
          (note) => note.sourceKind === "SYNTHETIC",
        ).length,
        notes: matching,
      },
    ];
  });
}

/**
 * 课程级评价中未绑定老师的部分（teacherKey 为空）。
 * 绑定到具体老师的评价不在这里出现，只在该老师名下列出。
 */
export function unboundReviewNotes(
  notes: readonly ReviewNote[],
  courseCode: string,
): ReviewNote[] {
  return notes.filter(
    (note) => note.courseCode === courseCode && note.teacherKey === null,
  );
}

/**
 * 某位老师名下的评价：课程号与 teacherKey 必须完全一致。
 * 未绑定老师的评价不归到任何老师名下，避免把「课程整体」说成「这位老师」。
 */
export function teacherReviewNotes(
  notes: readonly ReviewNote[],
  courseCode: string,
  teacherKey: string,
): ReviewNote[] {
  return notes.filter(
    (note) => note.courseCode === courseCode && note.teacherKey === teacherKey,
  );
}
