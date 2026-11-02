import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";
import domainSchema from "../../../contracts/schemas/domain.schema.json";
import { emptyPlanningDraft, type PlanningDraft } from "./question-flow";
import {
  buildPlanningRequest,
  isCurriculumUsableForMode,
} from "./planning-request";
import { dayKeys, sectionKeys } from "./schedule-grid";

const validator = new Ajv2020({ allErrors: true, strict: false });
addFormats(validator);
validator.addSchema(domainSchema, "independent-coursepilot-contract");
const validatePlanningRequest = validator.getSchema(
  "independent-coursepilot-contract#/$defs/PlanningRequest",
);

const verifiedContext = {
  curriculumSnapshotId: "curriculum-computer-science-2026",
  curriculumSourceKind: "CURRICULUM_FILE" as const,
  curriculumSourceValidation: "VERIFIED" as const,
  academicRecordId: "record-from-fixture",
  offeringSnapshotId: null,
  mode: "REAL" as const,
};

/** A draft that passes every gate except the fields a test sets. */
function readyDraft(overrides: Partial<PlanningDraft> = {}): PlanningDraft {
  return {
    ...emptyPlanningDraft(),
    motives: ["GPA"],
    priorityOrder: ["GPA"],
    prioritiesConfirmed: true,
    classPreferencesReviewed: true,
    mustReviewed: true,
    preferReviewed: true,
    ...overrides,
  };
}

/** Cells that never form a whole day or a whole section (each day spans 5 sections). */
function scatteredKeys(count: number): string[] {
  const keys: string[] = [];
  for (let day = 1; day <= 7; day += 1) {
    for (let section = day; section <= day + 4; section += 1) {
      keys.push(`${day}-${section}`);
    }
  }
  return keys.slice(0, count);
}

describe("PlanningRequest handoff", () => {
  it("maps hard and soft time independently, includes class preferences, and carries every filled field", () => {
    const draft = readyDraft({
      motives: ["LOW_WORKLOAD", "SCHEDULE"],
      priorityOrder: ["SCHEDULE", "LOW_WORKLOAD"],
      mustSlots: [...dayKeys(2), ...dayKeys(5), "1-1"],
      preferSlots: sectionKeys(6),
      classPreferences: ["LOWER_HOMEWORK"],
      careerText: "data science",
      interestTags: ["robotics"],
    });

    const result = buildPlanningRequest(draft, {
      ...verifiedContext,
      curriculumSourceKind: "SYNTHETIC",
      curriculumSourceValidation: "SYNTHETIC",
      academicRecordId: "record-from-fixture",
      mode: "SIMULATION",
    });

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(validatePlanningRequest?.(result.request)).toBe(true);
    expect(result.request.intent.motives).toEqual(["LOW_WORKLOAD", "SCHEDULE"]);
    expect(result.request.intent.priorityOrder).toEqual([
      "SCHEDULE",
      "LOW_WORKLOAD",
    ]);
    expect(result.request.intent.hardConstraints).toEqual([
      {
        kind: "BLOCK_DAY",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: 2,
        section: null,
        value: null,
        sourceText: "必须避开周二整天",
      },
      {
        kind: "BLOCK_DAY",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: 5,
        section: null,
        value: null,
        sourceText: "必须避开周五整天",
      },
      {
        kind: "BLOCK_SLOT",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: 1,
        section: 1,
        value: null,
        sourceText: "必须避开周一第1节",
      },
    ]);
    expect(result.request.intent.softPreferences).toEqual([
      {
        dimension: "schedule.blocked_section",
        value: "6",
        sourceText: "尽量避开每天第6节",
      },
      {
        dimension: "workload.homework",
        value: "lower_homework",
        sourceText: "希望参考作业投入较少的课程",
      },
    ]);
    expect(result.request.intent.interestTags).toEqual(["robotics"]);
    expect(result.request.promptText).toBe("职业方向补充：data science");
    expect(result.request.intent.pinnedTeacherCoursePairs).toEqual([]);
    expect(result.request.offeringSnapshotId).toBeNull();
    expect(result.request.previousPlanId).toBeNull();
  });

  it("keeps filled answers whose goal is not selected instead of filtering them by motive", () => {
    const draft = readyDraft({
      classPreferences: ["LOWER_HOMEWORK"],
      mustSlots: dayKeys(2),
      preferSlots: sectionKeys(6),
      careerText: "data science",
      interestTags: ["robotics"],
    });

    const result = buildPlanningRequest(draft, verifiedContext);

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(validatePlanningRequest?.(result.request)).toBe(true);
    expect(result.request.intent.motives).toEqual(["GPA"]);
    expect(result.request.intent.hardConstraints).toEqual([
      {
        kind: "BLOCK_DAY",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: 2,
        section: null,
        value: null,
        sourceText: "必须避开周二整天",
      },
    ]);
    expect(result.request.intent.softPreferences).toEqual([
      {
        dimension: "schedule.blocked_section",
        value: "6",
        sourceText: "尽量避开每天第6节",
      },
      {
        dimension: "workload.homework",
        value: "lower_homework",
        sourceText: "希望参考作业投入较少的课程",
      },
    ]);
    expect(result.request.intent.interestTags).toEqual(["robotics"]);
    expect(result.request.promptText).toBe("职业方向补充：data science");
  });

  it("represents time preferences as soft preferences instead of hard constraints", () => {
    const draft = readyDraft({
      motives: ["SCHEDULE"],
      priorityOrder: ["SCHEDULE"],
      preferSlots: dayKeys(3),
    });

    const result = buildPlanningRequest(draft, verifiedContext);

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.hardConstraints).toEqual([]);
    expect(result.request.intent.softPreferences).toEqual([
      {
        dimension: "schedule.blocked_day",
        value: "3",
        sourceText: "尽量避开周三整天",
      },
    ]);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it("maps a whole weekday to BLOCK_DAY with section null", () => {
    const result = buildPlanningRequest(
      readyDraft({ mustSlots: dayKeys(4) }),
      verifiedContext,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.hardConstraints).toEqual([
      {
        kind: "BLOCK_DAY",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: 4,
        section: null,
        value: null,
        sourceText: "必须避开周四整天",
      },
    ]);
  });

  it("maps a whole section row to BLOCK_SECTION with dayOfWeek null", () => {
    const result = buildPlanningRequest(
      readyDraft({ mustSlots: sectionKeys(2) }),
      verifiedContext,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.hardConstraints).toEqual([
      {
        kind: "BLOCK_SECTION",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: null,
        section: 2,
        value: null,
        sourceText: "必须避开每天第2节",
      },
    ]);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it('maps scattered cells to BLOCK_SLOT and blocked_slot values in "星期-节次" form', () => {
    const result = buildPlanningRequest(
      readyDraft({
        mustSlots: ["3-2"],
        preferSlots: ["7-12"],
      }),
      verifiedContext,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.hardConstraints).toEqual([
      {
        kind: "BLOCK_SLOT",
        courseCode: null,
        teacherKey: null,
        dayOfWeek: 3,
        section: 2,
        value: null,
        sourceText: "必须避开周三第2节",
      },
    ]);
    expect(result.request.intent.softPreferences).toEqual([
      {
        dimension: "schedule.blocked_slot",
        value: "7-12",
        sourceText: "尽量避开周日第12节",
      },
    ]);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it("selecting all 84 cells yields only whole-day constraints, never BLOCK_SECTION too", () => {
    const allCells: string[] = [];
    for (let day = 1; day <= 7; day += 1) allCells.push(...dayKeys(day));
    const result = buildPlanningRequest(
      readyDraft({ mustSlots: allCells }),
      verifiedContext,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const kinds = result.request.intent.hardConstraints.map(
      (item) => item.kind,
    );
    expect(kinds).toHaveLength(7);
    expect(kinds.every((kind) => kind === "BLOCK_DAY")).toBe(true);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it("returns an actionable failure instead of truncating when hard constraints exceed 30", () => {
    const result = buildPlanningRequest(
      readyDraft({ mustSlots: scatteredKeys(35) }),
      verifiedContext,
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.missing).toEqual(["时间安排"]);
    expect(result.hints).toHaveLength(1);
    expect(result.hints?.[0]).toContain("归一后 35 条");
    expect(result.hints?.[0]).toContain("上限 30");
    expect(result.hints?.[0]).toContain("改用整行或整列");
  });

  it("counts class preferences against the same 30-item soft-preference cap", () => {
    const result = buildPlanningRequest(
      readyDraft({
        preferSlots: scatteredKeys(26),
        classPreferences: [
          "GRADING_FEEDBACK",
          "LOWER_ATTENDANCE",
          "LOWER_HOMEWORK",
          "FEWER_GROUP_TASKS",
          "FEWER_PRESENTATIONS",
          "AVOID_CLOSED_BOOK_EXAMS",
        ],
      }),
      verifiedContext,
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.hints?.[0]).toContain("共 32 条");
  });

  it("accepts exactly 30 soft preferences", () => {
    const result = buildPlanningRequest(
      readyDraft({
        preferSlots: scatteredKeys(24),
        classPreferences: [
          "GRADING_FEEDBACK",
          "LOWER_ATTENDANCE",
          "LOWER_HOMEWORK",
          "FEWER_GROUP_TASKS",
          "FEWER_PRESENTATIONS",
          "AVOID_CLOSED_BOOK_EXAMS",
        ],
      }),
      verifiedContext,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.softPreferences).toHaveLength(30);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it("requires the class-preference and schedule reviews whatever the goals are", () => {
    const draft = readyDraft({
      motives: ["INTEREST"],
      priorityOrder: ["INTEREST"],
      classPreferencesReviewed: false,
      mustReviewed: false,
      preferReviewed: false,
    });
    expect(buildPlanningRequest(draft, verifiedContext)).toEqual({
      ok: false,
      missing: ["上课与考核偏好", "时间安排"],
    });
  });

  it("allows an empty schedule and class-preference page once reviewed", () => {
    const result = buildPlanningRequest(
      readyDraft({
        motives: ["GPA", "SCHEDULE"],
        priorityOrder: ["GPA", "SCHEDULE"],
      }),
      verifiedContext,
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.hardConstraints).toEqual([]);
    expect(result.request.intent.softPreferences).toEqual([]);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it("maps all six course and assessment choices to schema-valid soft preferences", () => {
    const draft = readyDraft({
      classPreferences: [
        "GRADING_FEEDBACK",
        "LOWER_ATTENDANCE",
        "LOWER_HOMEWORK",
        "FEWER_GROUP_TASKS",
        "FEWER_PRESENTATIONS",
        "AVOID_CLOSED_BOOK_EXAMS",
      ],
    });

    const result = buildPlanningRequest(draft, {
      curriculumSnapshotId: "fixture-curriculum",
      curriculumSourceKind: "SYNTHETIC",
      curriculumSourceValidation: "SYNTHETIC",
      academicRecordId: "fixture-record",
      offeringSnapshotId: null,
      mode: "SIMULATION",
    });

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.intent.softPreferences).toEqual([
      {
        dimension: "assessment.grading_feedback",
        value: "prefer_friendly",
        sourceText: "希望参考给分反馈较友好的课程，不代表保证高分",
      },
      {
        dimension: "workload.attendance",
        value: "lower_attendance",
        sourceText: "希望参考签到要求较少的课程",
      },
      {
        dimension: "workload.homework",
        value: "lower_homework",
        sourceText: "希望参考作业投入较少的课程",
      },
      {
        dimension: "assessment.group_tasks",
        value: "fewer_group_tasks",
        sourceText: "希望参考小组任务较少的课程",
      },
      {
        dimension: "assessment.presentations",
        value: "fewer_presentations",
        sourceText: "希望参考汇报和展示较少的课程",
      },
      {
        dimension: "assessment.closed_book_exam",
        value: "avoid_closed_book",
        sourceText: "希望尽量避开闭卷考试",
      },
    ]);
    expect(validatePlanningRequest?.(result.request)).toBe(true);
  });

  it("never invents academic record or curriculum identifiers", () => {
    const result = buildPlanningRequest(readyDraft(), {
      curriculumSnapshotId: null,
      curriculumSourceKind: null,
      curriculumSourceValidation: null,
      academicRecordId: null,
      offeringSnapshotId: null,
      mode: "REAL",
    });

    expect(result).toEqual({ ok: false, missing: ["培养方案", "学业记录"] });
  });

  it("requires a complete, explicitly confirmed priority order", () => {
    const draft = readyDraft({
      motives: ["GPA", "LOW_WORKLOAD"],
      priorityOrder: ["GPA"],
    });

    const result = buildPlanningRequest(draft, {
      ...verifiedContext,
      mode: "SIMULATION",
    });

    expect(result).toEqual({ ok: false, missing: ["已确认目标优先级"] });
  });

  it("does not treat the initial motive order as a confirmed priority", () => {
    const draft = readyDraft({
      motives: ["GPA", "LOW_WORKLOAD"],
      priorityOrder: ["GPA", "LOW_WORKLOAD"],
      prioritiesConfirmed: false,
    });

    const result = buildPlanningRequest(draft, {
      ...verifiedContext,
      mode: "SIMULATION",
    });

    expect(result).toEqual({ ok: false, missing: ["已确认目标优先级"] });
  });

  it("refuses synthetic curricula in REAL mode even when a record ID exists", () => {
    const result = buildPlanningRequest(readyDraft(), {
      ...verifiedContext,
      curriculumSnapshotId: "fixture-curriculum-computer-science",
      curriculumSourceValidation: "SYNTHETIC",
    });

    expect(result).toEqual({ ok: false, missing: ["真实培养方案"] });
  });

  it("allows an imported curriculum file to provide course suggestions while keeping its unverified source", () => {
    const result = buildPlanningRequest(readyDraft(), {
      ...verifiedContext,
      curriculumSnapshotId: "curriculum-unverified",
      curriculumSourceValidation: "UNVERIFIED",
      academicRecordId: "record-123",
    });

    expect(result.ok).toBe(true);
  });

  it("rejects a synthetic source kind even when the source is labelled verified", () => {
    const result = buildPlanningRequest(readyDraft(), {
      ...verifiedContext,
      curriculumSnapshotId: "mislabelled-synthetic-curriculum",
      curriculumSourceKind: "SYNTHETIC",
      academicRecordId: "record-123",
    });

    expect(result).toEqual({ ok: false, missing: ["真实培养方案"] });
  });
});

describe("课程与教师的选择", () => {
  it("将优先考虑课程提交为软偏好，不生成必选约束", () => {
    const built = buildPlanningRequest(
      readyDraft({ preferredCourseCodes: ["CS102"] }),
      verifiedContext,
    );
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.request.intent.softPreferences).toContainEqual({
      dimension: "course.prefer",
      value: "CS102",
      sourceText: "学生优先考虑的课程",
    });
    expect(built.request.intent.hardConstraints).toEqual([]);
    expect(validatePlanningRequest?.(built.request)).toBe(true);
  });

  it("将学生加入规划的课程作为必选约束提交", () => {
    const built = buildPlanningRequest(
      readyDraft({ selectedCourseCodes: ["CS102", "CS103"] }),
      verifiedContext,
    );
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(
      built.request.intent.hardConstraints
        .filter((item) => item.kind === "PIN_COURSE")
        .map((item) => item.courseCode),
    ).toEqual(["CS102", "CS103"]);
    expect(validatePlanningRequest!(built.request)).toBe(true);
  });
  it("把比较页选的课程+教师交给 pinnedTeacherCoursePairs", () => {
    // 契约的 GoalIntent 早就留好了这个字段（元素是 TeacherPreference）。
    // 之前这里恒为空数组，学生在比较页标的「必须保留」永远到不了后端。
    const draft = readyDraft({
      teacherPicks: [
        { courseCode: "CS103", teacherKey: "teacher-zhang-02", mode: "MUST" },
        { courseCode: "CS102", teacherKey: "teacher-li-01", mode: "PREFER" },
      ],
    });

    const built = buildPlanningRequest(draft, verifiedContext);
    expect(built.ok).toBe(true);
    if (!built.ok) return;

    expect(built.request.intent.pinnedTeacherCoursePairs).toEqual([
      { courseCode: "CS103", teacherKey: "teacher-zhang-02", mode: "MUST" },
      { courseCode: "CS102", teacherKey: "teacher-li-01", mode: "PREFER" },
    ]);
    expect(validatePlanningRequest!(built.request)).toBe(true);
  });

  it("没选教师时是空数组，不是缺字段", () => {
    const built = buildPlanningRequest(readyDraft(), verifiedContext);
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.request.intent.pinnedTeacherCoursePairs).toEqual([]);
    expect(validatePlanningRequest!(built.request)).toBe(true);
  });

  it("超过契约的 20 条上限时给可操作提示，不截断", () => {
    // 截断会把学生明确标过的教师悄悄丢掉，和「不静默删除必须项」冲突。
    const draft = readyDraft({
      teacherPicks: Array.from({ length: 21 }, (_, index) => ({
        courseCode: `CS${100 + index}`,
        teacherKey: `teacher-${index}`,
        mode: "MUST" as const,
      })),
    });

    const built = buildPlanningRequest(draft, verifiedContext);
    expect(built.ok).toBe(false);
    if (built.ok) return;
    expect(built.hints?.join("")).toContain("课程与教师太多");
  });
});

describe("isCurriculumUsableForMode", () => {
  // 自动选择与提交请求共用来源规则。
  const cases = [
    { sourceKind: "CURRICULUM_FILE", sourceValidation: "VERIFIED", real: true },
    {
      sourceKind: "CURRICULUM_FILE",
      sourceValidation: "UNVERIFIED",
      real: true,
    },
    {
      sourceKind: "BROWSER_SNAPSHOT",
      sourceValidation: "UNVERIFIED",
      real: false,
    },
    { sourceKind: "SYNTHETIC", sourceValidation: "SYNTHETIC", real: false },
  ] as const;

  it.each(cases)(
    "REAL 模式下 $sourceKind/$sourceValidation 可用性为 $real",
    ({ sourceKind, sourceValidation, real }) => {
      expect(
        isCurriculumUsableForMode({ sourceKind, sourceValidation }, "REAL"),
      ).toBe(real);
    },
  );

  it("REAL 模式的判断必须和提交前的缺项判断一致", () => {
    for (const { sourceKind, sourceValidation } of cases) {
      const build = buildPlanningRequest(readyDraft(), {
        ...verifiedContext,
        curriculumSourceKind: sourceKind,
        curriculumSourceValidation: sourceValidation,
      });
      const blockedByCurriculum =
        !build.ok &&
        build.missing.some((item) =>
          ["培养方案", "真实培养方案", "已核验培养方案"].includes(item),
        );
      expect(
        isCurriculumUsableForMode({ sourceKind, sourceValidation }, "REAL"),
      ).toBe(!blockedByCurriculum);
    }
  });

  it("a pending curriculum file cannot qualify an offering snapshot for real timetable checks", () => {
    expect(
      isCurriculumUsableForMode(
        {
          kind: "OFFERING",
          sourceKind: "CURRICULUM_FILE",
          sourceValidation: "UNVERIFIED",
        },
        "REAL",
      ),
    ).toBe(false);
  });

  it("演示模式只接受虚构资料", () => {
    expect(
      isCurriculumUsableForMode(
        { sourceKind: "SYNTHETIC", sourceValidation: "SYNTHETIC" },
        "SIMULATION",
      ),
    ).toBe(true);
    expect(
      isCurriculumUsableForMode(
        { sourceKind: "CURRICULUM_FILE", sourceValidation: "VERIFIED" },
        "SIMULATION",
      ),
    ).toBe(false);
  });

  it("演示模式接受未核验的培养文件，但不接受未核验的开课快照", () => {
    const source = {
      sourceKind: "CURRICULUM_FILE",
      sourceValidation: "UNVERIFIED",
    } as const;
    expect(
      isCurriculumUsableForMode(
        { ...source, kind: "CURRICULUM" },
        "SIMULATION",
      ),
    ).toBe(true);
    expect(
      isCurriculumUsableForMode({ ...source, kind: "OFFERING" }, "SIMULATION"),
    ).toBe(false);
  });
});
