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
import type { SchoolProgressNode } from "./school-progress";

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

/**
 * 学校报告里与本类别唯一对应的节点数字。学校数字只作参考来源，保留学校原值。
 * 没有唯一对应（无此类别，或父子同名）时整体为 null，不猜。
 */
export interface SchoolCategoryGap {
  schoolNodeId: string | null;
  requiredCredits: number | null;
  earnedCredits: number | null;
  remainingCredits: number | null;
}

/**
 * 按类别名在学校报告里找唯一节点。找不到或重名（例如父子同名「专业选修课」）都返回 null，
 * 不挑一个来用。
 */
export function schoolCategoryGap(
  category: string | null,
  nodes: readonly SchoolProgressNode[],
): SchoolCategoryGap | null {
  if (category === null) return null;
  const wanted = category.trim();
  const matches = nodes.filter((node) => node.name.trim() === wanted);
  if (matches.length !== 1) return null;
  const node = matches[0]!;
  return {
    schoolNodeId: node.schoolNodeId,
    requiredCredits: node.requiredCredits,
    earnedCredits: node.earnedCredits,
    remainingCredits: node.remainingCredits,
  };
}

/**
 * gapCredits 的来源：JAVA 为本地核对给出的缺口；SCHOOL 表示本地核对无法确定，
 * 账本改用学校报告的剩余学分（页面必须注明「本地核对无法确认」）。
 */
export type GapSource = "JAVA" | "SCHOOL";

export interface CategoryCreditPlan {
  requirementId: string;
  category: string | null;
  requiredCredits: number | null;
  earnedCredits: number | null;
  /** 账本使用的缺口：Java 有值用 Java，否则用学校报告的剩余学分，两者都没有为 null。 */
  gapCredits: number | null;
  gapSource: GapSource | null;
  /** Java 本地核对给出的缺口（不论学校报告如何），供页面说明「本地核对」一侧。 */
  javaGapCredits: number | null;
  /** 与本类别唯一对应的学校报告数字；没有则为 null。 */
  school: SchoolCategoryGap | null;
  /** 候选收窄到学校子类时的子类名（如「思想政治必修课」）；未收窄为 null。 */
  focusLabel?: string | null;
  /** 核对项的数字来源（来自 Java 核对项）：SCHOOL_REPORT 或 LOCAL，缺省视为 LOCAL。 */
  source?: AuditItem["source"];
  /** 在读学分，不计入已获学分；未知或未提供为 null。 */
  inProgressCredits: number | null;
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
  school: SchoolCategoryGap | null = null,
): CategoryCreditPlan {
  const schoolRemaining = school?.remainingCredits ?? null;
  const gapCredits = requirement.gapCredits ?? schoolRemaining;
  const gapSource: GapSource | null =
    requirement.gapCredits !== null
      ? "JAVA"
      : schoolRemaining !== null
        ? "SCHOOL"
        : null;
  const base = {
    requirementId: requirement.requirementId,
    category: requirement.category,
    requiredCredits: requirement.requiredCredits,
    earnedCredits: requirement.earnedCredits,
    gapCredits,
    gapSource,
    javaGapCredits: requirement.gapCredits,
    school,
    source: requirement.source,
    inProgressCredits: requirement.inProgressCredits ?? null,
    focusLabel: null,
  };
  if (requirement.category === null) {
    return { ...base, state: "NO_CATEGORY", countable: [], uncountable: [] };
  }

  const pool = courses.filter(
    (course) =>
      course.category === requirement.category &&
      !completedCodes.has(course.courseCode),
  );
  const { countable, uncountable } = classifyPool(pool, courses, interestTags);
  let state: CategoryPlanState = "NEEDS_CREDITS";
  if (gapCredits === null) state = "UNKNOWN_GAP";
  else if (gapCredits <= 0) state = "SATISFIED";
  return { ...base, state, countable, uncountable };
}

/**
 * 把候选池分成可计入（countable）与待确认（uncountable）两类。
 * catalog 用来数课程号重复；池里的已修课程应已先排除。
 */
export function classifyPool(
  pool: readonly Course[],
  catalog: readonly Course[],
  interestTags: readonly string[],
): { countable: PlanCourse[]; uncountable: UncountableCourse[] } {
  const codeCounts = new Map<string, number>();
  for (const course of catalog) {
    codeCounts.set(
      course.courseCode,
      (codeCounts.get(course.courseCode) ?? 0) + 1,
    );
  }
  const sorted = [...pool].sort((a, b) => byCode(a.courseCode, b.courseCode));
  const countable: PlanCourse[] = [];
  const uncountable: UncountableCourse[] = [];
  for (const course of sorted) {
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
  return { countable, uncountable };
}

/* ---------- 缺口下钻到学校的最细子类 ---------- */

/** 学校类别树里的一个节点（子类）及其在学校报告中的缺口。 */
export interface GapSubcategory {
  nodeId: string;
  name: string;
  remainingCredits: number;
}

/**
 * 从一个第一级类别往下找真正缺分的子类：
 * 某节点还差 > 0 时，若它的子节点里还有差 > 0 的，继续往下；直到没有更深的。
 * 同层有多个并列子类都差分时，全部返回（它们互不重叠，缺口可相加）。
 * 根节点没有缺口或学校没给数字时返回空数组，不猜。
 */
export function deepestGapSubcategories(
  nodes: readonly SchoolProgressNode[],
  rootNodeId: string,
): GapSubcategory[] {
  const root = nodes.find((node) => node.nodeId === rootNodeId);
  if (!root || root.remainingCredits === null || root.remainingCredits <= 0)
    return [];
  const childrenOf = (id: string) =>
    nodes.filter(
      (node) =>
        node.parentId === id &&
        node.remainingCredits !== null &&
        node.remainingCredits > 0,
    );
  let frontier = childrenOf(root.nodeId);
  if (frontier.length === 0) {
    return [
      {
        nodeId: root.nodeId,
        name: root.name.trim(),
        remainingCredits: root.remainingCredits,
      },
    ];
  }
  const result: GapSubcategory[] = [];
  while (frontier.length > 0) {
    const next: SchoolProgressNode[] = [];
    for (const node of frontier) {
      const deeper = childrenOf(node.nodeId);
      if (deeper.length > 0) next.push(...deeper);
      else
        result.push({
          nodeId: node.nodeId,
          name: node.name.trim(),
          remainingCredits: node.remainingCredits ?? 0,
        });
    }
    frontier = next;
  }
  return result;
}

/**
 * 子类的候选课程：学校报告里挂在该子类下的课程号，加上课程目录里类别名与子类同名的课程，
 * 两者取并集。已修 / 在读课程由调用方通过 completedCodes 排除。
 */
export function subcategoryCandidates(
  subcategories: readonly GapSubcategory[],
  schoolCourses: readonly { nodeId: string; courseCode: string }[],
  catalog: readonly Course[],
): Course[] {
  const picked = new Set<Course>();
  for (const sub of subcategories) {
    const linked = new Set(
      schoolCourses
        .filter((course) => course.nodeId === sub.nodeId)
        .map((course) => course.courseCode),
    );
    for (const course of catalog) {
      if (linked.has(course.courseCode) || course.category.trim() === sub.name)
        picked.add(course);
    }
  }
  return [...picked];
}

/**
 * 把一个类别的候选收窄到子类：候选只来自子类，缺口改用子类的剩余学分。
 * 子类下没有可选课程时 countable 为空，页面据此说明，不回退到整个大类。
 */
export function narrowPlanToSubcategories(
  plan: CategoryCreditPlan,
  subcategories: readonly GapSubcategory[],
  candidates: readonly Course[],
  completedCodes: ReadonlySet<string>,
  interestTags: readonly string[],
  catalog: readonly Course[],
): CategoryCreditPlan {
  const pool = candidates.filter(
    (course) => !completedCodes.has(course.courseCode),
  );
  const { countable, uncountable } = classifyPool(pool, catalog, interestTags);
  const remaining = subcategories.reduce(
    (sum, sub) => sum + toCents(sub.remainingCredits),
    0,
  );
  return {
    ...plan,
    gapCredits: remaining / 100,
    gapSource: "SCHOOL",
    focusLabel: subcategories.map((sub) => sub.name).join("、"),
    countable,
    uncountable,
    state: "NEEDS_CREDITS",
  };
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
 * options.minCourses 可要求组合至少几门课（页面用 2，单门课已在候选列表里）。
 */
export function suggestCompletions(
  plan: CategoryCreditPlan,
  selectedCodes: readonly string[],
  remainingCredits: number | null,
  options: { minCourses?: number } = {},
): CompletionSuggestion[] {
  const minCourses = options.minCourses ?? 1;
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
    if (codes.length >= minCourses) {
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
