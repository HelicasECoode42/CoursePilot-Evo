import type domainSchema from "../../contracts/schemas/domain.schema.json";

export const SCHEMA_VERSION = "1.0" as const;

export const MOTIVES = [
  "GPA",
  "LOW_WORKLOAD",
  "LOW_ATTENDANCE",
  "GOOD_REVIEWS",
  "SPECIFIC_TEACHER",
  "INTEREST",
  "CAREER",
  "POSTGRAD",
  "CREDIT_PROGRESS",
  "SCHEDULE",
] as const satisfies readonly (typeof domainSchema.$defs.GoalIntent.properties.motives.items.enum)[number][];

export type Motive = (typeof MOTIVES)[number];
export type PlanningMode = "REAL" | "SIMULATION";

export interface Envelope<T> {
  schemaVersion: typeof SCHEMA_VERSION;
  requestId: string;
  traceId: string | null;
  status:
    | "OK"
    | "UNKNOWN"
    | "INVALID_INPUT"
    | "UNAUTHORIZED"
    | "FORBIDDEN"
    | "NOT_FOUND"
    | "CONFLICT"
    | "ERROR";
  data: T;
  provenance: unknown[];
  issues: Issue[];
}

export interface SessionResult {
  sessionId: string;
  sessionToken: string;
  expiresAt: string;
}

export interface SnapshotSummary {
  snapshotId: string;
  kind: "CURRICULUM" | "OFFERING";
  state: "PUBLISHED" | "REJECTED";
  sourceKind: "CURRICULUM_FILE" | "BROWSER_SNAPSHOT" | "SYNTHETIC";
  termId: string | null;
  createdAt: string;
  sourceValidation: "VERIFIED" | "UNVERIFIED" | "SYNTHETIC";
  displayName?: string | null;
}

export interface PlanningRequest {
  schemaVersion: typeof SCHEMA_VERSION;
  curriculumSnapshotId: string;
  offeringSnapshotId: string | null;
  academicRecordId: string;
  mode: PlanningMode;
  promptText: string;
  intent: {
    motives: Motive[];
    priorityOrder: string[];
    hardConstraints: Constraint[];
    softPreferences: Array<{
      dimension: string;
      value: string;
      sourceText: string;
    }>;
    pinnedTeacherCoursePairs: Array<{
      courseCode: string;
      teacherKey: string;
      mode: "MUST" | "PREFER";
    }>;
    interestTags: string[];
    careerDirectionIds: string[];
  };
  previousPlanId: string | null;
}

export type DomainSchema = typeof domainSchema;

// --- E2: 学业记录、核对与规划答复（字段以 contracts/schemas/domain.schema.json 为准） ---

/** 业务错误项。系统错误与业务未知共用这个形状，语义由 code 决定。 */
export interface Issue {
  code: string;
  message: string;
  field: string | null;
  retryable: boolean;
}

export type CourseOutcome = "PASSED" | "FAILED" | "IN_PROGRESS" | "UNKNOWN";

/** 一条已修课程。earnedCredits / completedTerm 未知时是 null，不转成 0。 */
export interface CompletedCourse {
  courseCode: string;
  earnedCredits: number | null;
  outcome: CourseOutcome;
  completedTerm: string | null;
}

/** 一份学业记录。academicRecordId 由服务端生成，学生不提交。 */
export interface AcademicRecord {
  academicRecordId: string;
  revision: number;
  curriculumSnapshotId: string;
  completedCourses: CompletedCourse[];
  transcriptComplete: boolean;
  sourceKind: "USER_IMPORT" | "SYNTHETIC";
  createdAt: string;
}

export interface AcademicRecordInput {
  schemaVersion: typeof SCHEMA_VERSION;
  curriculumSnapshotId: string;
  completedCourses: CompletedCourse[];
  transcriptComplete: boolean;
  sourceKind: "USER_IMPORT" | "SYNTHETIC";
}

/** 三态必须分开展示：UNKNOWN 不许渲染成已满足。 */
export type AuditState = "SATISFIED" | "UNSATISFIED" | "UNKNOWN";

export interface AuditItem {
  requirementId: string;
  /** 类别名（必修 / 通识 …）。为 null 时才退回显示序号。 */
  category: string | null;
  courseCodes: string[];
  requiredCredits: number | null;
  earnedCredits: number | null;
  gapCredits: number | null;
  state: AuditState;
  sourceRefIds: string[];
}

export interface AuditResult {
  curriculumSnapshotId: string;
  academicRecordId: string;
  recordRevision: number;
  transcriptComplete: boolean;
  requirements: AuditItem[];
  suggestedCourseCodes: string[];
  unknowns: Issue[];
}

export interface PlanItem {
  courseCode: string;
  teacherKey: string | null;
  classId: string | null;
}

export type PlanVerdict = "VALID" | "INVALID" | "UNKNOWN";
export type PlanScope = "COURSE_ONLY" | "REAL_TIMETABLE" | "SIMULATION";

/** 核验器判决。页面原样展示，不自行改写，也不从 violations 为空推断通过。 */
export interface PlanValidation {
  verifierResultId: string;
  verdict: PlanVerdict;
  scope: PlanScope;
  curriculumSnapshotId: string;
  offeringSnapshotId: string | null;
  recordRevision: number;
  violations: Issue[];
  unknownChecks: Issue[];
  performedChecks: string[];
  sourceRefIds: string[];
}

export interface QuestionChoice {
  value: string;
  label: string;
}

export interface Question {
  questionId: string;
  text: string;
  choices: QuestionChoice[];
  allowFreeText: boolean;
  requiredFor: string[];
}

export interface Recommendation {
  planId: string;
  items: PlanItem[];
  explanation: string;
  reviewNoteIds: string[];
  courseRationales?: {
    courseCode: string;
    reason: string;
    reviewNoteIds: string[];
    courseSourceRefIds?: string[];
    reviewBasisStatus?: "HAS_EVIDENCE" | "NO_RECORDS" | "NOT_QUERIED" | null;
    rationaleSource?: "MODEL" | "COURSE_FACTS" | null;
    reviewEvidenceRefs?: Array<{ reviewNoteId: string; sourceRefId: string }>;
  }[];
  explorationDirections?: {
    title: string;
    description: string;
    steps: string[];
  }[];
  verification: PlanValidation;
}

export interface Usage {
  inputTokens: number | null;
  outputTokens: number | null;
  toolCalls: number;
  elapsedMs: number;
}

export type PlanningDecision =
  | "RECOMMENDATIONS"
  | "CLARIFY"
  | "UNABLE_TO_VERIFY";

export interface PlanningAnswer {
  taskId: string;
  traceId: string;
  decision: PlanningDecision;
  academicAudit: AuditResult;
  recommendations: Recommendation[];
  clarification: Question | null;
  unknowns: Issue[];
  usage: Usage;
}

/** `GET /api/v1/academic-records` 的 data：items 为空数组表示本会话尚无记录。 */
export interface AcademicRecordList {
  items: AcademicRecord[];
}

// --- E4: 换班次、教师与评价、运行报告（字段以 contracts/schemas/domain.schema.json 为准） ---

export interface Course {
  courseCode: string;
  name: string;
  credits: number | null;
  category: string;
  sourceRefIds: string[];
  suggestedTerm?: string | null;
}

/** 一次上课时段。weeks 是教学周号，去重后不超过 60 个。 */
export interface Meeting {
  dayOfWeek: number;
  sectionStart: number;
  sectionEnd: number;
  weeks: number[];
}

/**
 * 一个开课班次。只是可替换的候选，不构成核验结论：候选自身无冲突不代表
 * 放进整份方案后无冲突，必须经换班次接口对整份方案重新核验。
 * parseStatus 不是 PARSED 时 meetings 为空，页面要说明时间未能确认。
 */
export interface CourseOffering {
  courseCode: string;
  classId: string;
  teacherKey: string | null;
  teacherText: string;
  credits: number | null;
  capacity: number | null;
  meetingTextRaw: string;
  meetings: Meeting[];
  parseStatus: "PARSED" | "UNPARSED" | "INVALID";
  sourceRefId: string;
}

/** 学生的硬条件。kind 决定哪些字段必须非空，见 domain.schema.json 的 allOf。 */
export interface Constraint {
  kind:
    | "BLOCK_DAY"
    | "BLOCK_SECTION"
    | "BLOCK_SLOT"
    | "PIN_TEACHER_COURSE"
    | "PIN_COURSE"
    | "MAX_CREDITS";
  courseCode: string | null;
  teacherKey: string | null;
  dayOfWeek: number | null;
  section: number | null;
  value: number | null;
  sourceText: string;
}

/**
 * 教师与课程的对应。历史与当期分开：HISTORICAL_ONLY 只说明教过，不说明本学期会开；
 * UNKNOWN 表示当期是否开课无法确认，页面不能把它显示成可选。
 */
export interface TeacherCourseOption {
  courseCode: string;
  teacherKey: string;
  teacherDisplayName: string;
  availability: "CURRENT_VERIFIED" | "HISTORICAL_ONLY" | "UNKNOWN";
  reviewNoteIds: string[];
  classIds: string[];
}

/**
 * 一条评价证据。matchStatus 不是 COURSE_TEACHER_MATCHED 时，依据只能对应课程或
 * 未核实的教师，页面要标注「依据有限」，不能当作该教师的评价。
 */
export interface ReviewNote {
  reviewNoteId: string;
  courseCode: string;
  teacherKey: string | null;
  teacherDisplayName?: string | null;
  termId: string | null;
  sourceKind:
    | "OFFICIAL_SYLLABUS"
    | "USER_IMPORT"
    | "EXTERNAL_LINK"
    | "SYNTHETIC";
  publishedAt: string | null;
  sourceUrl: string | null;
  excerpt: string;
  dimensions: Array<
    | "GRADING"
    | "ATTENDANCE"
    | "WORKLOAD"
    | "EXAM"
    | "GROUP_WORK"
    | "PRESENTATION"
    | "TEACHING"
    | "OVERALL"
  >;
  matchStatus: "COURSE_TEACHER_MATCHED" | "COURSE_ONLY" | "UNVERIFIED";
  sourceRefId: string;
}

/** 受限的运行报告。heldOutScore 与各项平均值未知时为 null，不转成 0。 */
export interface RunReport {
  runId: string;
  harnessVersion: string;
  parentVersion: string | null;
  decision: "BASELINE" | "PROMOTED" | "REJECTED";
  heldOutScore: number | null;
  averageInputTokens: number | null;
  averageOutputTokens: number | null;
  averageToolCalls: number | null;
  averageLatencyMs: number | null;
  failureCategories: string[];
}

/** `GET /api/v1/session-offerings` 的 data。items 为空数组是正常业务状态。 */
export interface SessionOfferingList {
  previousPlanId: string;
  courseCode: string;
  items: CourseOffering[];
}

/** `POST /api/v1/session-plans/replace` 的请求体。selectedClassId 必须来自搜索结果。 */
export interface SessionPlanReplaceInput {
  previousPlanId: string;
  courseCode: string;
  selectedClassId: string;
}

/**
 * 换班次后的新方案。verification 是对整份新方案的判决，原样展示，
 * 不能把 INVALID 或 UNKNOWN 改写成有效。
 */
export interface SessionPlanReplacement {
  previousPlanId: string;
  planId: string;
  items: PlanItem[];
  hardConstraints: Constraint[];
  verification: PlanValidation;
}

export interface SessionPlanEditInput {
  previousPlanId: string;
  courseCode: string;
}

export interface SessionPlanEditResult {
  previousPlanId: string;
  planId: string;
  items: PlanItem[];
  hardConstraints: Constraint[];
  verification: PlanValidation | null;
  empty: boolean;
}
