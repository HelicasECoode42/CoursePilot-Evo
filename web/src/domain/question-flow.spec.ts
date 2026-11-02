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
  "interest",
  "teacher",
  "schedule",
  "priorities",
  "ready",
];

describe("guided question flow", () => {
  it("shows every student the same fixed questions in order", () => {
    expect(questionSequence({ curricula: [curriculum], mode: "REAL" })).toEqual(
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
      mode: "REAL" as const,
    };

    expect(firstIncompleteQuestion(context)).toBe("preferences");
    draft.classPreferencesReviewed = true;
    expect(firstIncompleteQuestion(context)).toBe("interest");
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
    expect(
      questionSequence({ curricula: [curriculum], mode: "REAL" }),
    ).not.toContain("curriculum");
    expect(
      firstIncompleteQuestion({
        draft: emptyPlanningDraft(),
        curricula: [curriculum, second],
        selectedCurriculumId: null,
        mode: "REAL" as const,
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
      mode: "REAL" as const,
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
      mode: "REAL" as const,
    };

    expect(resolveQuestion("schedule", context)).toBe("preferences");
    draft.classPreferencesReviewed = true;
    expect(resolveQuestion("schedule", context)).toBe("interest");
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

describe("培养方案选择步骤", () => {
  const unverified: SnapshotSummary = {
    ...curriculum,
    snapshotId: "curriculum-browser-2025",
    sourceKind: "BROWSER_SNAPSHOT",
    sourceValidation: "UNVERIFIED",
  };

  it("恰好一个可用方案时不必多问", () => {
    expect(
      questionSequence({ curricula: [curriculum], mode: "REAL" }),
    ).not.toContain("curriculum");
  });

  it("只列出一个但它不可用时，仍要让人看见方案列表", () => {
    // 这是真实踩到的死胡同：REAL 模式下过滤后只剩一个 UNVERIFIED 快照，原来
    // 「超过一个才问」的规则让它既不被展示也不能选，用户走完 8 步才被拦下。
    expect(
      questionSequence({ curricula: [unverified], mode: "REAL" }),
    ).toContain("curriculum");
  });

  it("多个可用方案时要问", () => {
    expect(
      questionSequence({
        curricula: [curriculum, { ...curriculum, snapshotId: "another" }],
        mode: "REAL",
      }),
    ).toContain("curriculum");
  });

  it("一个方案都没有时不问这一步", () => {
    expect(questionSequence({ curricula: [], mode: "REAL" })).not.toContain(
      "curriculum",
    );
  });

  it("未核验方案不能当成已选，流程停在这一步", () => {
    const draft = emptyPlanningDraft();
    expect(
      firstIncompleteQuestion({
        draft,
        curricula: [unverified],
        selectedCurriculumId: null,
        mode: "REAL",
      }),
    ).toBe("curriculum");
  });
});
