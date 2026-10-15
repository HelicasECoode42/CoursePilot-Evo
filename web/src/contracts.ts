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
    hardConstraints: Array<{
      kind: "BLOCK_DAY" | "BLOCK_SECTION" | "BLOCK_SLOT";
      courseCode: null;
      teacherKey: null;
      dayOfWeek: number | null;
      section: number | null;
      value: number | null;
      sourceText: string;
    }>;
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
