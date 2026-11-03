import { describe, expect, it } from "vitest";
import type { AuditItem, Course } from "../contracts";
import {
  MAX_SUGGESTIONS,
  buildCategoryPlan,
  deepestGapSubcategories,
  interestRelevance,
  narrowPlanToSubcategories,
  schoolCategoryGap,
  subcategoryCandidates,
  suggestCompletions,
  suggestionsApply,
  summarizeSelection,
} from "./credit-plan";
import type { SchoolProgressNode } from "./school-progress";

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
  it("已通过的重复课程编号仍从候选中排除", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [course("DONE", 3), course("DONE", 3)],
      new Set(["DONE"]),
      [],
    );
    expect(plan.countable).toHaveLength(0);
    expect(plan.uncountable).toHaveLength(0);
  });
  it("保留重复占位编号的课程，并且不将其计入学分或认定为已修", () => {
    const plan = buildCategoryPlan(
      requirement(3),
      [course("008532xx", 1, "体育1"), course("008532xx", 1, "体育2")],
      NONE,
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

// 学校报告节点形状与 school-progress 的 SchoolProgressNode 一致，名字与数字均为虚构。
function schoolNode(
  nodeId: string,
  name: string,
  parentId: string | null,
  remaining: number | null,
): SchoolProgressNode {
  return {
    nodeId,
    parentId,
    schoolNodeId: `S-${nodeId}`,
    leaf: parentId !== null,
    name,
    requiredCredits: 12,
    earnedCredits: remaining === null ? null : 12 - remaining,
    remainingCredits: remaining,
  };
}

describe("学校报告数字作为缺口的后备来源", () => {
  it("matches a school category only when exactly one node has that name", () => {
    const nodes = [
      schoolNode("top", "通识课", null, 0),
      schoolNode("dup-parent", "专业选修课", null, 5),
      schoolNode("dup-child", "专业选修课", "dup-parent", 2),
    ];
    expect(schoolCategoryGap("通识课", nodes)).toEqual({
      schoolNodeId: "S-top",
      requiredCredits: 12,
      earnedCredits: 12,
      remainingCredits: 0,
    });
    expect(schoolCategoryGap("专业选修课", nodes)).toBeNull();
    expect(schoolCategoryGap(null, nodes)).toBeNull();
  });

  it("uses the school remaining credits when the Java gap is unknown, labelled as school-sourced", () => {
    const plan = buildCategoryPlan(
      requirement(null, {
        gapCredits: null,
        earnedCredits: null,
        state: "UNKNOWN",
      }),
      [course("E2", 2), course("E4", 4)],
      NONE,
      [],
      schoolCategoryGap("专业选修课", [schoolNode("p", "专业选修课", null, 6)]),
    );
    expect(plan.state).toBe("NEEDS_CREDITS");
    expect(plan.gapCredits).toBe(6);
    expect(plan.gapSource).toBe("SCHOOL");
    expect(plan.javaGapCredits).toBeNull();
    expect(plan.school?.earnedCredits).toBe(6);
    expect(summarizeSelection(plan, ["E4"]).remainingCredits).toBe(2);
  });

  it("keeps the Java gap when Java knows it, even if the school report differs", () => {
    const plan = buildCategoryPlan(
      requirement(4),
      [course("E2", 2)],
      NONE,
      [],
      schoolCategoryGap("专业选修课", [schoolNode("p", "专业选修课", null, 9)]),
    );
    expect(plan.gapCredits).toBe(4);
    expect(plan.gapSource).toBe("JAVA");
  });

  it("stays unknown when neither Java nor the school report gives a gap", () => {
    const plan = buildCategoryPlan(
      requirement(null, { gapCredits: null }),
      [course("E2", 2)],
      NONE,
      [],
      null,
    );
    expect(plan.state).toBe("UNKNOWN_GAP");
    expect(plan.gapSource).toBeNull();
  });

  it("treats a school remaining of zero as satisfied from the school source", () => {
    const plan = buildCategoryPlan(
      requirement(null, { gapCredits: null }),
      [course("E2", 2)],
      NONE,
      [],
      schoolCategoryGap("专业选修课", [schoolNode("p", "专业选修课", null, 0)]),
    );
    expect(plan.state).toBe("SATISFIED");
    expect(plan.gapSource).toBe("SCHOOL");
  });

  describe("缺口下钻到学校子类（合成数据）", () => {
    const node = (
      nodeId: string,
      parentId: string | null,
      name: string,
      remaining: number | null,
    ): SchoolProgressNode => ({
      nodeId,
      parentId,
      schoolNodeId: nodeId,
      leaf: false,
      name,
      requiredCredits: null,
      earnedCredits: null,
      remainingCredits: remaining,
    });

    it("一直往下找到没有更深缺口的子类；并列子类全部返回", () => {
      const nodes = [
        node("root", null, "公共基础课", 6),
        node("a", "root", "思想政治必修课", 4),
        node("a1", "a", "马克思主义", 4),
        node("a2", "a", "形势与政策", 0),
        node("b", "root", "体育", 2),
        node("c", "root", "已满足", 0),
      ];
      expect(
        deepestGapSubcategories(nodes, "root")
          .map((s) => s.name)
          .sort(),
      ).toEqual(["体育", "马克思主义"]);
    });

    it("根节点没有缺口或没有数字时返回空，不猜", () => {
      expect(deepestGapSubcategories([node("r", null, "x", 0)], "r")).toEqual(
        [],
      );
      expect(
        deepestGapSubcategories([node("r", null, "x", null)], "r"),
      ).toEqual([]);
    });

    it("子类候选来自学校挂靠的课程号，或课程目录里同名类别；已修课由调用方排除", () => {
      const catalog: Course[] = [
        {
          courseCode: "M1",
          name: "马原",
          credits: 3,
          category: "其他",
          sourceRefIds: [],
        },
        {
          courseCode: "M2",
          name: "毛概",
          credits: 2,
          category: "思想政治必修课",
          sourceRefIds: [],
        },
        {
          courseCode: "X1",
          name: "无关",
          credits: 2,
          category: "通识课",
          sourceRefIds: [],
        },
      ];
      const subs = [
        { nodeId: "a1", name: "思想政治必修课", remainingCredits: 5 },
      ];
      const result = subcategoryCandidates(
        subs,
        [{ nodeId: "a1", courseCode: "M1" }],
        catalog,
      ).map((course) => course.courseCode);
      expect(result.sort()).toEqual(["M1", "M2"]);
    });

    it("收窄后候选只来自子类，缺口用子类剩余学分，已修课被排除", () => {
      const plan = buildCategoryPlan(
        requirement(1, { category: "公共基础课" }),
        [],
        NONE,
        [],
      );
      const catalog: Course[] = [
        {
          courseCode: "M1",
          name: "马原",
          credits: 1,
          category: "公共基础课",
          sourceRefIds: [],
        },
        {
          courseCode: "M2",
          name: "毛概",
          credits: 2,
          category: "公共基础课",
          sourceRefIds: [],
        },
      ];
      const narrowed = narrowPlanToSubcategories(
        plan,
        [{ nodeId: "a1", name: "思想政治必修课", remainingCredits: 1 }],
        [catalog[0], catalog[1]],
        new Set(["M2"]),
        [],
        catalog,
      );
      expect(narrowed.countable.map((c) => c.courseCode)).toEqual(["M1"]);
      expect(narrowed.gapCredits).toBe(1);
      expect(narrowed.focusLabel).toBe("思想政治必修课");
    });

    it("子类没有可选课程时 countable 为空，不回退到大类", () => {
      const plan = buildCategoryPlan(
        requirement(2),
        [course("A", 2)],
        NONE,
        [],
      );
      const narrowed = narrowPlanToSubcategories(
        plan,
        [{ nodeId: "p", name: "体育", remainingCredits: 2 }],
        [],
        NONE,
        [],
        [course("A", 2)],
      );
      expect(narrowed.countable).toEqual([]);
      expect(narrowed.focusLabel).toBe("体育");
    });

    it("minCourses 为 2 时只给多门课组合", () => {
      const plan = buildCategoryPlan(
        requirement(4),
        [course("A", 2), course("B", 2), course("C", 4)],
        NONE,
        [],
      );
      const multi = suggestCompletions(plan, [], 4, { minCourses: 2 });
      expect(multi.length).toBeGreaterThan(0);
      expect(multi.every((s) => s.courseCodes.length >= 2)).toBe(true);
      expect(
        suggestCompletions(plan, [], 4, { minCourses: 2 }).some(
          (s) => s.courseCodes.length === 1,
        ),
      ).toBe(false);
    });
  });
});
