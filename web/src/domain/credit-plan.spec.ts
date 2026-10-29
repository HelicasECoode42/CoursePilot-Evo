import { describe, expect, it } from "vitest";
import type { AuditItem, Course } from "../contracts";
import {
  MAX_SUGGESTIONS,
  buildCategoryPlan,
  interestRelevance,
  suggestCompletions,
  suggestionsApply,
  summarizeSelection,
} from "./credit-plan";

const ELECTIVE = "专业选修课";
const NONE = new Set<string>();

function course(
  code: string,
  credits: number | null,
  name = `课程${code}`,
  category = ELECTIVE,
): Course {
  return { courseCode: code, name, credits, category, sourceRefIds: [] };
}

function requirement(
  gap: number | null,
  overrides: Partial<AuditItem> = {},
): AuditItem {
  return {
    requirementId: "req-elective",
    category: ELECTIVE,
    courseCodes: [],
    requiredCredits: 24,
    earnedCredits: gap === null ? null : 24 - gap,
    gapCredits: gap,
    state: gap === 0 ? "SATISFIED" : "UNSATISFIED",
    sourceRefIds: [],
    ...overrides,
  };
}

describe("候选课程", () => {
  it("保留重复占位编号的课程，并且不将其计入学分或认定为已修", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [course("008532xx", 1, "体育1"), course("008532xx", 1, "体育2")],
      new Set(["008532xx"]),
      [],
    );
    expect(plan.countable).toHaveLength(0);
    expect(plan.uncountable.map((item) => item.name)).toEqual([
      "体育1",
      "体育2",
    ]);
    expect(
      plan.uncountable.every((item) => item.reason === "AMBIGUOUS_COURSE_CODE"),
    ).toBe(true);
  });
  it("排除已修课程，学分 null 与 0 单独列出，不进入候选", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [
        course("N1", null),
        course("Z1", 0),
        course("E3", 3),
        course("E1", 1),
        course("DONE", 3),
      ],
      new Set(["DONE"]),
      [],
    );
    expect(plan.countable.map((c) => c.courseCode)).toEqual(["E1", "E3"]);
    expect(plan.uncountable).toEqual([
      {
        courseCode: "N1",
        name: "课程N1",
        credits: null,
        reason: "CREDITS_UNKNOWN",
      },
      { courseCode: "Z1", name: "课程Z1", credits: 0, reason: "ZERO_CREDITS" },
    ]);
  });

  it("按兴趣相关度排前面，同分按课程号", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [
        course("A1", 3, "编译原理"),
        course("B1", 3, "机器学习导论"),
        course("C1", 3, "深度学习实践"),
      ],
      NONE,
      ["学习", "机器"],
    );
    expect(plan.countable.map((c) => c.courseCode)).toEqual(["B1", "C1", "A1"]);
  });

  it("没有类别名时状态为 NO_CATEGORY，缺口为 null 时状态为 UNKNOWN_GAP", () => {
    expect(
      buildCategoryPlan(
        requirement(3, { category: null }),
        [course("E3", 3)],
        NONE,
        [],
      ).state,
    ).toBe("NO_CATEGORY");
    expect(
      buildCategoryPlan(requirement(null), [course("E3", 3)], NONE, []).state,
    ).toBe("UNKNOWN_GAP");
    expect(
      buildCategoryPlan(requirement(0), [course("E3", 3)], NONE, []).state,
    ).toBe("SATISFIED");
  });
});

describe("账本：已选课程的加减", () => {
  const plan = buildCategoryPlan(
    requirement(21),
    [course("E5", 5), course("E4", 4), course("E3", 3), course("E2", 2)],
    NONE,
    [],
  );

  it("没选时显示整个缺口", () => {
    expect(summarizeSelection(plan, [])).toEqual({
      selectedCredits: 0,
      selectedCount: 0,
      remainingCredits: 21,
      overCredits: 0,
    });
  });

  it("选了几门后还差多少", () => {
    const ledger = summarizeSelection(plan, ["E5", "E4"]);
    expect(ledger.selectedCredits).toBe(9);
    expect(ledger.selectedCount).toBe(2);
    expect(ledger.remainingCredits).toBe(12);
    expect(ledger.overCredits).toBe(0);
  });

  it("超了不报错，显示超出多少", () => {
    const small = buildCategoryPlan(
      requirement(6),
      [course("E5", 5), course("E4", 4)],
      NONE,
      [],
    );
    const ledger = summarizeSelection(small, ["E5", "E4"]);
    expect(ledger.remainingCredits).toBe(0);
    expect(ledger.overCredits).toBe(3);
  });

  it("过期或不在候选里的选择被忽略；缺口为 null 时剩余为 null", () => {
    expect(summarizeSelection(plan, ["GHOST"]).selectedCount).toBe(0);
    const unknown = buildCategoryPlan(
      requirement(null),
      [course("E5", 5)],
      NONE,
      [],
    );
    expect(summarizeSelection(unknown, ["E5"]).remainingCredits).toBeNull();
  });

  it("小数学分用整数分相加", () => {
    const decimals = buildCategoryPlan(
      requirement(0.3),
      [course("A", 0.1), course("B", 0.2)],
      NONE,
      [],
    );
    expect(summarizeSelection(decimals, ["A", "B"]).remainingCredits).toBe(0);
  });
});

describe("学分组合建议", () => {
  it("按恰好、超出、未补齐排序，超出少的优先", () => {
    const plan = buildCategoryPlan(
      requirement(6),
      [course("A", 2), course("B", 4), course("C", 7), course("D", 9)],
      NONE,
      [],
    );
    const result = suggestCompletions(plan, [], 6);
    expect(result[0].courseCodes).toEqual(["A", "B"]);
    const categories = result.map((s) => s.category);
    expect(categories.lastIndexOf("EXACT")).toBeLessThan(
      categories.indexOf("OVER"),
    );
    expect(categories.lastIndexOf("OVER")).toBeLessThan(
      categories.indexOf("UNDER"),
    );
    const over = result.filter((s) => s.category === "OVER");
    expect(over.map((s) => s.difference)).toEqual(
      [...over.map((s) => s.difference)].sort((a, b) => a - b),
    );
  });
  it("支持四门课、较大缺口及每层上限", () => {
    const courses = Array.from({ length: 25 }, (_, i) =>
      course(`C${String(i).padStart(2, "0")}`, 6),
    );
    const plan = buildCategoryPlan(requirement(24), courses, NONE, []);
    const result = suggestCompletions(plan, [], 24);
    expect(
      result.some((s) => s.category === "EXACT" && s.courseCodes.length === 4),
    ).toBe(true);
    expect(result.every((s) => s.courseCodes.length <= 4)).toBe(true);
    for (const kind of ["EXACT", "OVER", "UNDER"])
      expect(
        result.filter((s) => s.category === kind).length,
      ).toBeLessThanOrEqual(MAX_SUGGESTIONS);
  });
  it("排除已选、未知学分及重复编号；未知或已满足缺口不推荐", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [
        course("A", 3),
        course("B", null),
        course("D", 1, "体育1"),
        course("D", 1, "体育2"),
      ],
      NONE,
      [],
    );
    expect(suggestCompletions(plan, ["A"], 3)).toEqual([]);
    expect(suggestionsApply(null)).toBe(false);
    expect(suggestionsApply(0)).toBe(false);
    expect(suggestionsApply(24)).toBe(true);
  });
  it("同层按兴趣相关度排序", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [course("A", 3, "编译原理"), course("B", 3, "机器学习")],
      NONE,
      ["机器"],
    );
    expect(suggestCompletions(plan, [], 3)[0].courseCodes).toEqual(["B"]);
  });
});

describe("interestRelevance", () => {
  it("同一关键词只计一次，空白忽略", () => {
    expect(interestRelevance("数据结构", ["数据", " 数据 ", ""])).toBe(1);
    expect(interestRelevance("数据结构", [])).toBe(0);
  });
});
