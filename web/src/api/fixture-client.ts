import type {
  AcademicRecord,
  AcademicRecordInput,
  AcademicRecordList,
  AuditResult,
  CareerDirection,
  Constraint,
  Course,
  CourseOffering,
  PlanItem,
  PlanningAnswer,
  PlanningRequest,
  PlanValidation,
  ReviewNote,
  RunReport,
  SessionPlanReplaceInput,
  SessionPlanEditInput,
  SessionPlanEditResult,
  SessionPlanReplacement,
  SnapshotSummary,
  TeacherCourseOption,
} from "../contracts";
import type {
  SchoolProgressImportRequest,
  SchoolProgressImportResult,
} from "../domain/school-progress";
import {
  ApiFailure,
  type CoursePilotApiClient,
  type CurriculumResult,
  type OfferingSnapshotResult,
  type CourseSearch,
  type ReviewNoteSearch,
  type SessionOfferingSearch,
  type SessionView,
  type TeacherCourseOptionSearch,
} from "./client";

const DEMO_SESSION: SessionView = {
  sessionId: "fixture-session-e1",
  expiresAt: "2099-01-01T00:00:00Z",
};
const DEMO_SESSION_TOKEN = "fixture-token-0123456789abcdef0123456789abcdef";
const DEMO_RECORD_ID = "fixture-academic-record-e1";
const DEMO_CURRICULUM_ID = "fixture-curriculum-computer-science";
const DEMO_COURSES: Course[] = [
  {
    courseCode: "CS102",
    name: "程序设计基础（演示）",
    credits: null,
    category: "演示课程",
    sourceRefIds: ["source:fixture-course-cs102"],
  },
  {
    courseCode: "CS103",
    name: "数据结构与算法（演示）",
    credits: null,
    category: "演示课程",
    sourceRefIds: ["source:fixture-course-cs103"],
  },
];

const DEMO_CURRICULA: CurriculumResult = {
  items: [
    {
      snapshotId: DEMO_CURRICULUM_ID,
      kind: "CURRICULUM",
      state: "PUBLISHED",
      sourceKind: "SYNTHETIC",
      termId: null,
      createdAt: "2026-10-01T00:00:00Z",
      sourceValidation: "SYNTHETIC",
    },
  ],
  unknownMessages: [],
};

/** 虚构学业记录。三态刻意都给一份，用来演示「已满足 / 未满足 / 无法确认」必须分开。 */
const DEMO_RECORD: AcademicRecord = {
  academicRecordId: DEMO_RECORD_ID,
  revision: 1,
  curriculumSnapshotId: DEMO_CURRICULUM_ID,
  completedCourses: [
    {
      courseCode: "CS101",
      earnedCredits: 4,
      outcome: "PASSED",
      completedTerm: "2024-2025-1",
    },
    {
      courseCode: "MATH201",
      earnedCredits: null,
      outcome: "IN_PROGRESS",
      completedTerm: null,
    },
    {
      courseCode: "PHYS110",
      earnedCredits: null,
      outcome: "UNKNOWN",
      completedTerm: null,
    },
  ],
  transcriptComplete: false,
  sourceKind: "SYNTHETIC",
  createdAt: "2026-10-01T00:00:00Z",
};

const DEMO_AUDIT: AuditResult = {
  curriculumSnapshotId: DEMO_CURRICULUM_ID,
  academicRecordId: DEMO_RECORD_ID,
  recordRevision: DEMO_RECORD.revision,
  transcriptComplete: DEMO_RECORD.transcriptComplete,
  requirements: [
    {
      requirementId: "req:major-core",
      category: "必修",
      courseCodes: ["CS101"],
      requiredCredits: 4,
      earnedCredits: 4,
      gapCredits: 0,
      state: "SATISFIED",
      sourceRefIds: ["source:fixture"],
    },
    {
      requirementId: "req:math-core",
      category: "通识",
      courseCodes: ["MATH201"],
      requiredCredits: 3,
      earnedCredits: 0,
      gapCredits: 3,
      state: "UNSATISFIED",
      sourceRefIds: ["source:fixture"],
    },
    {
      requirementId: "req:physics",
      category: "专业选修",
      courseCodes: ["PHYS110"],
      requiredCredits: 3,
      earnedCredits: null,
      gapCredits: null,
      state: "UNKNOWN",
      sourceRefIds: ["source:fixture"],
    },
  ],
  suggestedCourseCodes: ["MATH201"],
  unknowns: [
    {
      code: "FIXTURE_DATA",
      message: "当前是演示模式，核对结果来自虚构样例，不是真实培养规则计算。",
      field: null,
      retryable: false,
    },
  ],
};

/**
 * 演示模式不生成课程推荐：没有核验器就不该有候选。
 * 结果页的候选渲染由单测用替身客户端覆盖，不由学生可见的演示模式承担。
 */

/**
 * 演示方案的 id。方案里 CS102 已定在周一第 1-2 节，CS103 尚未选班次；
 * 换班次的演示以它为起点。真实服务里 id 由服务端生成，这里只是虚构常量。
 */
export const FIXTURE_PREVIOUS_PLAN_ID = "fixture-plan-e4-v1";
const FIXTURE_OFFERING_SNAPSHOT_ID = "fixture-offering-e4";

/** 演示开课快照：SYNTHETIC，只在演示模式可用；与规划结果里写死的 FIXTURE_OFFERING_SNAPSHOT_ID 一致。 */
const DEMO_OFFERING_SNAPSHOTS: SnapshotSummary[] = [
  {
    snapshotId: FIXTURE_OFFERING_SNAPSHOT_ID,
    kind: "OFFERING",
    state: "PUBLISHED",
    sourceKind: "SYNTHETIC",
    termId: "2025-FALL",
    createdAt: "2026-10-01T00:00:00Z",
    sourceValidation: "SYNTHETIC",
  },
];
const WEEKS_1_TO_16 = Array.from({ length: 16 }, (_, index) => index + 1);

/**
 * 演示方案的基础条目。CS103 的班次为空，换班次后才补上。
 * 这里不写成真实课程：编号和教师都是虚构的。
 */
const FIXTURE_PLAN_BASE_ITEMS: PlanItem[] = [
  { courseCode: "CS102", teacherKey: "teacher-li-01", classId: "CS102-01" },
  { courseCode: "CS103", teacherKey: null, classId: null },
];

/** 学生的硬条件。换班次时必须原样保留在新方案里，不能被静默删除。 */
const FIXTURE_HARD_CONSTRAINTS: Constraint[] = [
  {
    kind: "BLOCK_DAY",
    courseCode: null,
    teacherKey: null,
    dayOfWeek: 5,
    section: null,
    value: null,
    sourceText: "周五不排课（演示数据）",
  },
];

/**
 * 演示方案的核验结论。
 *
 * scope 只能是 SIMULATION：演示数据不是真实班次，标成 REAL_TIMETABLE 会让
 * 「缺班次不给绿色通过」那道展示门禁失效，页面就会把一份虚构课表显示成
 * 已核验通过。verdict 写 VALID 只表示「在这组演示数据里没发现违规」，
 * 页面仍然不会给绿色。
 */
const DEMO_VERIFICATION: PlanValidation = {
  verifierResultId: "fixture-verifier-base",
  verdict: "VALID",
  scope: "SIMULATION",
  curriculumSnapshotId: DEMO_CURRICULUM_ID,
  offeringSnapshotId: FIXTURE_OFFERING_SNAPSHOT_ID,
  recordRevision: DEMO_RECORD.revision,
  violations: [],
  unknownChecks: [
    {
      code: "CLASS_NOT_SELECTED",
      message: "CS103 尚未选定班次，上课时间无法确认（演示数据）。",
      field: null,
      retryable: false,
    },
  ],
  performedChecks: ["PLAN_TIME_OVERLAP", "HARD_CONSTRAINT_BLOCK_DAY"],
  sourceRefIds: ["source:fixture-offering-cs102-01"],
};

const DEMO_ANSWER: PlanningAnswer = {
  taskId: "fixture-task-e2",
  traceId: "fixture-trace-e2",
  decision: "RECOMMENDATIONS",
  academicAudit: DEMO_AUDIT,
  recommendations: [
    {
      planId: FIXTURE_PREVIOUS_PLAN_ID,
      items: structuredClone(FIXTURE_PLAN_BASE_ITEMS),
      explanation:
        "（合成）这份方案用于演示结果页与换班次流程，不是真实推荐；课程、教师和时间都是虚构的。",
      reviewNoteIds: [],
      verification: DEMO_VERIFICATION,
    },
  ],
  clarification: null,
  unknowns: [
    {
      code: "FIXTURE_DATA",
      message:
        "演示模式没有真实核验器，这份方案和它的判决都是合成的，不能当作已核验结果。",
      field: null,
      retryable: false,
    },
  ],
  usage: { inputTokens: null, outputTokens: null, toolCalls: 0, elapsedMs: 0 },
};

/**
 * CS103 的三个班次刻意演示三种状态：
 * 01 与方案里的 CS102 撞在周一第 1-2 节；02 与所有已选课都不冲突；
 * 03 时间文本无法解析，因此 meetings 为空、不能确认冲突。
 */
const CS103_OFFERINGS: CourseOffering[] = [
  {
    courseCode: "CS103",
    classId: "CS103-01",
    teacherKey: "teacher-zhang-02",
    teacherText: "张伟（合成）",
    credits: 3,
    capacity: 60,
    meetingTextRaw: "周一 1-2 节 1-16 周",
    meetings: [
      { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: WEEKS_1_TO_16 },
    ],
    parseStatus: "PARSED",
    sourceRefId: "source:fixture-offering-cs103-01",
  },
  {
    courseCode: "CS103",
    classId: "CS103-02",
    teacherKey: "teacher-wang-03",
    teacherText: "王芳（合成）",
    credits: 3,
    capacity: 60,
    meetingTextRaw: "周四 7-8 节 1-16 周",
    meetings: [
      { dayOfWeek: 4, sectionStart: 7, sectionEnd: 8, weeks: WEEKS_1_TO_16 },
    ],
    parseStatus: "PARSED",
    sourceRefId: "source:fixture-offering-cs103-02",
  },
  {
    courseCode: "CS103",
    classId: "CS103-03",
    teacherKey: null,
    teacherText: "待定（合成）",
    credits: null,
    capacity: null,
    meetingTextRaw: "时间待定",
    meetings: [],
    parseStatus: "UNPARSED",
    sourceRefId: "source:fixture-offering-cs103-03",
  },
];

/**
 * 方案里已选的 CS102 班次。
 *
 * 结果页判断「候选班次会不会撞课」时要先知道已选课程的时间，而时间是按
 * classId 再查一次班次拿到的。这里不给 CS102 的数据，页面就只能说
 * 「时间未知」，三态里的「有冲突」在演示里永远出不来。
 */
const CS102_OFFERINGS: CourseOffering[] = [
  {
    courseCode: "CS102",
    classId: "CS102-01",
    teacherKey: "teacher-li-01",
    teacherText: "李明（合成）",
    credits: 4,
    capacity: 50,
    meetingTextRaw: "周一 1-2 节 1-16 周",
    meetings: [
      { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: WEEKS_1_TO_16 },
    ],
    parseStatus: "PARSED",
    sourceRefId: "source:fixture-offering-cs102-01",
  },
];

const FIXTURE_OFFERINGS = new Map<string, CourseOffering[]>([
  ["CS102", CS102_OFFERINGS],
  ["CS103", CS103_OFFERINGS],
]);

const FIXTURE_TEACHER_OPTIONS: TeacherCourseOption[] = [
  {
    courseCode: "CS103",
    teacherKey: "teacher-zhang-02",
    teacherDisplayName: "张伟（合成）",
    availability: "HISTORICAL_ONLY",
    reviewNoteIds: ["review-cs103-zhang-01"],
    classIds: [],
  },
  {
    courseCode: "CS103",
    teacherKey: "teacher-wang-03",
    teacherDisplayName: "王芳（合成）",
    availability: "UNKNOWN",
    reviewNoteIds: ["review-cs103-wang-01"],
    classIds: ["CS103-02"],
  },
  {
    courseCode: "CS102",
    teacherKey: "teacher-li-01",
    teacherDisplayName: "李明（合成）",
    availability: "HISTORICAL_ONLY",
    reviewNoteIds: [],
    classIds: [],
  },
];

/**
 * 评价证据。第二、三条故意不是精确匹配：一条只对应课程，一条教师未核实，
 * 页面要据此显示「依据有限」，不能把它们当成该教师的评价。
 */
const FIXTURE_REVIEWS: ReviewNote[] = [
  {
    reviewNoteId: "review-cs103-zhang-01",
    courseCode: "CS103",
    teacherKey: "teacher-zhang-02",
    termId: "2024-2025-1",
    sourceKind: "SYNTHETIC",
    publishedAt: "2025-01-10T00:00:00Z",
    sourceUrl: null,
    excerpt: "（合成）作业量适中，期中有一次小组展示，评分标准写在课程大纲里。",
    dimensions: ["WORKLOAD", "GROUP_WORK", "GRADING"],
    matchStatus: "COURSE_TEACHER_MATCHED",
    sourceRefId: "source:fixture-review-cs103-zhang-01",
  },
  {
    reviewNoteId: "review-cs103-course-01",
    courseCode: "CS103",
    teacherKey: null,
    termId: null,
    sourceKind: "SYNTHETIC",
    publishedAt: null,
    sourceUrl: null,
    excerpt: "（合成）课程整体评价偏正面，但没有写明是哪位老师授课。",
    dimensions: ["OVERALL"],
    matchStatus: "COURSE_ONLY",
    sourceRefId: "source:fixture-review-cs103-course-01",
  },
  {
    reviewNoteId: "review-cs103-wang-01",
    courseCode: "CS103",
    teacherKey: "teacher-wang-03",
    termId: "2023-2024-2",
    sourceKind: "SYNTHETIC",
    publishedAt: "2024-07-01T00:00:00Z",
    sourceUrl: null,
    excerpt: "（合成）考勤记录较严格，平时分占比较高。",
    dimensions: ["ATTENDANCE", "GRADING"],
    matchStatus: "UNVERIFIED",
    sourceRefId: "source:fixture-review-cs103-wang-01",
  },
];

const FIXTURE_RUN_REPORT: RunReport = {
  runId: "fixture-run-e7",
  harnessVersion: "fixture-harness-v0",
  parentVersion: null,
  decision: "BASELINE",
  heldOutScore: null,
  averageInputTokens: null,
  averageOutputTokens: null,
  averageToolCalls: null,
  averageLatencyMs: null,
  failureCategories: ["FIXTURE_NO_EVALUATION"],
};

/** 按班次生成核验判决。判决只说明演示数据的情况，不是真实核验。 */
function fixtureVerification(
  offering: CourseOffering,
  verdict: PlanValidation["verdict"],
): PlanValidation {
  const violations: PlanValidation["violations"] =
    verdict === "INVALID"
      ? [
          {
            code: "TIME_CONFLICT",
            message: `${offering.classId} 与方案中的 CS102-01 在周一第 1-2 节时间重叠（演示数据）。`,
            field: null,
            retryable: false,
          },
        ]
      : [];
  const unknownChecks: PlanValidation["unknownChecks"] =
    verdict === "UNKNOWN"
      ? [
          {
            code: "TIME_UNPARSED",
            message: `${offering.classId} 的时间文本「${offering.meetingTextRaw}」无法解析，无法确认它是否与其他课程冲突。`,
            field: null,
            retryable: false,
          },
        ]
      : [];
  return {
    verifierResultId: `fixture-verifier-${offering.classId.toLowerCase()}`,
    verdict,
    // 演示数据不是真实班次，所以 scope 只能是 SIMULATION，不能标成 REAL_TIMETABLE。
    scope: "SIMULATION",
    curriculumSnapshotId: DEMO_CURRICULUM_ID,
    offeringSnapshotId: FIXTURE_OFFERING_SNAPSHOT_ID,
    recordRevision: DEMO_RECORD.revision,
    violations,
    unknownChecks,
    performedChecks: ["PLAN_TIME_OVERLAP", "HARD_CONSTRAINT_BLOCK_DAY"],
    sourceRefIds: [offering.sourceRefId],
  };
}

export class FixtureApiClient implements CoursePilotApiClient {
  readonly mode = "fixture" as const;
  private sessionToken: string | null = null;

  clearSession(): void {
    this.sessionToken = null;
  }

  async createSession(signal?: AbortSignal): Promise<SessionView> {
    this.sessionToken = null;
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(resolve, 60);
      signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timeout);
          reject(new DOMException("Aborted", "AbortError"));
        },
        { once: true },
      );
    });
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    this.sessionToken = DEMO_SESSION_TOKEN;
    return { ...DEMO_SESSION };
  }

  async listCurricula(signal?: AbortSignal): Promise<CurriculumResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return { items: [...DEMO_CURRICULA.items], unknownMessages: [] };
  }

  async listOfferingSnapshots(
    signal?: AbortSignal,
  ): Promise<OfferingSnapshotResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return { items: [...DEMO_OFFERING_SNAPSHOTS], unknownMessages: [] };
  }

  async listCourses(
    curriculumSnapshotId: string,
    cursor: string | null = null,
    signal?: AbortSignal,
    query: string | null = null,
  ): Promise<CourseSearch> {
    void cursor;
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    if (curriculumSnapshotId !== DEMO_CURRICULUM_ID) {
      return { items: [], nextCursor: null };
    }
    const needle = query?.trim().toLowerCase() ?? "";
    const items = DEMO_COURSES.filter(
      (course) =>
        needle === "" ||
        course.courseCode.toLowerCase().includes(needle) ||
        course.name.toLowerCase().includes(needle),
    );
    return { items: structuredClone(items), nextCursor: null };
  }

  async listSessionRecords(signal?: AbortSignal): Promise<AcademicRecordList> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return { items: [structuredClone(DEMO_RECORD)] };
  }

  async saveSessionRecord(
    input: AcademicRecordInput,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AcademicRecord> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return {
      ...structuredClone(DEMO_RECORD),
      revision: DEMO_RECORD.revision + 1,
      curriculumSnapshotId: input.curriculumSnapshotId,
      completedCourses: input.completedCourses,
      transcriptComplete: input.transcriptComplete,
      sourceKind: input.sourceKind,
    };
  }

  async auditRequirements(
    curriculumSnapshotId: string,
    academicRecordId: string,
    signal?: AbortSignal,
  ): Promise<AuditResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return {
      ...structuredClone(DEMO_AUDIT),
      curriculumSnapshotId,
      academicRecordId,
    };
  }

  async submitPlanning(
    _request: PlanningRequest,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<PlanningAnswer> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return structuredClone(DEMO_ANSWER);
  }

  async searchSessionOfferings(
    previousPlanId: string,
    courseCode: string,
    signal?: AbortSignal,
  ): Promise<SessionOfferingSearch> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    // 没有对应课程的班次返回空数组：这是正常业务状态，不是错误。
    // fixture 的数据是确定的，所以空数组就是「确定没有」，status 显式给 OK；
    // 不能用 UNKNOWN 来模拟「无法确认」，那要靠真实快照缺失时的 HTTP 响应。
    return {
      previousPlanId,
      courseCode,
      items: structuredClone(FIXTURE_OFFERINGS.get(courseCode) ?? []),
      status: "OK",
    };
  }

  async replaceSessionPlanItem(
    body: SessionPlanReplaceInput,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SessionPlanReplacement> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    const offering = (FIXTURE_OFFERINGS.get(body.courseCode) ?? []).find(
      (item) => item.classId === body.selectedClassId,
    );
    // 班次必须来自搜索结果；不在结果里的班次不能替换进方案。
    if (!offering) {
      throw new ApiFailure(
        "所选班次不在当前搜索结果里，请重新搜索后再选。",
        "http",
        404,
        "NOT_FOUND",
      );
    }
    // 判决按班次固定：01 冲突、02 有效、03 无法确认。页面不能自己改写这些结论。
    const verdict =
      offering.parseStatus !== "PARSED"
        ? "UNKNOWN"
        : offering.classId === "CS103-01"
          ? "INVALID"
          : "VALID";
    return {
      previousPlanId: body.previousPlanId,
      // 新版本的 planId 必须与旧方案不同，旧方案保留以便学生返回对照。
      planId: `${body.previousPlanId}-${offering.classId}`,
      items: FIXTURE_PLAN_BASE_ITEMS.map((item) =>
        item.courseCode === body.courseCode
          ? {
              courseCode: item.courseCode,
              teacherKey: offering.teacherKey,
              classId: offering.classId,
            }
          : { ...item },
      ),
      hardConstraints: structuredClone(FIXTURE_HARD_CONSTRAINTS),
      verification: fixtureVerification(offering, verdict),
    };
  }

  async removeSessionPlanCourse(
    body: SessionPlanEditInput,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SessionPlanEditResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    const items = FIXTURE_PLAN_BASE_ITEMS.filter(
      (item) => item.courseCode !== body.courseCode,
    ).map((item) => ({ ...item }));
    const hardConstraints = FIXTURE_HARD_CONSTRAINTS.filter(
      (constraint) =>
        !(
          (constraint.kind === "PIN_COURSE" ||
            constraint.kind === "PIN_TEACHER_COURSE") &&
          constraint.courseCode === body.courseCode
        ),
    ).map((constraint) => ({ ...constraint }));
    const remainingOffering =
      items.length > 0
        ? FIXTURE_OFFERINGS.get(items[0].courseCode)?.[0]
        : undefined;
    return {
      previousPlanId: body.previousPlanId,
      planId: `${body.previousPlanId}-without-${body.courseCode}`,
      items,
      hardConstraints,
      empty: items.length === 0,
      verification:
        items.length === 0 || !remainingOffering
          ? null
          : fixtureVerification(remainingOffering, "VALID"),
    };
  }

  async saveSchoolProgress(
    _body: SchoolProgressImportRequest,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SchoolProgressImportResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    throw new ApiFailure(
      "fixture 模式不支持导入学业进度",
      "http",
      501,
      "NOT_IMPLEMENTED",
    );
  }

  async importSchoolProgress(
    body: SchoolProgressImportRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SchoolProgressImportResult> {
    return this.saveSchoolProgress(body, idempotencyKey, signal);
  }

  async getSchoolProgress(
    signal?: AbortSignal,
  ): Promise<SchoolProgressImportResult | null> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return null;
  }

  async listTeacherCourseOptions(
    _curriculumSnapshotId: string,
    courseCode: string | null,
    signal?: AbortSignal,
    query?: string | null,
  ): Promise<TeacherCourseOptionSearch> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    // fixture 数据是确定的，过滤后为空也是确定的「没有」，所以 status 显式给 OK。
    return {
      items: structuredClone(
        FIXTURE_TEACHER_OPTIONS.filter(
          (option) =>
            (courseCode === null || option.courseCode === courseCode) &&
            (!query?.trim() ||
              option.teacherDisplayName
                .toLowerCase()
                .includes(query.trim().toLowerCase())),
        ),
      ),
      status: "OK",
    };
  }

  async searchReviews(
    courseCode: string,
    teacherKey: string | null,
    signal?: AbortSignal,
  ): Promise<ReviewNoteSearch> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    // 按教师过滤时仍保留只对应课程的证据，但不保留别的教师的评价。
    const matches = FIXTURE_REVIEWS.filter(
      (note) =>
        note.courseCode === courseCode &&
        (teacherKey === null ||
          note.teacherKey === null ||
          note.teacherKey === teacherKey),
    );
    // fixture 的评价是确定数据，没有匹配就是确定的「没有找到」，status 显式给 OK。
    return {
      items: structuredClone(matches.slice(0, 5)),
      status: "OK",
    };
  }

  /** 演示模式下的职业方向：虚构内容，description 自带标记，页面照原样显示。 */
  async listCareerDirections(signal?: AbortSignal): Promise<CareerDirection[]> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return [
      {
        directionId: "DIR_DEMO_BACKEND",
        subjectTags: ["计算机", "后端开发"],
        title: "后端与业务系统开发",
        description:
          "【演示数据】偏向服务端开发，需要扎实的编程和数据结构基础。",
        courseCodes: ["CS101", "CS102"],
        sourceRefIds: ["fixture:career:demo"],
      },
    ];
  }

  async getRunReport(runId: string, signal?: AbortSignal): Promise<RunReport> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    // 老师报告不是学生会话里的一页，打开它只能靠直接输网址，而直接输网址就是
    // 整页加载、内存里的会话必然是空的。演示模式下再要求会话，这一页就永远
    // 看不到内容。真实模式仍然要求 bearer + 管理密钥，由服务端强制。
    return { ...structuredClone(FIXTURE_RUN_REPORT), runId };
  }

  fixtureAcademicRecordId(): string {
    return DEMO_RECORD_ID;
  }
}
