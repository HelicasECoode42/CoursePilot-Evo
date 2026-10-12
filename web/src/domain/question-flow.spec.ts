import { describe, expect, it } from "vitest";
import type { SnapshotSummary } from "../contracts";
import {
  emptyPlanningDraft,
  firstIncompleteQuestion,
  questionSequence,
  resolveQuestion,
} from "./question-flow";

const curriculum: SnapshotSummary = {
  snapshotId: "curriculum-computer-science-2026",
  kind: "CURRICULUM",
  state: "PUBLISHED",
  sourceKind: "CURRICULUM_FILE",
  termId: null,
  createdAt: "2026-10-01T00:00:00Z",
  sourceValidation: "VERIFIED",
};

const fixedSequence = [
  "goals",
  "preferences",
  "career",
  "interest",
  "teacher",
  "schedule",
  "priorities",
  "ready",
];

describe("guided question flow", () => {
  it("shows every student the same fixed questions in order", () => {
    expect(questionSequence({ curricula: [curriculum] })).toEqual(
      fixedSequence,
    );
  });

  it("gates each question on its own review state, not on the selected goals", () => {
    const draft = emptyPlanningDraft();
    draft.motives = ["LOW_WORKLOAD"];
    draft.priorityOrder = [...draft.motives];
    const context = {
      draft,
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
    };

    expect(firstIncompleteQuestion(context)).toBe("preferences");
    draft.classPreferencesReviewed = true;
    expect(firstIncompleteQuestion(context)).toBe("career");
    draft.careerReviewed = true;
    expect(firstIncompleteQuestion(context)).toBe("interest");
    draft.interestReviewed = true;
    expect(firstIncompleteQuestion(context)).toBe("teacher");
    draft.teacherHandoffAccepted = true;
    expect(firstIncompleteQuestion(context)).toBe("schedule");
    draft.mustReviewed = true;
    expect(firstIncompleteQuestion(context)).toBe("schedule");
    draft.preferReviewed = true;
    expect(firstIncompleteQuestion(context)).toBe("priorities");
    draft.prioritiesConfirmed = true;
    expect(firstIncompleteQuestion(context)).toBe("ready");
  });

  it("requires a curriculum choice only when several published options exist", () => {
    const second = { ...curriculum, snapshotId: "curriculum-math-2026" };
    expect(questionSequence({ curricula: [curriculum] })).not.toContain(
      "curriculum",
    );
    expect(
      firstIncompleteQuestion({
        draft: emptyPlanningDraft(),
        curricula: [curriculum, second],
        selectedCurriculumId: null,
      }),
    ).toBe("curriculum");
  });

  it("redirects arbitrary URLs and skipped prerequisites to the first unanswered question", () => {
    const draft = emptyPlanningDraft();
    draft.motives = ["CAREER"];
    draft.priorityOrder = ["CAREER"];
    const context = {
      draft,
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
    };
    expect(resolveQuestion("ready", context)).toBe("preferences");
    expect(resolveQuestion("career", context)).toBe("preferences");
    expect(resolveQuestion("not-a-question", context)).toBe("preferences");
    expect(resolveQuestion("goals", context)).toBe("goals");
  });

  it("does not let a URL skip any question, including preference review and the shared time page", () => {
    const draft = emptyPlanningDraft();
    draft.motives = ["GPA", "SCHEDULE"];
    draft.priorityOrder = [...draft.motives];
    const context = {
      draft,
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
    };

    expect(resolveQuestion("schedule", context)).toBe("preferences");
    draft.classPreferencesReviewed = true;
    expect(resolveQuestion("schedule", context)).toBe("career");
    draft.careerReviewed = true;
    expect(resolveQuestion("schedule", context)).toBe("interest");
    draft.interestReviewed = true;
    draft.teacherHandoffAccepted = true;
    expect(resolveQuestion("schedule", context)).toBe("schedule");
    draft.mustReviewed = true;
    draft.preferReviewed = true;
    expect(resolveQuestion("ready", context)).toBe("priorities");
    draft.prioritiesConfirmed = true;
    expect(resolveQuestion("ready", context)).toBe("ready");
  });
});
