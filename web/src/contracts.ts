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
  issues: Array<{
    code: string;
    message: string;
    field: string | null;
    retryable: boolean;
  }>;
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
