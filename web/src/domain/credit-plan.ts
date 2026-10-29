/**
 * 凑学分（购物车模式）的纯规则。前端只做加法，不定义学分规则。
 *
 * 缺口（gapCredits）、类别、学分、已修课程全部来自 Java 的学业核对与课程目录。
 * 这里负责三件事：
 *   1. 候选课程：类别匹配、排除已修、学分 null / 0 的单独列出；
 *   2. 账本：已选课程的学分求和，算出还差多少、超出多少；
 *   3. 补齐建议：按恰好、超出、未补齐分层，最多组合四门课。
 *
 * 学分用「分」（整数）累加，避免小数误差。
 */

import type { AuditItem, Course } from "../contracts";

/** 补齐建议最多由几门课组成。 */
export const MAX_SUGGESTION_COURSES = 4;
/** 每层最多展示几条。 */
export const MAX_SUGGESTIONS = 20;
/** 限制同步计算的组合数；课程仍完整显示在候选列表。 */
export const MAX_COMBINATIONS = 200000;
/** 培养方案里系统没建模、不参与核验的规则。凑分页必须原样展示。 */
export const UNMODELED_RULES_CODE = "UNMODELED_CURRICULUM_RULES";

export interface PlanCourse {
  courseCode: string;
  name: string;
  category: string;
  /** 只有可计入凑分的课程才有数字。 */
  credits: number;
  relevance: number;
}

export interface UncountableCourse {
  courseCode: string;
  name: string;
  credits: number | null;
  reason: "CREDITS_UNKNOWN" | "ZERO_CREDITS" | "AMBIGUOUS_COURSE_CODE";
}

export type CategoryPlanState =
  | "NEEDS_CREDITS"
  | "SATISFIED"
  | "UNKNOWN_GAP"
  | "NO_CATEGORY";

export interface CategoryCreditPlan {
  requirementId: string;
  category: string | null;
  requiredCredits: number | null;
  earnedCredits: number | null;
  gapCredits: number | null;
  state: CategoryPlanState;
  /** 可计入凑分的候选，按相关度、再按课程号排序。 */
  countable: PlanCourse[];
  uncountable: UncountableCourse[];
}

export interface SelectionLedger {
  /** 已选且可计入的课程学分合计（只算 countable 里的课）。 */
  selectedCredits: number;
  /** 已选课程数（只算 countable 里的课）。 */
  selectedCount: number;
  /** 还差多少学分；缺口为 null 时为 null。负数不会出现，超出见 overCredits。 */
  remainingCredits: number | null;
  /** 超出多少学分；没超出为 0。 */
  overCredits: number;
}

/** 学分换成整数「分」。学分最多两位小数，四舍五入不丢精度。 */
export function toCents(credits: number): number {
  return Math.round(credits * 100);
}

/** 兴趣关键词命中数：课程名里包含几个关键词，同一关键词只算一次。 */
export function interestRelevance(
  name: string,
  tags: readonly string[],
): number {
  const haystack = name.toLowerCase();
  let hits = 0;
  const seen = new Set<string>();
  for (const raw of tags) {
    const tag = raw.trim().toLowerCase();
    if (tag === "" || seen.has(tag)) continue;
    seen.add(tag);
    if (haystack.includes(tag)) hits += 1;
  }
  return hits;
}

function byCode(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * 为一个学业核对要求建立候选视图。
 * courses 是课程目录；completedCodes 是学生已修课程号，全部排除。
 */
export function buildCategoryPlan(
  requirement: AuditItem,
  courses: readonly Course[],
  completedCodes: ReadonlySet<string>,
  interestTags: readonly string[],
): CategoryCreditPlan {
  const base = {
    requirementId: requirement.requirementId,
    category: requirement.category,
    requiredCredits: requirement.requiredCredits,
    earnedCredits: requirement.earnedCredits,
    gapCredits: requirement.gapCredits,
  };
  if (requirement.category === null) {
    return { ...base, state: "NO_CATEGORY", countable: [], uncountable: [] };
  }

  const codeCounts = new Map<string, number>();
  for (const course of courses) {
    codeCounts.set(
      course.courseCode,
      (codeCounts.get(course.courseCode) ?? 0) + 1,
    );
  }
  const pool = courses
    .filter(
      (course) =>
        course.category === requirement.category &&
        (!completedCodes.has(course.courseCode) ||
          (codeCounts.get(course.courseCode) ?? 0) > 1),
    )
    .sort((a, b) => byCode(a.courseCode, b.courseCode));

  const countable: PlanCourse[] = [];
  const uncountable: UncountableCourse[] = [];
  for (const course of pool) {
    if ((codeCounts.get(course.courseCode) ?? 0) > 1) {
      uncountable.push({
        courseCode: course.courseCode,
        name: course.name,
        credits: course.credits,
        reason: "AMBIGUOUS_COURSE_CODE",
      });
    } else if (course.credits === null) {
      uncountable.push({
        courseCode: course.courseCode,
        name: course.name,
        credits: null,
        reason: "CREDITS_UNKNOWN",
      });
    } else if (course.credits === 0) {
      uncountable.push({
        courseCode: course.courseCode,
        name: course.name,
        credits: 0,
        reason: "ZERO_CREDITS",
      });
    } else {
      countable.push({
        courseCode: course.courseCode,
        name: course.name,
        category: course.category,
        credits: course.credits,
        relevance: interestRelevance(course.name, interestTags),
      });
    }
  }
  countable.sort(
    (a, b) => b.relevance - a.relevance || byCode(a.courseCode, b.courseCode),
  );

  let state: CategoryPlanState = "NEEDS_CREDITS";
  if (requirement.gapCredits === null) state = "UNKNOWN_GAP";
  else if (requirement.gapCredits <= 0) state = "SATISFIED";
  return { ...base, state, countable, uncountable };
}

/**
 * 账本：已选课程的学分求和，算还差多少或超出多少。
 * 只认 countable 里的课；选中的课号若不在候选里（过期选择）直接忽略。
 */
export function summarizeSelection(
  plan: CategoryCreditPlan,
  selectedCodes: readonly string[],
): SelectionLedger {
  const chosen = new Set(selectedCodes);
  const picked = plan.countable.filter((course) =>
    chosen.has(course.courseCode),
  );
  const selectedCents = picked.reduce(
    (sum, course) => sum + toCents(course.credits),
    0,
  );
  if (plan.gapCredits === null) {
    return {
      selectedCredits: selectedCents / 100,
      selectedCount: picked.length,
      remainingCredits: null,
      overCredits: 0,
    };
  }
  const gapCents = toCents(plan.gapCredits);
  const remainingCents = gapCents - selectedCents;
  return {
    selectedCredits: selectedCents / 100,
    selectedCount: picked.length,
    remainingCredits: Math.max(0, remainingCents) / 100,
    overCredits: Math.max(0, -remainingCents) / 100,
  };
}

/** 仅对明确且大于零的缺口给出建议。 */
export function suggestionsApply(remainingCredits: number | null): boolean {
  if (remainingCredits === null) return false;
  return toCents(remainingCredits) > 0;
}

export interface CompletionSuggestion {
  courseCodes: string[];
  totalCredits: number;
  relevance: number;
  category: "EXACT" | "OVER" | "UNDER";
  difference: number;
}

/**
 * 恰好补齐、超出、未补齐分层，超出层按超出多少排序，同层按兴趣相关度排序。
 * 每层保留前 MAX_SUGGESTIONS 条，最多遍历 MAX_COMBINATIONS 个组合。
 */
export function suggestCompletions(
  plan: CategoryCreditPlan,
  selectedCodes: readonly string[],
  remainingCredits: number | null,
): CompletionSuggestion[] {
  if (!suggestionsApply(remainingCredits)) return [];
  const targetCents = toCents(remainingCredits!);
  const chosen = new Set(selectedCodes);
  const pool = plan.countable.filter(
    (course) => !chosen.has(course.courseCode),
  );

  const groups: Record<
    CompletionSuggestion["category"],
    CompletionSuggestion[]
  > = {
    EXACT: [],
    OVER: [],
    UNDER: [],
  };
  let visited = 0;
  const compare = (a: CompletionSuggestion, b: CompletionSuggestion) =>
    (a.category === "OVER" ? a.difference - b.difference : 0) ||
    b.relevance - a.relevance ||
    a.courseCodes.length - b.courseCodes.length ||
    byCode(a.courseCodes.join(","), b.courseCodes.join(","));
  function visit(
    start: number,
    codes: string[],
    cents: number,
    relevance: number,
  ) {
    if (visited >= MAX_COMBINATIONS) return;
    if (codes.length) {
      visited += 1;
      const category =
        cents === targetCents
          ? "EXACT"
          : cents > targetCents
            ? "OVER"
            : "UNDER";
      const group = groups[category];
      group.push({
        courseCodes: [...codes].sort(byCode),
        totalCredits: cents / 100,
        relevance,
        category,
        difference: Math.abs(cents - targetCents) / 100,
      });
      group.sort(compare);
      if (group.length > MAX_SUGGESTIONS) group.pop();
    }
    if (codes.length === MAX_SUGGESTION_COURSES) return;
    for (let i = start; i < pool.length && visited < MAX_COMBINATIONS; i += 1) {
      const course = pool[i];
      visit(
        i + 1,
        [...codes, course.courseCode],
        cents + toCents(course.credits),
        relevance + course.relevance,
      );
    }
  }
  visit(0, [], 0, 0);
  return [...groups.EXACT, ...groups.OVER, ...groups.UNDER];
}
