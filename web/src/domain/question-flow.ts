import type { Motive, PlanningMode, SnapshotSummary } from "../contracts";
import { isCurriculumUsableForMode } from "./planning-request";
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

/**
 * 一个具体的「课程 + 教师」选择。
 *
 * 和契约的 TeacherPreference 同形（domain.schema.json）。E1 只收了
 * teacherHandoffAccepted —— 那时还没有课程与教师资料，学生无法选到具体的人，
 * 所以只是「知道了，之后再挑」。真正的选择在 E3 的比较页产生，落到这里。
 */
export interface TeacherPick {
  courseCode: string;
  teacherKey: string;
  mode: "MUST" | "PREFER";
}

export interface PlanningDraft {
  motives: Motive[];
  classPreferences: ClassPreferenceId[];
  classPreferencesReviewed: boolean;
  interestTags: string[];
  interestReviewed: boolean;
  careerText: string;
  careerReviewed: boolean;
  teacherHandoffAccepted: boolean;
  teacherPicks: TeacherPick[];
  selectedCourseCodes: string[];
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
  teacherPicks: [],
  selectedCourseCodes: [],
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
  mode: PlanningMode;
}

export function questionSequence({
  curricula,
  mode,
}: Pick<QuestionContext, "curricula" | "mode">): QuestionId[] {
  const sequence: QuestionId[] = [];
  const published = curricula.filter(
    (item) => item.kind === "CURRICULUM" && item.state === "PUBLISHED",
  );
  // 按「可用数量」而不是「总数量」决定是否需要这一步，和 store 的自动选择规则对齐。
  // 恰好一个可用时自动选中，不必多问；其余情况都要让人看见有哪些方案、为什么不能用。
  // 原来只在「超过一个」时才加这一步：于是只列出一个、而它又不可用时，用户既看不到
  // 方案列表也选不了，一路走到第 8 步才被拦下。
  const usable = published.filter((item) =>
    isCurriculumUsableForMode(item, mode),
  );
  if (published.length > 0 && usable.length !== 1) {
    sequence.push("curriculum");
  }
  sequence.push(
    "goals",
    "preferences",
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
  if (!context.draft.careerReviewed || !context.draft.interestReviewed)
    return "interest";
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
  if (requested === "career") requested = "interest";
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
