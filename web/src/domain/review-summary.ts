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
