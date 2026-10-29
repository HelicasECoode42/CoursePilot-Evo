import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import type { AcademicRecord, AuditResult, Course } from "../contracts";
import { emptyPlanningDraft } from "../domain/question-flow";
import { usePlanningStore } from "../stores/planning";
import CreditPlanView from "./CreditPlanView.vue";

vi.mock("../api", () => ({
  api: {
    mode: "fixture",
    listCourses: vi.fn(),
  },
}));

const SNAPSHOT = "curriculum-2026";

const catalog: Course[] = [
  {
    courseCode: "E2",
    name: "编译原理",
    credits: 2,
    category: "专业选修课",
    sourceRefIds: [],
  },
  {
    courseCode: "E4",
    name: "机器学习导论",
    credits: 4,
    category: "专业选修课",
    sourceRefIds: [],
  },
  {
    courseCode: "E3",
    name: "深度学习",
    credits: 3,
    category: "专业选修课",
    sourceRefIds: [],
  },
  {
    courseCode: "E6",
    name: "计算机图形学",
    credits: 6,
    category: "专业选修课",
    sourceRefIds: [],
  },
  {
    courseCode: "N1",
    name: "操作系统",
    credits: null,
    category: "专业选修课",
    sourceRefIds: [],
  },
  {
    courseCode: "G1",
    name: "通识艺术",
    credits: 2,
    category: "通识课",
    sourceRefIds: [],
  },
  {
    courseCode: "DONE",
    name: "已修的课",
    credits: 3,
    category: "专业选修课",
    sourceRefIds: [],
  },
  {
    courseCode: "AI01",
    name: "人工智能导论",
    credits: 2,
    category: "专业选修课",
    sourceRefIds: [],
  },
];

const record: AcademicRecord = {
  academicRecordId: "rec-1",
  revision: 1,
  curriculumSnapshotId: SNAPSHOT,
  completedCourses: [
    {
      courseCode: "DONE",
      earnedCredits: 3,
      outcome: "PASSED",
      completedTerm: null,
    },
  ],
  transcriptComplete: true,
  sourceKind: "USER_IMPORT",
  createdAt: "2026-10-01T00:00:00Z",
};

const audit: AuditResult = {
  curriculumSnapshotId: SNAPSHOT,
  academicRecordId: "rec-1",
  recordRevision: 1,
  transcriptComplete: true,
  requirements: [
    {
      requirementId: "req-elective",
      category: "专业选修课",
      courseCodes: [],
      requiredCredits: 24,
      earnedCredits: 0,
      gapCredits: 6,
      state: "UNSATISFIED",
      sourceRefIds: [],
    },
    {
      requirementId: "req-unknown",
      category: "实践教学环节",
      courseCodes: [],
      requiredCredits: 4,
      earnedCredits: null,
      gapCredits: null,
      state: "UNKNOWN",
      sourceRefIds: [],
    },
  ],
  suggestedCourseCodes: [],
  unknowns: [
    {
      code: "UNMODELED_CURRICULUM_RULES",
      message:
        "本培养方案有 3 条规则系统未建模、不参与核验（原表位置：凑学分说明）。多修同时属于通识课的课程可认定为通识课学分。",
      field: null,
      retryable: false,
    },
    {
      code: "TRANSCRIPT_COMPLETENESS_UNKNOWN",
      message: "courseCodes=[CS101] outcome=UNKNOWN",
      field: null,
      retryable: false,
    },
  ],
};

async function mountView(
  options: {
    gap?: number;
    unknownGap?: boolean;
    interestTags?: string[];
    careerText?: string;
  } = {},
) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = usePlanningStore();
  store.$patch({
    sessionStatus: "ready",
    sessionId: "session-test",
    expiresAt: "2099-01-01T00:00:00Z",
    selectedCurriculumId: SNAPSHOT,
    records: [record],
    selectedRecordId: "rec-1",
    audit: options.unknownGap
      ? {
          ...audit,
          requirements: [
            {
              ...audit.requirements[0],
              gapCredits: null,
              earnedCredits: null,
              state: "UNKNOWN",
            },
            audit.requirements[1],
          ],
        }
      : options.gap
        ? {
            ...audit,
            requirements: [
              {
                ...audit.requirements[0],
                gapCredits: options.gap,
                earnedCredits: 24 - options.gap,
              },
              audit.requirements[1],
            ],
          }
        : audit,
    draft: {
      ...emptyPlanningDraft(),
      interestTags: options.interestTags ?? ["学习"],
      careerText: options.careerText ?? "",
    },
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/plan/credits", component: CreditPlanView },
      { path: "/plan/teachers", component: { template: "<p>教师</p>" } },
      { path: "/records", component: { template: "<p>资料</p>" } },
    ],
  });
  await router.push("/plan/credits");
  await router.isReady();
  const wrapper = mount(CreditPlanView, {
    global: { plugins: [pinia, router] },
  });
  await flushPromises();
  return { wrapper, router };
}

describe("凑学分选课页", () => {
  beforeEach(() => {
    vi.mocked(api.listCourses).mockReset();
    vi.mocked(api.listCourses).mockResolvedValue({
      items: catalog,
      nextCursor: null,
    });
  });

  it("shows the unmodeled cross-category rule notice verbatim", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain("系统没有算跨类别抵扣");
    expect(wrapper.text()).toContain("本培养方案有 3 条规则系统未建模");
    expect(wrapper.text()).toContain("凑学分只按单个类别计算");
    expect(wrapper.text()).toContain(
      "已修课程可能还未填全，暂时无法确定剩余要求。",
    );
    expect(wrapper.text()).not.toContain("courseCodes=[CS101]");
  });

  it("shows the category ledger line from the audit", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain("要求 24 · 已修 0 · 已选 0 · 还差 6 学分");
  });

  it("uses free-form career text from the planning store to rank candidates", async () => {
    const { wrapper } = await mountView({
      interestTags: [],
      careerText: "希望了解人工智能方向，优先补足学分。",
    });
    const firstCandidate = wrapper
      .findAll("details.credits-category")[0]!
      .find(".credits-list li")
      .text();
    expect(firstCandidate).toContain("AI01 · 人工智能导论");
    expect(wrapper.text()).toContain("按兴趣关键词与发展方向排序");
    expect(wrapper.text()).not.toContain("没有填写兴趣关键词");
  });

  it("keeps manual course selection available when the audit gap is unknown", async () => {
    const { wrapper } = await mountView({ unknownGap: true });
    const firstCandidate = wrapper
      .findAll("details.credits-category")[0]!
      .find('input[type="checkbox"]');
    const selectedCode = firstCandidate.element.parentElement?.textContent
      ?.trim()
      .split(" · ")[0];
    expect((firstCandidate.element as HTMLInputElement).disabled).toBe(false);
    await firstCandidate.setValue(true);
    expect(usePlanningStore().draft.selectedCourseCodes).toContain(
      selectedCode,
    );
    expect(wrapper.text()).toContain("还差无法确定");
  });

  it("keeps duplicate school category nodes as references and keeps candidate totals on Java audit", async () => {
    const { wrapper } = await mountView();
    usePlanningStore().$patch({
      schoolProgress: {
        receipt: {
          schoolProgressId: "school:fixture",
          contentHash: "a".repeat(64),
          importedAt: "2026-10-29T00:00:00Z",
          reused: false,
        },
        snapshot: {
          format: "coursepilot-shu-academic-progress",
          version: 1,
          capturedAt: "2026-10-29T00:00:00Z",
          source: "fictional fixture",
          nodes: [
            {
              nodeId: "school-parent",
              parentId: null,
              schoolNodeId: "98",
              leaf: false,
              name: "专业选修课",
              requiredCredits: 10,
              earnedCredits: 5,
              remainingCredits: 5,
            },
            {
              nodeId: "school-child",
              parentId: "school-parent",
              schoolNodeId: "54",
              leaf: true,
              name: "专业选修课",
              requiredCredits: 4,
              earnedCredits: 2,
              remainingCredits: 2,
            },
          ],
          courses: [],
        },
        academicRecord: record,
      },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("学校报告中有 2 个同名类别");
    expect(wrapper.text()).toContain("要求 24 · 已修 0 · 已选 0 · 还差 6 学分");
    expect(wrapper.text()).toContain("学分组合（还差 6 学分）");
  });

  it("says selections are included in the plan", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain("勾选的课程会加入本次规划");
  });

  it("updates the ledger live when a course is checked, and shows over-selection without blocking", async () => {
    const { wrapper } = await mountView();
    const box = (name: string) =>
      wrapper
        .findAll("label.credits-check")
        .find((l) => l.text().includes(name))!
        .get("input");
    await box("计算机图形学").setValue(true);
    await flushPromises();
    expect(wrapper.text()).toContain("要求 24 · 已修 0 · 已选 6 · 已凑满");
    await box("编译原理").setValue(true);
    await flushPromises();
    expect(wrapper.text()).toContain("已超出 2 学分");
    expect(wrapper.text()).toContain("已选 2 门");
    expect(wrapper.text()).toContain("已选学分：8");
    expect(usePlanningStore().draft.selectedCourseCodes).toEqual(["E6", "E2"]);
  });

  it("shows completion suggestions when a gap remains", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain("学分组合（还差 6 学分）");
    expect(wrapper.text()).toContain("编译原理 + 机器学习导论");
    expect(wrapper.text()).toContain("E2 + E4");
    const box = wrapper
      .findAll("label.credits-check")
      .find((l) => l.text().includes("计算机图形学"))!;
    await box.get("input").setValue(true);
    await flushPromises();
    expect(wrapper.text()).not.toContain("学分组合（还差 0 学分）");
  });

  it("does not count an UNKNOWN school status as passed or remove the course from the credit candidates", async () => {
    const { wrapper } = await mountView();
    const unknownRecord: AcademicRecord = {
      ...record,
      completedCourses: [
        ...record.completedCourses,
        {
          courseCode: "E2",
          earnedCredits: null,
          outcome: "UNKNOWN",
          completedTerm: null,
        },
      ],
    };
    usePlanningStore().$patch({ records: [unknownRecord] });
    await flushPromises();
    const courseLabel = wrapper
      .findAll("label.credits-check")
      .find((label) => label.text().includes("编译原理"));
    expect(courseLabel).toBeDefined();
    expect(wrapper.text()).toContain("要求 24 · 已修 0 · 已选 0 · 还差 6 学分");
  });

  it("adds a suggested group to the selection when asked", async () => {
    const { wrapper } = await mountView();
    const group = wrapper
      .findAll("li")
      .find((li) => li.text().includes("编译原理 + 机器学习导论"))!;
    await group.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("已选 2 门");
    expect(wrapper.text()).toContain("已凑满");
  });

  it("shows bounded combinations when the gap is large", async () => {
    vi.mocked(api.listCourses).mockResolvedValue({
      items: catalog.map((c) =>
        c.courseCode === "E6" ? { ...c, credits: 2 } : c,
      ),
      nextCursor: null,
    });
    const { wrapper } = await mountView({ gap: 21 });
    expect(wrapper.text()).toContain("还差 21 学分");
    expect(wrapper.text()).toContain("学分组合（还差 21 学分）");
    expect(wrapper.text()).not.toContain("个组合");
  });

  it("lists uncountable courses separately with the reason", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain("学分待确认，无法纳入凑分");
    expect(wrapper.text()).toContain("操作系统");
  });

  it("does not compute anything for a category with unknown gap", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain("这个类别的缺口无法确定，先补全学业记录");
    expect(wrapper.text()).toContain("实践教学环节");
  });

  it("excludes courses already completed in the record", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).not.toContain("已修的课");
  });

  it("labels the teacher link as not joining the plan", async () => {
    const { wrapper, router } = await mountView();
    expect(wrapper.text()).not.toContain("加入规划（去挑教师）");
    const link = wrapper
      .findAll("button")
      .find((b) => b.text().includes("不等于加入规划"))!;
    await link.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/plan/teachers");
  });
});
