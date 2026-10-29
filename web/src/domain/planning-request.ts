import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import domainSchema from "../../../contracts/schemas/domain.schema.json";
import {
  SCHEMA_VERSION,
  type Motive,
  type PlanningMode,
  type PlanningRequest,
} from "../contracts";
import { MOTIVE_LABELS } from "./goals";
import type { SnapshotSummary } from "../contracts";
import { collectClassSoftPreferences } from "./class-preferences";
import type { PlanningDraft } from "./question-flow";
import { normalizeScheduleKeys, WEEKDAY_NAMES } from "./schedule-grid";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addSchema(domainSchema, "coursepilot-domain-v1");
const validateRequest = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/PlanningRequest",
);

/** Shared per-array cap in the contract; soft class items count against it too. */
export const MAX_INTENT_ITEMS = 30;

/** 契约对 pinnedTeacherCoursePairs 的上限，和上面那条是不同的数。 */
export const MAX_TEACHER_PAIRS = 20;

export interface PlanningContext {
  curriculumSnapshotId: string | null;
  curriculumSourceKind: SnapshotSummary["sourceKind"] | null;
  curriculumSourceValidation: SnapshotSummary["sourceValidation"] | null;
  academicRecordId: string | null;
  offeringSnapshotId: string | null;
  mode: PlanningMode;
}

export type PlanningRequestBuild =
  | { ok: true; request: PlanningRequest }
  | {
      ok: false;
      missing: Array<
        | "培养方案"
        | "真实培养方案"
        | "已核验培养方案"
        | "学业记录"
        | "已确认目标优先级"
        | "上课与考核偏好"
        | "时间安排"
      >;
      /** Actionable advice, present only when the schedule exceeds the contract cap. */
      hints?: string[];
    };

type HardConstraints = PlanningRequest["intent"]["hardConstraints"];
type SoftPreferences = PlanningRequest["intent"]["softPreferences"];

function scheduleConstraints(mustSlots: readonly string[]): HardConstraints {
  const normalized = normalizeScheduleKeys(mustSlots);
  return [
    ...normalized.blockedDays.map((dayOfWeek) => ({
      kind: "BLOCK_DAY" as const,
      courseCode: null,
      teacherKey: null,
      dayOfWeek,
      section: null,
      value: null,
      sourceText: `必须避开${WEEKDAY_NAMES[dayOfWeek - 1]}整天`,
    })),
    ...normalized.blockedSections.map((section) => ({
      kind: "BLOCK_SECTION" as const,
      courseCode: null,
      teacherKey: null,
      dayOfWeek: null,
      section,
      value: null,
      sourceText: `必须避开每天第${section}节`,
    })),
    ...normalized.blockedSlots.map(({ dayOfWeek, section }) => ({
      kind: "BLOCK_SLOT" as const,
      courseCode: null,
      teacherKey: null,
      dayOfWeek,
      section,
      value: null,
      sourceText: `必须避开${WEEKDAY_NAMES[dayOfWeek - 1]}第${section}节`,
    })),
  ];
}

function schedulePreferences(preferSlots: readonly string[]): SoftPreferences {
  const normalized = normalizeScheduleKeys(preferSlots);
  return [
    ...normalized.blockedDays.map((day) => ({
      dimension: "schedule.blocked_day",
      value: String(day),
      sourceText: `尽量避开${WEEKDAY_NAMES[day - 1]}整天`,
    })),
    ...normalized.blockedSections.map((section) => ({
      dimension: "schedule.blocked_section",
      value: String(section),
      sourceText: `尽量避开每天第${section}节`,
    })),
    ...normalized.blockedSlots.map(({ dayOfWeek, section }) => ({
      dimension: "schedule.blocked_slot",
      value: `${dayOfWeek}-${section}`,
      sourceText: `尽量避开${WEEKDAY_NAMES[dayOfWeek - 1]}第${section}节`,
    })),
  ];
}

function freeText(draft: PlanningDraft): string {
  if (!draft.careerText.trim()) return "";
  return `职业方向补充：${draft.careerText.trim()}`;
}

function cleanTags(draft: PlanningDraft): string[] {
  return draft.interestTags.map((tag) => tag.trim()).filter(Boolean);
}

function isPriorityOrderConfirmed(draft: PlanningDraft): boolean {
  return (
    draft.prioritiesConfirmed &&
    draft.priorityOrder.length === draft.motives.length &&
    draft.priorityOrder.every(
      (motive, index) =>
        draft.motives.includes(motive) &&
        draft.priorityOrder.indexOf(motive) === index,
    )
  );
}

/** 培养文件可提供待核验的课程建议；实际班次仍要求来源已核验。 */
export function isCurriculumUsableForMode(
  curriculum: Pick<SnapshotSummary, "sourceKind" | "sourceValidation"> &
    Partial<Pick<SnapshotSummary, "kind">>,
  mode: PlanningMode,
): boolean {
  if (mode !== "REAL") {
    return (
      curriculum.sourceKind === "SYNTHETIC" ||
      curriculum.sourceValidation === "SYNTHETIC" ||
      (curriculum.kind === "CURRICULUM" &&
        curriculum.sourceKind === "CURRICULUM_FILE" &&
        curriculum.sourceValidation === "UNVERIFIED")
    );
  }
  if (
    curriculum.sourceKind === "SYNTHETIC" ||
    curriculum.sourceValidation === "SYNTHETIC"
  ) {
    return false;
  }
  return (
    curriculum.sourceValidation === "VERIFIED" ||
    ((curriculum.kind ?? "CURRICULUM") === "CURRICULUM" &&
      curriculum.sourceKind === "CURRICULUM_FILE" &&
      curriculum.sourceValidation === "UNVERIFIED")
  );
}

export function buildPlanningRequest(
  draft: PlanningDraft,
  context: PlanningContext,
): PlanningRequestBuild {
  const problems: Array<
    | "培养方案"
    | "真实培养方案"
    | "已核验培养方案"
    | "学业记录"
    | "已确认目标优先级"
    | "上课与考核偏好"
    | "时间安排"
  > = [];
  if (!context.curriculumSnapshotId) problems.push("培养方案");
  else if (context.mode === "REAL") {
    if (
      context.curriculumSourceKind === "SYNTHETIC" ||
      context.curriculumSourceValidation === "SYNTHETIC"
    ) {
      problems.push("真实培养方案");
    } else if (
      !isCurriculumUsableForMode(
        {
          kind: "CURRICULUM",
          sourceKind: context.curriculumSourceKind!,
          sourceValidation: context.curriculumSourceValidation!,
        },
        context.mode,
      )
    ) {
      problems.push("已核验培养方案");
    }
  }
  if (!context.academicRecordId) problems.push("学业记录");
  if (!draft.classPreferencesReviewed) problems.push("上课与考核偏好");
  if (!draft.mustReviewed || !draft.preferReviewed) problems.push("时间安排");
  if (!isPriorityOrderConfirmed(draft)) problems.push("已确认目标优先级");

  const hardConstraints: HardConstraints = [
    ...scheduleConstraints(draft.mustSlots),
    ...draft.selectedCourseCodes.map((courseCode) => ({
      kind: "PIN_COURSE" as const,
      courseCode,
      teacherKey: null,
      dayOfWeek: null,
      section: null,
      value: null,
      sourceText: "学生选入规划的课程",
    })),
  ];
  const scheduleSoft = schedulePreferences(draft.preferSlots);
  const softPreferences = [
    ...scheduleSoft,
    ...collectClassSoftPreferences(draft.classPreferences),
  ];
  // 课程+教师的选择来自 E3 的比较页。契约字段就是为这个留的，不要把它
  // 塞进 softPreferences 或自造 dimension 名。
  const teacherPairs = draft.teacherPicks.map((pick) => ({
    courseCode: pick.courseCode,
    teacherKey: pick.teacherKey,
    mode: pick.mode,
  }));

  const hints: string[] = [];
  if (teacherPairs.length > MAX_TEACHER_PAIRS) {
    hints.push(
      `选定的课程与教师太多（${teacherPairs.length} 条，上限 ${MAX_TEACHER_PAIRS}）。请减少「必须保留」或「优先考虑」的教师。`,
    );
  }
  if (hardConstraints.length > MAX_INTENT_ITEMS) {
    hints.push(
      `所选课程和必须避开的时段归一后 ${hardConstraints.length} 条，上限 ${MAX_INTENT_ITEMS}。请减少课程，或将时段改用整行或整列选择。`,
    );
  }
  if (softPreferences.length > MAX_INTENT_ITEMS) {
    hints.push(
      `尽量避开的时段太零散（归一后 ${scheduleSoft.length} 条，连同上课与考核偏好共 ${softPreferences.length} 条，上限 ${MAX_INTENT_ITEMS}）。请改用整行或整列选择，减少格子，或减少上课与考核偏好。`,
    );
  }
  // Show cap advice together with other gaps, so the student fixes both in one pass.
  if (hints.length > 0 && !problems.includes("时间安排")) {
    problems.push("时间安排");
  }
  if (problems.length > 0) {
    return hints.length > 0
      ? { ok: false, missing: problems, hints }
      : { ok: false, missing: problems };
  }

  const request: PlanningRequest = {
    schemaVersion: SCHEMA_VERSION,
    curriculumSnapshotId: context.curriculumSnapshotId!,
    offeringSnapshotId: context.offeringSnapshotId,
    academicRecordId: context.academicRecordId!,
    mode: context.mode,
    promptText: freeText(draft),
    intent: {
      motives: [...draft.motives],
      priorityOrder: [...draft.priorityOrder],
      hardConstraints,
      softPreferences,
      pinnedTeacherCoursePairs: teacherPairs,
      interestTags: cleanTags(draft),
      careerDirectionIds: [],
    },
    previousPlanId: null,
  };

  if (!validateRequest?.(request)) {
    return { ok: false, missing: ["已确认目标优先级"] };
  }
  return { ok: true, request };
}

export function priorityLabel(motive: Motive): string {
  return MOTIVE_LABELS[motive];
}
