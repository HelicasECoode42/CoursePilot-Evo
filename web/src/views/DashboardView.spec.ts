import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  AdviceChatAnswer,
  AuditResult,
  Course,
  ReviewNote,
} from "../contracts";
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

async function mountDashboard(
  withAudit = true,
  recordsReady = false,
  withPlanningResult = false,
) {
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
    recordsStatus: recordsReady ? "ready" : "idle",
    planningResult: withPlanningResult
      ? ({ decision: "UNABLE_TO_VERIFY" } as never)
      : null,
    schoolProgress: recordsReady
      ? ({
          receipt: {
            schoolProgressId: "progress-1",
            contentHash: "hash-1",
            importedAt: "2026-10-30T00:00:00Z",
            reused: true,
          },
          snapshot: { nodes: [], courses: [] },
          academicRecord: {},
        } as never)
      : null,
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

const openCourse = async (
  wrapper: Awaited<ReturnType<typeof mountDashboard>>["wrapper"],
  name: string,
) => {
  await wrapper.get('[data-view="courses"]').trigger("click");
  await flushPromises();
  await wrapper.get(".catalog-group summary").trigger("click");
  await wrapper
    .findAll("button.dash-course")
    .find((button) => button.text().includes(name))!
    .trigger("click");
};

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("个人控制台", () => {
  it("说明目标至少选择一项，其他偏好可留空", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("完整引导仍会逐步确认目标、偏好和时间");
  });

  it("学校报告已有缺口时先显示学校数值，保留本地核对的 UNKNOWN", async () => {
    const { wrapper, store } = await mountDashboard();
    store.$patch({
      schoolProgress: {
        receipt: { importedAt: "2026-10-30T00:00:00Z" },
        snapshot: {
          nodes: [
            {
              nodeId: "elective",
              parentId: null,
              schoolNodeId: "24",
              leaf: true,
              name: "专业选修课",
              requiredCredits: 24,
              earnedCredits: 18,
              remainingCredits: 6,
            },
            {
              nodeId: "unknown",
              parentId: null,
              schoolNodeId: "25",
              leaf: true,
              name: "通识课",
              requiredCredits: 12,
              earnedCredits: null,
              remainingCredits: null,
            },
          ],
          courses: [],
        },
      },
    });
    await flushPromises();
    const values = wrapper
      .findAll(".school-category__remaining dd")
      .map((node) => node.text());
    expect(values).toEqual(["6", "待确认"]);
    expect(store.audit?.requirements[0]?.gapCredits).toBeNull();
    expect(
      wrapper.get(".dashboard-panel > .record-help").attributes("open"),
    ).toBeUndefined();
  });

  it("评价读取失败后可以在原课程卡重试", async () => {
    const { wrapper } = await mountDashboard();
    const load = vi
      .spyOn(api, "searchReviews")
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce({ items: reviews, status: "OK" });
    await openCourse(wrapper, "有评价的课");
    await flushPromises();
    await wrapper.get(".dash-course__body button").trigger("click");
    await flushPromises();
    expect(load).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("评价 1 条");
  });

  it("评价状态未知且没有记录时不显示为 0 条", async () => {
    const { wrapper } = await mountDashboard();
    vi.spyOn(api, "searchReviews").mockResolvedValue({
      items: [],
      status: "UNKNOWN",
    });
    await openCourse(wrapper, "没有评价的课");
    await flushPromises();
    expect(wrapper.text()).toContain(
      "评价资料状态未确认，当前没有可展示的评价记录。",
    );
    expect(wrapper.text()).not.toContain("评价 0 条");
  });

  it("课程目录可以通过名称筛选，不要求学生记住课程号", async () => {
    const { wrapper } = await mountDashboard();
    await wrapper.get('[data-view="courses"]').trigger("click");
    await wrapper.get('input[type="search"]').setValue("没有评价");
    expect(
      wrapper.findAll("button.dash-course").map((button) => button.text()),
    ).toHaveLength(1);
    expect(wrapper.get("button.dash-course").text()).toContain("没有评价的课");
  });
  it("显示来源待核验，不美化成已核验", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("来源待核验");
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
    await openCourse(wrapper, "有评价的课");
    await flushPromises();
    expect(api.searchReviews).toHaveBeenCalledWith("C-WITH-REVIEWS", null);
  });

  it("没有评价记录时明说，不留空", async () => {
    const { wrapper } = await mountDashboard();
    await openCourse(wrapper, "没有评价的课");
    await flushPromises();
    expect(wrapper.text()).toContain("暂无评价记录");
  });

  it("评价只给条数和维度标签，不折算成分数或星级", async () => {
    const { wrapper } = await mountDashboard();
    await openCourse(wrapper, "有评价的课");
    await flushPromises();
    const text = wrapper.text();
    expect(text).toContain("评价 1 条");
    expect(text).toContain("工作量");
    expect(text).toContain("授课");
    expect(text).not.toMatch(/评分|均分|星|\d+(\.\d+)?\s*分\b/);
  });

  it("教师名标明是历史记录，不说成本学期谁上", async () => {
    const { wrapper } = await mountDashboard();
    await openCourse(wrapper, "有评价的课");
    await flushPromises();
    expect(wrapper.text()).toContain("历史记录，不代表下学期任课");
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
    await openCourse(wrapper, "有评价的课");
    await flushPromises();
    const text = wrapper.text();
    expect(text).not.toContain("已确认教过这门课的教师");
    expect(text).not.toContain("未绑定教师");
    // 但要把这件事说出来，不能静悄悄吞掉。
    expect(text).toContain("没有确认这位教师教过这门课");
  });

  it("本学期时间未知这件事写在课程区块里", async () => {
    const { wrapper } = await mountDashboard();
    await wrapper.get('[data-view="courses"]').trigger("click");
    expect(wrapper.text()).toContain("目录不代表下学期开课清单");
  });

  it("显示直接对话和完整引导入口", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("问一个关于方向或课程的问题");
    expect(wrapper.text()).toContain("继续完整需求引导");
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

  it("已有学业资料和规划结果时重开控制台不重复读记录或清除方案", async () => {
    const { wrapper, store } = await mountDashboard(true, true, true);
    const previousResult = store.planningResult;
    expect(store.loadRecords).not.toHaveBeenCalled();
    expect(store.loadSchoolProgress).not.toHaveBeenCalled();
    expect(store.planningResult).toBe(previousResult);
    expect(wrapper.text()).toContain("继续完整需求引导");
  });

  it("打字提问会发起对话并显示服务端回答，不跳转问卷", async () => {
    const { wrapper, store } = await mountDashboard();
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "可以先从基础课程开始。",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: { inputTokens: 2, outputTokens: 3, toolCalls: 1, elapsedMs: 10 },
    };
    const chat = vi.spyOn(api, "adviceChat").mockResolvedValue(answer);
    await wrapper.get("#dash-question").setValue("我这学期应该学什么？");
    await wrapper.get(".advice-chat__form").trigger("submit");
    await flushPromises();
    expect(chat).toHaveBeenCalledWith(
      expect.objectContaining({ message: "我这学期应该学什么？" }),
      expect.any(String),
      expect.any(AbortSignal),
    );
    expect(wrapper.text()).toContain(answer.reply);
    expect(store.draft.questionText).toBe("");
    expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe("/me");
  });

  it("对话失败后保留输入并使用原请求重试", async () => {
    const { wrapper } = await mountDashboard();
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "重试成功",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const chat = vi
      .spyOn(api, "adviceChat")
      .mockRejectedValueOnce(
        new ApiFailure("网络中断", "network", null, null, true),
      )
      .mockResolvedValueOnce(answer);
    await wrapper.get("#dash-question").setValue("保留这条问题");
    await wrapper.get(".advice-chat__form").trigger("submit");
    await flushPromises();
    expect(
      (wrapper.get("#dash-question").element as HTMLTextAreaElement).value,
    ).toBe("保留这条问题");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "重试本次请求")!
      .trigger("click");
    await flushPromises();
    expect(chat).toHaveBeenCalledTimes(2);
    expect(chat.mock.calls[0]?.[1]).toBe(chat.mock.calls[1]?.[1]);
    expect(wrapper.text()).toContain(answer.reply);
  });

  it("模型输出校验失败后展示重新生成动作并创建新幂等请求", async () => {
    const { wrapper } = await mountDashboard();
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "重新生成成功",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const chat = vi
      .spyOn(api, "adviceChat")
      .mockRejectedValueOnce(
        new ApiFailure(
          "旧的规划通用错误文案",
          "http",
          422,
          "MODEL_INVALID_OUTPUT",
        ),
      )
      .mockResolvedValueOnce(answer);
    await wrapper.get("#dash-question").setValue("请解释课程方向");
    await wrapper.get(".advice-chat__form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("这次回答未能生成");
    expect(wrapper.text()).not.toContain("没有写入任何方案");
    expect(
      (wrapper.get("#dash-question").element as HTMLTextAreaElement).value,
    ).toBe("请解释课程方向");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "重新生成回答")!
      .trigger("click");
    await flushPromises();
    expect(chat).toHaveBeenCalledTimes(2);
    expect(chat.mock.calls[0]?.[1]).not.toBe(chat.mock.calls[1]?.[1]);
    expect(wrapper.text()).toContain(answer.reply);
  });

  it("待选课程显示课程名，学校进度使用本地化日期时间", async () => {
    const { wrapper } = await mountDashboard();
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "建议了解这门课。",
      question: null,
      courses: [
        {
          courseCode: "C101",
          name: "数据分析导论",
          credits: 3,
          category: "专业选修课",
          reason: "相关",
          reviewNoteIds: [],
          reviews: [],
          reviewStatus: "NOT_QUERIED",
        },
      ],
      suggestions: [
        {
          suggestionId: "prefer-c101",
          kind: "PREFER_COURSE",
          label: "优先考虑数据分析导论",
          value: "C101",
        },
      ],
      schoolProgress: {
        capturedAt: "2026-10-30T08:00:00Z",
        source: "学校报告",
        nodes: [],
      },
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    vi.spyOn(api, "adviceChat").mockResolvedValue(answer);
    await wrapper.get("#dash-question").setValue("方向建议");
    await wrapper.get(".advice-chat__form").trigger("submit");
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "优先考虑：数据分析导论")!
      .trigger("click");
    await flushPromises();
    expect(wrapper.get("[aria-label='优先考虑课程']").text()).toContain(
      "数据分析导论",
    );
    expect(wrapper.get("[aria-label='优先考虑课程']").text()).toContain("C101");
    expect(wrapper.text()).not.toContain("2026-10-30T08:00:00Z");
  });

  it("对话不会自动填写动机和优先级", async () => {
    // 那几步是「一次一问、每个问题都要问到」的，自动填等于替他声明没说过的偏好。
    const { wrapper, store } = await mountDashboard();
    vi.spyOn(api, "adviceChat").mockResolvedValue({
      schemaVersion: "1.0",
      reply: "已收到。",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    });
    await wrapper.get("#dash-question").setValue("想做后端");
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("发送问题"))!
      .trigger("click");
    await flushPromises();
    expect(store.draft.motives).toEqual([]);
    expect(store.draft.priorityOrder).toEqual([]);
    expect(store.draft.prioritiesConfirmed).toBe(false);
  });

  it("空问题禁用发送并保留完整引导链接", async () => {
    const { wrapper } = await mountDashboard();
    expect(
      wrapper
        .get(".advice-chat__form button[type='submit']")
        .attributes("disabled"),
    ).toBeDefined();
    expect(
      wrapper.get(".plan-start a.button--primary").attributes("href"),
    ).toBe("/plan/questions/goals");
  });

  it("说明确认采用的聊天内容会进入本次规划草稿", async () => {
    const { wrapper } = await mountDashboard();
    expect(wrapper.text()).toContain("确认采用的兴趣或课程会进入本次规划草稿");
  });
});
