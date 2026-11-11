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
    listSessionRecords: vi.fn(),
    getSchoolProgress: vi.fn(),
    summarizeOfferings: vi.fn(),
  },
}));

const SNAPSHOT = "curriculum-2026";
const OFFERING_SNAPSHOT = "offering-2026";

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
    recordsStatus: "ready",
    schoolProgressStatus: "ready",
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
  const loadRecordsSpy = vi.spyOn(store, "loadRecords");
  await flushPromises();
  return { wrapper, router, store, loadRecordsSpy };
}

describe("凑学分选课页", () => {
  beforeEach(() => {
    vi.mocked(api.listCourses).mockReset();
    vi.mocked(api.listSessionRecords).mockReset();
    vi.mocked(api.getSchoolProgress).mockReset();
    vi.mocked(api.listCourses).mockResolvedValue({
      items: catalog,
      nextCursor: null,
    });
    vi.mocked(api.summarizeOfferings).mockReset();
  });

  it("shows the unmodeled cross-category rule notice verbatim", async () => {
    const { wrapper } = await mountView();
    expect(wrapper.text()).toContain(
      "学分按学校教务导入的学业情况计算；跨类别抵扣以教务认定为准。",
    );
    expect(wrapper.text()).not.toContain("凑分只按单个类别");
    expect(wrapper.text()).not.toContain("原表位置");
    expect(wrapper.text()).toContain(
      "已修课程可能还未填全，暂时无法确定剩余要求。",
    );
    expect(wrapper.text()).not.toContain("courseCodes=[CS101]");
  });

  it("shows the category ledger line from the audit", async () => {
    const { wrapper, store, loadRecordsSpy } = await mountView();
    expect(wrapper.text()).toContain("要求 24 · 已修 0 · 已选 0 · 还差 6 学分");
    expect(store.audit?.requirements).toHaveLength(2);
    expect(loadRecordsSpy).not.toHaveBeenCalled();
  });

  it("prepares a new session on direct entry and links to import when no record exists", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({ sessionStatus: "idle", recordsStatus: "idle" });
    const startSession = vi
      .spyOn(store, "startSession")
      .mockImplementation(async () => {
        store.$patch({
          sessionStatus: "ready",
          sessionId: "session-cold",
          selectedCurriculumId: SNAPSHOT,
        });
      });
    const loadRecords = vi.mocked(api.listSessionRecords).mockResolvedValue({
      items: [],
    });
    vi.mocked(api.getSchoolProgress).mockResolvedValue(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/plan/credits", component: CreditPlanView },
        { path: "/records", component: { template: "<p>资料页</p>" } },
      ],
    });
    await router.push("/plan/credits");
    await router.isReady();
    const wrapper = mount(CreditPlanView, {
      global: { plugins: [pinia, router] },
    });
    await flushPromises();
    expect(startSession).toHaveBeenCalledOnce();
    expect(loadRecords).toHaveBeenCalledOnce();
    expect(store.audit).toBeNull();
    expect(wrapper.text()).toContain("当前会话还没有学业记录");
    expect(wrapper.text()).toContain("去学业资料导入");
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
    attachOfferingSnapshot();
    markEveryOfferingKnown();
    await flushPromises();
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

  it("shows school category progress with an action to run local audit when audit is missing", async () => {
    const { wrapper } = await mountView();
    usePlanningStore().$patch({ audit: null });
    usePlanningStore().$patch({
      schoolProgress: {
        receipt: {
          schoolProgressId: "school:fixture",
          contentHash: "b".repeat(64),
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
              nodeId: "school-elective",
              parentId: null,
              schoolNodeId: "S1",
              leaf: true,
              name: "专业选修课",
              requiredCredits: 10,
              earnedCredits: 4,
              remainingCredits: 6,
            },
          ],
          courses: [],
        },
        academicRecord: record,
      },
    });
    await flushPromises();
    const report = wrapper.find("details.school-report-reference");
    expect(report.text()).toContain("学校报告进度");
    expect(report.text()).toContain("还差");
    expect(report.text()).toContain("去学业资料运行本地核对");
    expect(wrapper.text()).toContain("学校报告进度 · 原始类别与学分");
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

  it("switches category while retaining selected courses and removes a selection from the summary", async () => {
    const { wrapper } = await mountView();
    const elective = wrapper
      .findAll("label.credits-check")
      .find((label) => label.text().includes("编译原理"))!;
    await elective.get("input").setValue(true);
    const categoryButton = wrapper
      .findAll("nav[aria-label='课程类别'] button")
      .find((button) => button.text().includes("实践教学环节"))!;
    await categoryButton.trigger("click");
    expect(wrapper.findAll("label.credits-check").length).toBe(0);
    expect(wrapper.get("section[aria-label='已选课程']").text()).toContain(
      "E2 · 编译原理 · 2 学分",
    );
    expect(usePlanningStore().draft.selectedCourseCodes).toEqual(["E2"]);
    await wrapper
      .get("section[aria-label='已选课程']")
      .find("button")
      .trigger("click");
    expect(usePlanningStore().draft.selectedCourseCodes).toEqual([]);
    expect(wrapper.get("section[aria-label='已选课程']").text()).toContain(
      "已选 0 门",
    );
  });

  it("counts a legacy duplicate selection only once", async () => {
    const { wrapper } = await mountView();
    usePlanningStore().updateDraft("selectedCourseCodes", ["E2", "E2"]);
    await flushPromises();
    const cart = wrapper.get("section[aria-label='已选课程']");
    expect(cart.text()).toContain("已选 1 门");
    expect(cart.text()).toContain("已选学分：2");
  });

  it("shows completion suggestions when a gap remains", async () => {
    const { wrapper } = await mountView();
    attachOfferingSnapshot();
    markEveryOfferingKnown();
    await flushPromises();
    expect(wrapper.text()).toContain("学分组合（还差 6 学分）");
    expect(wrapper.text()).toContain("编译原理 + 机器学习导论");
    expect(wrapper.text()).toContain("E2 · E4");
    const box = wrapper
      .findAll("label.credits-check")
      .find((l) => l.text().includes("计算机图形学"))!;
    await box.get("input").setValue(true);
    await flushPromises();
    expect(wrapper.text()).not.toContain("学分组合（还差 0 学分）");
  });

  it("keeps courses with unknown offering status out of current-term combinations", async () => {
    const { wrapper } = await mountView();
    attachOfferingSnapshot();
    vi.mocked(api.summarizeOfferings).mockResolvedValue({
      items: [{ courseCode: "E2", sectionCount: 1, teacherTexts: [] }],
      unknownCourseCodes: ["E4", "E3", "E6", "AI01"],
      status: "OK",
    });
    await flushPromises();

    expect(wrapper.text()).toContain("开课情况无法确认");
    expect(wrapper.text()).not.toContain("学分组合（还差 6 学分）");
    expect(wrapper.text()).not.toContain("编译原理 + 机器学习导论");
    expect(
      wrapper
        .findAll("label.credits-check")
        .some((label) => label.text().includes("机器学习导论")),
    ).toBe(true);
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

  it("excludes an in-progress course from selectable credit candidates without counting its credits", async () => {
    const { wrapper } = await mountView();
    usePlanningStore().$patch({
      records: [
        {
          ...record,
          completedCourses: [
            {
              courseCode: "E2",
              earnedCredits: 2,
              outcome: "IN_PROGRESS",
              completedTerm: null,
            },
          ],
        },
      ],
    });
    await flushPromises();
    const courseLabel = wrapper
      .findAll("label.credits-check")
      .find((label) => label.text().includes("编译原理"));
    expect(courseLabel).toBeUndefined();
    expect(wrapper.text()).toContain("要求 24 · 已修 0 · 已选 0 · 还差 6 学分");
  });

  it("adds a suggested group to the selection when asked", async () => {
    const { wrapper } = await mountView();
    attachOfferingSnapshot();
    markEveryOfferingKnown();
    await flushPromises();
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
    attachOfferingSnapshot();
    markEveryOfferingKnown();
    await flushPromises();
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
    await wrapper
      .findAll("nav[aria-label='课程类别'] button")
      .find((button) => button.text().includes("实践教学环节"))!
      .trigger("click");
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

  /** 只在 mount 之后挂上学校报告（测试数据为虚构）。 */
  function attachSchool(nodes: Array<Record<string, unknown>>) {
    usePlanningStore().$patch({
      schoolProgress: {
        receipt: {
          schoolProgressId: "school:fixture",
          contentHash: "c".repeat(64),
          importedAt: "2026-10-29T00:00:00Z",
          reused: false,
        },
        snapshot: {
          format: "coursepilot-shu-academic-progress",
          version: 1,
          capturedAt: "2026-10-29T00:00:00Z",
          source: "fictional fixture",
          nodes: nodes as never,
          courses: [],
        },
        academicRecord: record,
      },
    });
  }

  function attachOfferingSnapshot() {
    usePlanningStore().$patch({
      offeringSnapshots: [
        {
          snapshotId: OFFERING_SNAPSHOT,
          kind: "OFFERING",
          state: "PUBLISHED",
          sourceKind: "SYNTHETIC",
          termId: "2026-27-1",
          createdAt: "2026-10-01T00:00:00Z",
          sourceValidation: "SYNTHETIC",
        },
      ],
      selectedOfferingSnapshotId: OFFERING_SNAPSHOT,
    });
  }

  function markEveryOfferingKnown() {
    vi.mocked(api.summarizeOfferings).mockResolvedValue({
      items: catalog.map((course) => ({
        courseCode: course.courseCode,
        sectionCount: 1,
        teacherTexts: [],
      })),
      unknownCourseCodes: [],
      status: "OK",
    });
  }

  it("uses the school report gap when the Java gap is unknown and keeps candidates selectable", async () => {
    const { wrapper } = await mountView({ unknownGap: true });
    attachSchool([
      {
        nodeId: "elective",
        parentId: null,
        schoolNodeId: "S1",
        leaf: true,
        name: "专业选修课",
        requiredCredits: 24,
        earnedCredits: 18,
        remainingCredits: 6,
      },
    ]);
    await flushPromises();
    expect(wrapper.text()).toContain(
      "按学校报告还差 6 学分；本地核对无法确认。",
    );
    expect(wrapper.text()).toContain("学校报告 要求 24 · 已获 18 · 还差 6");
    expect(wrapper.text()).toContain("本地核对缺口无法确定");
    expect(wrapper.text()).not.toContain("已修 0");
    const firstCandidate = wrapper
      .findAll("details.credits-category")[0]!
      .find('input[type="checkbox"]');
    expect((firstCandidate.element as HTMLInputElement).disabled).toBe(false);
  });

  it("groups repeated unknown audit items into the shared summary instead of listing each one", async () => {
    const { wrapper, store } = await mountView();
    const notInCatalog = [1, 2, 3].map((n) => ({
      code: "COURSE_NOT_IN_CATALOG",
      field: null,
      message: `课程 SYN090${n} 不在课程库中，无法归入培养要求。`,
      retryable: false,
    }));
    store.$patch({
      audit: {
        ...audit,
        unknowns: [...audit.unknowns, ...notInCatalog],
      },
    });
    await flushPromises();
    expect(wrapper.find(".local-audit-summary").exists()).toBe(true);
    expect(wrapper.text()).toContain("3 门课无法归入本专业培养要求");
    expect(wrapper.findAll(".credits-issue")).toHaveLength(0);
  });

  it("marks candidates by whether the selected offering snapshot has sections, offered first", async () => {
    const { wrapper } = await mountView({ interestTags: [] });
    vi.mocked(api.summarizeOfferings).mockImplementation(
      async (_c, _s, codes) => {
        const counts: Record<string, number> = { E2: 1, E3: 2 };
        const failed = codes.includes("E6");
        return {
          status: failed ? "UNKNOWN" : "OK",
          items: codes
            .filter((code) => code !== "E6")
            .map((code) => ({
              courseCode: code,
              sectionCount: counts[code] ?? 0,
              teacherTexts: [],
            })),
          unknownCourseCodes: failed ? ["E6"] : [],
        };
      },
    );
    attachOfferingSnapshot();
    await flushPromises();
    const rows = wrapper
      .findAll("details.credits-category")[0]!
      .findAll("label.credits-check")
      .map((label) => label.text());
    expect(rows.map((text) => text.split(" · ")[0])).toEqual([
      "E2",
      "E3",
      "E6",
    ]);
    expect(rows[0]).toContain("本学期开 1 个班");
    expect(rows[1]).toContain("本学期开 2 个班");
    expect(rows[2]).toContain("开课情况无法确认");
    // 未开的课不进可选列表，收在「本学期未开」折叠区里。
    const notOffered = wrapper.find("details.credits-not-offered");
    expect(notOffered.exists()).toBe(true);
    expect(notOffered.attributes("open")).toBeUndefined();
    expect(notOffered.text()).toContain("本学期未开（2 门");
    expect(notOffered.text()).toContain("AI01");
    expect(notOffered.text()).toContain("E4");
    expect(wrapper.text()).toContain("本学期开课情况暂无法确认");
  });

  it("says offering is unknown rather than not offered when the query fails", async () => {
    const { wrapper } = await mountView({ interestTags: [] });
    vi.mocked(api.summarizeOfferings).mockRejectedValue(new Error("network"));
    attachOfferingSnapshot();
    await flushPromises();
    const rows = wrapper
      .findAll("details.credits-category")[0]!
      .findAll("label.credits-check");
    expect(rows[0]!.text()).toContain("开课情况无法确认");
    expect(rows[0]!.text()).not.toContain("本学期未开");
    expect(wrapper.text()).toContain("本学期开课情况暂无法确认");
  });

  describe("学校导入与子类下钻（合成数据）", () => {
    type SchoolNodeFixture = {
      nodeId: string;
      parentId: string | null;
      schoolNodeId: string | null;
      leaf: boolean;
      name: string;
      requiredCredits: number | null;
      earnedCredits: number | null;
      remainingCredits: number | null;
    };
    type SchoolCourseFixture = {
      nodeId: string;
      courseCode: string;
      name: string;
      credits: number | null;
      outcome: "PASSED" | "IN_PROGRESS" | "NOT_TAKEN" | "UNKNOWN";
    };

    function attachSchoolTree(
      nodes: SchoolNodeFixture[],
      courses: SchoolCourseFixture[] = [],
    ) {
      usePlanningStore().$patch({
        schoolProgress: {
          receipt: {
            schoolProgressId: "school:fixture",
            contentHash: "d".repeat(64),
            importedAt: "2026-10-29T00:00:00Z",
            reused: false,
          },
          snapshot: {
            format: "coursepilot-shu-academic-progress",
            version: 1,
            capturedAt: "2026-10-29T00:00:00Z",
            source: "fictional fixture",
            nodes: nodes as never,
            courses: courses.map((course) => ({
              ...course,
              completedYear: null,
              completedTerm: null,
              grade: null,
              makeup: null,
              retake: null,
              suggestedYear: null,
              suggestedTerm: null,
            })) as never,
          },
          academicRecord: record,
        },
      });
    }

    const root: SchoolNodeFixture = {
      nodeId: "root",
      parentId: null,
      schoolNodeId: "R",
      leaf: false,
      name: "专业选修课",
      requiredCredits: 24,
      earnedCredits: 18,
      remainingCredits: 6,
    };

    it("排除学校导入里已通过和在读的课，不只看本次核对的学业记录", async () => {
      const { wrapper } = await mountView();
      attachSchoolTree(
        [{ ...root, leaf: true }],
        [
          {
            nodeId: "root",
            courseCode: "E3",
            name: "深度学习",
            credits: 3,
            outcome: "IN_PROGRESS",
          },
          {
            nodeId: "root",
            courseCode: "E4",
            name: "机器学习导论",
            credits: 4,
            outcome: "PASSED",
          },
        ],
      );
      await flushPromises();
      const labels = wrapper
        .findAll("label.credits-check")
        .map((label) => label.text());
      expect(labels.some((text) => text.includes("E3"))).toBe(false);
      expect(labels.some((text) => text.includes("E4"))).toBe(false);
      expect(labels.some((text) => text.includes("E2"))).toBe(true);
    });

    it("缺口下钻到最细的有缺口子类，候选只来自这些子类", async () => {
      const { wrapper } = await mountView();
      attachSchoolTree(
        [
          root,
          {
            nodeId: "ai",
            parentId: "root",
            schoolNodeId: "A",
            leaf: true,
            name: "人工智能方向",
            requiredCredits: 4,
            earnedCredits: 0,
            remainingCredits: 4,
          },
          {
            nodeId: "sys",
            parentId: "root",
            schoolNodeId: "B",
            leaf: true,
            name: "系统方向",
            requiredCredits: 2,
            earnedCredits: 0,
            remainingCredits: 2,
          },
          {
            nodeId: "done",
            parentId: "root",
            schoolNodeId: "C",
            leaf: true,
            name: "已满足方向",
            requiredCredits: 2,
            earnedCredits: 2,
            remainingCredits: 0,
          },
        ],
        [
          {
            nodeId: "ai",
            courseCode: "AI01",
            name: "人工智能导论",
            credits: 2,
            outcome: "NOT_TAKEN",
          },
          {
            nodeId: "sys",
            courseCode: "E2",
            name: "编译原理",
            credits: 2,
            outcome: "NOT_TAKEN",
          },
        ],
      );
      await flushPromises();
      const codes = wrapper
        .findAll("label.credits-check")
        .map((label) => label.text().split(" · ")[0]);
      expect(codes.sort()).toEqual(["AI01", "E2"]);
      expect(wrapper.text()).toContain(
        "缺口已下钻到学校报告的小类「人工智能方向、系统方向」",
      );
    });

    it("子类在课程库里没有可选课程时说明，不回退到整个大类", async () => {
      const { wrapper } = await mountView();
      attachSchoolTree([
        root,
        {
          nodeId: "pe",
          parentId: "root",
          schoolNodeId: "P",
          leaf: true,
          name: "体育方向",
          requiredCredits: 2,
          earnedCredits: 0,
          remainingCredits: 2,
        },
      ]);
      await flushPromises();
      expect(wrapper.findAll("label.credits-check")).toHaveLength(0);
      expect(wrapper.text()).toContain(
        "这个小类（体育方向）在课程库里没有可选课程。",
      );
    });

    it("只有单门课的组合时不显示学分组合区块", async () => {
      const { wrapper } = await mountView();
      attachSchoolTree(
        [
          root,
          {
            nodeId: "pe",
            parentId: "root",
            schoolNodeId: "P",
            leaf: true,
            name: "计算机图形学方向",
            requiredCredits: 6,
            earnedCredits: 0,
            remainingCredits: 6,
          },
        ],
        [
          {
            nodeId: "pe",
            courseCode: "E6",
            name: "计算机图形学",
            credits: 6,
            outcome: "NOT_TAKEN",
          },
        ],
      );
      await flushPromises();
      expect(wrapper.text()).toContain("计算机图形学");
      expect(wrapper.text()).not.toContain("学分组合");
    });
  });
});
