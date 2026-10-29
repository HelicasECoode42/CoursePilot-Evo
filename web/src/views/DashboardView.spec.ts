import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import type { AuditResult, Course, ReviewNote } from "../contracts";
import { usePlanningStore } from "../stores/planning";
import DashboardView from "./DashboardView.vue";

const curriculum = {
  snapshotId: "curr-real",
  kind: "CURRICULUM" as const,
  state: "PUBLISHED" as const,
  sourceKind: "CURRICULUM_FILE" as const,
  termId: null,
  createdAt: "2026-10-29T00:00:00Z",
  sourceValidation: "UNVERIFIED" as const,
  displayName: "计算机科学与技术（示例）",
};

const courses: Course[] = [
  {
    courseCode: "C-WITH-REVIEWS",
    name: "有评价的课",
    credits: 4,
    category: "学科基础课",
    sourceRefIds: ["ref-1"],
    suggestedTerm: "大二上",
  },
  {
    courseCode: "C-NO-REVIEWS",
    name: "没有评价的课",
    credits: 2,
    category: "学科基础课",
    sourceRefIds: ["ref-2"],
    suggestedTerm: null,
  },
];

const reviews: ReviewNote[] = [
  {
    reviewNoteId: "note-1",
    courseCode: "C-WITH-REVIEWS",
    teacherKey: "t-1",
    teacherDisplayName: "示例教师",
    termId: "2025-WINTER",
    sourceKind: "USER_IMPORT",
    publishedAt: null,
    sourceUrl: null,
    sourceRefId: "ref-note-1",
    excerpt: "作业偏多但讲得清楚。",
    dimensions: ["WORKLOAD", "TEACHING"],
    matchStatus: "COURSE_TEACHER_MATCHED",
  },
];

/** 一条 UNKNOWN、一条 UNSATISFIED：UNKNOWN 不许被渲染成已满足。 */
const audit: AuditResult = {
  curriculumSnapshotId: "curr-real",
  academicRecordId: "rec-1",
  recordRevision: 1,
  transcriptComplete: false,
  requirements: [
    {
      requirementId: "req-unknown",
      category: "专业选修课",
      courseCodes: [],
      requiredCredits: null,
      earnedCredits: null,
      gapCredits: null,
      state: "UNKNOWN",
      sourceRefIds: ["ref-a"],
    },
    {
      requirementId: "req-gap",
      category: "学科基础课",
      courseCodes: [],
      requiredCredits: 19,
      earnedCredits: 6,
      gapCredits: 13,
      state: "UNSATISFIED",
      sourceRefIds: ["ref-b"],
    },
  ],
  suggestedCourseCodes: [],
  unknowns: [],
};

async function mountDashboard(withAudit = true) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = usePlanningStore();
  store.$patch({
    sessionStatus: "ready",
    sessionId: "session-test",
    curricula: [curriculum],
    selectedCurriculumId: "curr-real",
    selectedRecordId: "rec-1",
    audit: withAudit ? audit : null,
  });
  vi.spyOn(store, "startSession").mockResolvedValue();
  vi.spyOn(store, "loadRecords").mockResolvedValue();
  vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
  vi.spyOn(store, "runAudit").mockResolvedValue(undefined as never);
  vi.spyOn(api, "listCourses").mockResolvedValue({
    items: courses,
    nextCursor: null,
  });
  vi.spyOn(api, "searchReviews").mockImplementation(async (courseCode) => ({
    items: reviews.filter((note) => note.courseCode === courseCode),
    status: "OK" as const,
  }));
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/me", component: DashboardView },
      { path: "/setup", component: { template: "<p>setup</p>" } },
      { path: "/records", component: { template: "<p>records</p>" } },
      {
        path: "/plan/questions/:questionId",
        component: { template: "<p>q</p>" },
      },
    ],
  });
  await router.push("/me");
  await router.isReady();
  const wrapper = mount(DashboardView, {
    global: { plugins: [pinia, router] },
    attachTo: document.body,
  });
  await flushPromises();
  await flushPromises();
  return { wrapper, store };
}

const courseButton = (
  wrapper: Awaited<ReturnType<typeof mountDashboard>>["wrapper"],
  name: string,
) =>
  wrapper.findAll("button.dash-course").find((b) => b.text().includes(name))!;

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("个人控制台", () => {
  it("原样显示来源核验状态，不美化成已核验", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("UNVERIFIED");
    expect(wrapper.text()).not.toContain("已核验");
  });

  it("把无法确认的要求和还差的要求分开，不并进已满足", async () => {
    const { wrapper } = await mountDashboard();
    const text = wrapper.text();
    expect(text).toContain("无法确认的要求");
    expect(text).toContain("还差的要求");
    // UNKNOWN 那条的缺口必须显示「无法确认」，不能变成 0 或「已凑满」。
    const unknownLine = wrapper
      .findAll("li")
      .map((li) => li.text())
      .find((line) => line.startsWith("专业选修课"));
    expect(unknownLine).toContain("无法确认");
  });

  it("展开才去查评价，没点开之前不发请求", async () => {
    const { wrapper } = await mountDashboard();
    expect(api.searchReviews).not.toHaveBeenCalled();
    await courseButton(wrapper, "有评价的课").trigger("click");
    await flushPromises();
    expect(api.searchReviews).toHaveBeenCalledWith("C-WITH-REVIEWS", null);
  });

  it("没有评价记录时明说，不留空", async () => {
    const { wrapper } = await mountDashboard();
    await courseButton(wrapper, "没有评价的课").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("暂无评价记录");
  });

  it("评价只给条数和维度标签，不折算成分数或星级", async () => {
    const { wrapper } = await mountDashboard();
    await courseButton(wrapper, "有评价的课").trigger("click");
    await flushPromises();
    const text = wrapper.text();
    expect(text).toContain("评价 1 条");
    expect(text).toContain("工作量");
    expect(text).toContain("讲课");
    expect(text).not.toMatch(/评分|均分|星|\d+(\.\d+)?\s*分\b/);
  });

  it("教师名标明是历史记录，不说成本学期谁上", async () => {
    const { wrapper } = await mountDashboard();
    await courseButton(wrapper, "有评价的课").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("历史记录，不代表本学期谁上");
  });

  it("COURSE_ONLY 的评价即使带教师名也不列进教师名单", async () => {
    // 实测：真实数据里一门课 10 条评价全是 COURSE_ONLY，却都带 teacherDisplayName。
    // 把它们列成「教过这门课的教师」就是把评价硬塞给某位教师。
    const { wrapper } = await mountDashboard();
    // mountDashboard 里已经装过一次 spy，这里要在它之后覆盖，否则不生效。
    vi.spyOn(api, "searchReviews").mockResolvedValue({
      items: [
        {
          ...reviews[0],
          reviewNoteId: "note-unbound",
          teacherKey: null,
          teacherDisplayName: "未绑定教师",
          matchStatus: "COURSE_ONLY",
        },
      ],
      status: "OK",
    });
    await courseButton(wrapper, "有评价的课").trigger("click");
    await flushPromises();
    const text = wrapper.text();
    expect(text).not.toContain("已确认教过这门课的教师");
    expect(text).not.toContain("未绑定教师");
    // 但要把这件事说出来，不能静悄悄吞掉。
    expect(text).toContain("没有确认这位教师教过这门课");
  });

  it("本学期时间未知这件事写在课程区块里", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("要等选课开放才公开");
  });

  it("「我学了什么」和方向两个回答都说明不经过模型", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("不经过模型");
  });

  it("方向要点开才去取，并且原样显示演示数据标记", async () => {
    const { wrapper } = await mountDashboard();
    const listCareerDirections = vi
      .spyOn(api, "listCareerDirections")
      .mockResolvedValue([
        {
          directionId: "DIR_X",
          subjectTags: ["计算机"],
          title: "后端与业务系统开发",
          description: "【演示数据】偏向服务端开发。",
          courseCodes: ["CS101"],
          sourceRefIds: ["ref-c"],
        },
      ]);
    expect(listCareerDirections).not.toHaveBeenCalled();
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("有哪些方向"))!
      .trigger("click");
    await flushPromises();
    expect(listCareerDirections).toHaveBeenCalled();
    expect(wrapper.text()).toContain("【演示数据】");
  });

  it("没有核对结果时指路去核对，而不是显示空的缺口", async () => {
    const { wrapper } = await mountDashboard(false);
    expect(wrapper.text()).toContain("还没有学业核对结果");
  });

  it("开始选课进的是现有的规划流程", async () => {
    const { wrapper } = await mountDashboard();
    const targets = wrapper.findAll("a").map((a) => a.attributes("href"));
    expect(targets).toContain("/plan/questions/goals");
  });
});
