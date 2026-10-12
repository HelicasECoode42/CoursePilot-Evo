import type { Motive, SnapshotSummary } from "../contracts";
import type { ClassPreferenceId } from "./class-preferences";

export type QuestionId =
  | "curriculum"
  | "goals"
  | "preferences"
  | "interest"
  | "career"
  | "teacher"
  | "schedule"
  | "priorities"
  | "ready";

export interface PlanningDraft {
  motives: Motive[];
  classPreferences: ClassPreferenceId[];
  classPreferencesReviewed: boolean;
  interestTags: string[];
  interestReviewed: boolean;
  careerText: string;
  careerReviewed: boolean;
  teacherHandoffAccepted: boolean;
  mustSlots: string[];
  mustReviewed: boolean;
  preferSlots: string[];
  preferReviewed: boolean;
  priorityOrder: Motive[];
  prioritiesConfirmed: boolean;
}

export const emptyPlanningDraft = (): PlanningDraft => ({
  motives: [],
  classPreferences: [],
  classPreferencesReviewed: false,
  interestTags: [],
  interestReviewed: false,
  careerText: "",
  careerReviewed: false,
  teacherHandoffAccepted: false,
  mustSlots: [],
  mustReviewed: false,
  preferSlots: [],
  preferReviewed: false,
  priorityOrder: [],
  prioritiesConfirmed: false,
});

export interface QuestionContext {
  draft: PlanningDraft;
  curricula: SnapshotSummary[];
  selectedCurriculumId: string | null;
}

export function questionSequence({
  curricula,
}: Pick<QuestionContext, "curricula">): QuestionId[] {
  const sequence: QuestionId[] = [];
  if (
    curricula.filter(
      (item) => item.kind === "CURRICULUM" && item.state === "PUBLISHED",
    ).length > 1
  ) {
    sequence.push("curriculum");
  }
  sequence.push(
    "goals",
    "preferences",
    "career",
    "interest",
    "teacher",
    "schedule",
    "priorities",
    "ready",
  );
  return sequence;
}

export function firstIncompleteQuestion(context: QuestionContext): QuestionId {
  const sequence = questionSequence(context);
  if (sequence.includes("curriculum") && !context.selectedCurriculumId)
    return "curriculum";
  if (context.draft.motives.length === 0) return "goals";
  if (!context.draft.classPreferencesReviewed) return "preferences";
  if (!context.draft.careerReviewed) return "career";
  if (!context.draft.interestReviewed) return "interest";
  if (!context.draft.teacherHandoffAccepted) return "teacher";
  if (!context.draft.mustReviewed || !context.draft.preferReviewed)
    return "schedule";
  const expected = [...context.draft.motives].sort();
  const actual = [...context.draft.priorityOrder].sort();
  if (
    !context.draft.prioritiesConfirmed ||
    expected.length !== actual.length ||
    expected.some((motive, index) => motive !== actual[index])
  ) {
    return "priorities";
  }
  return "ready";
}

export function resolveQuestion(
  requested: string,
  context: QuestionContext,
): QuestionId {
  const sequence = questionSequence(context);
  const current = firstIncompleteQuestion(context);
  const targetIndex = sequence.indexOf(requested as QuestionId);
  const requiredIndex = sequence.indexOf(current);
  if (targetIndex < 0 || targetIndex > requiredIndex) return current;
  return requested as QuestionId;
}

export function adjacentQuestion(
  current: QuestionId,
  context: QuestionContext,
  direction: -1 | 1,
): QuestionId {
  const sequence = questionSequence(context);
  const index = sequence.indexOf(current);
  return (
    sequence[Math.min(sequence.length - 1, Math.max(0, index + direction))] ??
    "goals"
  );
}
