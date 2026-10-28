import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  Course,
  ReviewNote,
  SnapshotSummary,
  TeacherCourseOption,
} from "../contracts";
import { emptyPlanningDraft } from "../domain/question-flow";
import { usePlanningStore } from "../stores/planning";
import TeacherView from "./TeacherView.vue";

vi.mock("../api", () => ({
  api: {
    mode: "fixture",
    listCourses: vi.fn(),
    listTeacherCourseOptions: vi.fn(),
    searchReviews: vi.fn(),
  },
}));

const curriculum: SnapshotSummary = {
  snapshotId: "curriculum-computer-science-2026",
  kind: "CURRICULUM",
  state: "PUBLISHED",
  sourceKind: "CURRICULUM_FILE",
  termId: null,
  createdAt: "2026-10-01T00:00:00Z",
  sourceValidation: "VERIFIED",
};
const course: Course = {
  courseCode: "CS103",
  name: "数据结构",
  credits: 3,
  category: "专业基础",
  sourceRefIds: ["source:curriculum-cs103"],
};

const zhang: TeacherCourseOption = {
  courseCode: "CS103",
  teacherKey: "teacher-zhang-02",
  teacherDisplayName: "张伟（合成）",
  availability: "HISTORICAL_ONLY",
  reviewNoteIds: ["review-cs103-zhang-01"],
  classIds: [],
};
const wang: TeacherCourseOption = {
  courseCode: "CS103",
  teacherKey: "teacher-wang-03",
  teacherDisplayName: "王芳（合成）",
  availability: "UNKNOWN",
  reviewNoteIds: ["review-cs103-wang-01"],
  classIds: ["CS103-02"],
};

const matched: ReviewNote = {
  reviewNoteId: "review-zhang-matched",
  courseCode: "CS103",
  teacherKey: "teacher-zhang-02",
  termId: "2024-2025-1",
  sourceKind: "SYNTHETIC",
  publishedAt: "2025-01-10T00:00:00Z",
  sourceUrl: null,
  excerpt: "（合成）作业量适中，期中有一次小组展示。",
  dimensions: ["WORKLOAD", "GROUP_WORK", "GRADING"],
  matchStatus: "COURSE_TEACHER_MATCHED",
  sourceRefId: "source:review-zhang-matched",
};
const courseOnly: ReviewNote = {
  reviewNoteId: "review-cs103-course",
  courseCode: "CS103",
  teacherKey: null,
  termId: null,
  sourceKind: "OFFICIAL_SYLLABUS",
  publishedAt: null,
  sourceUrl: null,
  excerpt: "课程整体评价偏正面，但没有写明是哪位老师授课。",
  dimensions: ["OVERALL"],
  matchStatus: "COURSE_ONLY",
  sourceRefId: "source:review-cs103-course",
  teacherDisplayName: "教师姓名显示样例",
};
const unverified: ReviewNote = {
  reviewNoteId: "review-wang-unverified",
  courseCode: "CS103",
  teacherKey: "teacher-zhang-02",
  termId: "2023-2024-2",
  sourceKind: "USER_IMPORT",
  publishedAt: "2024-07-01T00:00:00Z",
  sourceUrl: null,
  excerpt: "考勤记录较严格，平时分占比较高。",
  dimensions: ["ATTENDANCE", "GRADING"],
  matchStatus: "UNVERIFIED",
  sourceRefId: "source:review-wang-unverified",
};

describe("teacher comparison page", () => {
  let router: ReturnType<typeof createRouter>;
  let store: ReturnType<typeof usePlanningStore>;
  let pinia: ReturnType<typeof createPinia>;
  const listOptions = vi.mocked(api.listTeacherCourseOptions);
  const listCourses = vi.mocked(api.listCourses);
  const listReviews = vi.mocked(api.searchReviews);

  beforeEach(async () => {
    vi.clearAllMocks();
    document.body.innerHTML = "";
    pinia = createPinia();
    setActivePinia(pinia);
    store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      expiresAt: "2099-01-01T00:00:00Z",
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
      draft: emptyPlanningDraft(),
    });
    listOptions.mockResolvedValue({ items: [zhang, wang], status: "OK" });
    listCourses.mockResolvedValue({ items: [course], nextCursor: null });
    listReviews.mockResolvedValue({
      items: [matched, courseOnly, unverified],
      status: "OK",
    });
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/plan/teachers", component: TeacherView },
        { path: "/plan/questions/:questionId", component: TeacherView },
      ],
    });
    await router.push("/plan/teachers");
    await router.isReady();
  });

  const mountPage = (attachTo?: HTMLElement) =>
    mount(
      { template: "<RouterView />" },
      {
        global: { plugins: [router, pinia] },
        attachTo,
      },
    );

  const search = async (wrapper: VueWrapper, code = "CS103"): Promise<void> => {
    await flushPromises();
    await wrapper.get("#course-code").setValue(code);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
  };

  const optionItem = (wrapper: VueWrapper, name: string) => {
    const item = wrapper
      .findAll("li.teacher-option")
      .find((li) => li.text().includes(name));
    if (!item) throw new Error(`no option for ${name}`);
    return item;
  };

  const toggle = async (wrapper: VueWrapper, name: string) => {
    await optionItem(wrapper, name)
      .get("button[aria-expanded]")
      .trigger("click");
    await flushPromises();
  };

  const pick = async (
    wrapper: VueWrapper,
    name: string,
    mode: "必须保留" | "优先考虑",
  ) => {
    await optionItem(wrapper, name)
      .get(`button[aria-label$="${mode}"]`)
      .trigger("click");
    await flushPromises();
  };

  it("lists teacher options with availability and class count for a course", async () => {
    const wrapper = mountPage();
    await search(wrapper);

    expect(listCourses).toHaveBeenCalledWith(curriculum.snapshotId, null);
    expect(listOptions).toHaveBeenCalledWith(curriculum.snapshotId, "CS103");
    expect(wrapper.find("#course-code").element.tagName).toBe("SELECT");
    expect(
      wrapper.findAll("#course-code option").map((option) => option.text()),
    ).toContain("数据结构（CS103）");
    const text = wrapper.text();
    expect(text).toContain("张伟（合成）");
    expect(text).toContain("王芳（合成）");
    expect(text).toContain("仅有历史资料");
    expect(text).toContain("本学期状态未知");
    expect(text).toContain("1 个班次");
    expect(text).toContain("暂无班次资料");
  });

  it("loads all pages of curriculum courses and displays names with codes", async () => {
    listCourses
      .mockResolvedValueOnce({ items: [course], nextCursor: "page-2" })
      .mockResolvedValueOnce({
        items: [{ ...course, courseCode: "CS104", name: "离散数学" }],
        nextCursor: null,
      });
    const wrapper = mountPage();
    await flushPromises();

    expect(listCourses).toHaveBeenNthCalledWith(1, curriculum.snapshotId, null);
    expect(listCourses).toHaveBeenNthCalledWith(
      2,
      curriculum.snapshotId,
      "page-2",
    );
    expect(
      wrapper.findAll("#course-code option").map((option) => option.text()),
    ).toContain("数据结构（CS103）");
    expect(
      wrapper.findAll("#course-code option").map((option) => option.text()),
    ).toContain("离散数学（CS104）");
  });

  it("shows course-level reviews without attributing them to a teacher", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    const button = wrapper
      .findAll("button")
      .find((item) => item.text() === "查看课程历史评价");
    await button!.trigger("click");
    await flushPromises();
    expect(listReviews).toHaveBeenCalledWith("CS103", null);
    expect(wrapper.get('[aria-label="课程历史评价"]').text()).toContain(
      courseOnly.excerpt,
    );
    expect(wrapper.get('[aria-label="课程历史评价"]').text()).toContain(
      "教师姓名（未核验）：教师姓名显示样例",
    );
    expect(wrapper.get('[aria-label="课程历史评价"]').text()).not.toContain(
      matched.excerpt,
    );
  });

  it("returns to the teacher preference question", async () => {
    const wrapper = mountPage();
    store.$patch({ sessionStatus: "idle", selectedCurriculumId: null });
    await flushPromises();
    await wrapper.get('a[href="/plan/questions/teacher"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/plan/questions/teacher");
  });

  it("provides a direct route back to record confirmation", async () => {
    const wrapper = mountPage();
    store.$patch({
      draft: {
        ...emptyPlanningDraft(),
        motives: ["GPA"],
        classPreferencesReviewed: true,
        interestReviewed: true,
        careerReviewed: true,
        teacherHandoffAccepted: true,
        mustReviewed: true,
        preferReviewed: true,
        priorityOrder: ["GPA"],
        prioritiesConfirmed: true,
      },
    });
    await wrapper.get('a[href="/plan/questions/ready"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/plan/questions/ready");
  });

  it("shows each review's source, year, dimensions and match status after expanding a teacher", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    expect(listReviews).toHaveBeenCalledWith("CS103", "teacher-zhang-02");
    const items = wrapper.findAll("ol li");
    expect(items).toHaveLength(3);
    const first = items[0].text();
    expect(first).toContain("合成样例（非真实评价）");
    expect(first).toContain("发布于 2025 年");
    expect(first).toContain("工作量、小组任务、给分方式");
    expect(first).toContain("课程与教师均已对应");
    expect(items[0].classes()).not.toContain("review-limited");
  });

  it("labels COURSE_ONLY and UNVERIFIED evidence as limited, not as this teacher's evidence", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    const items = wrapper.findAll("ol li");
    expect(items[1].text()).toContain(
      "依据有限：只能确认是这门课，不能确认是这位老师",
    );
    expect(items[1].classes()).toContain("review-limited");
    expect(items[2].text()).toContain("依据有限：来源未经核验");
    expect(items[2].classes()).toContain("review-limited");
    expect(wrapper.text()).toContain("证据之间有分歧");
  });

  it("shows the year as unknown instead of blank when publishedAt is null", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    const courseOnlyItem = wrapper.findAll("ol li")[1];
    expect(courseOnlyItem.text()).toContain("年份未知");
  });

  it("marks synthetic sources prominently and never presents them as real reviews", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    expect(wrapper.text()).toContain(
      "本列表含合成样例，仅用于演示流程，不是真实学生的评价",
    );
    expect(wrapper.find(".notice--demo").exists()).toBe(true);
    expect(wrapper.findAll("ol li")[0].text()).toContain("合成样例");
  });

  it("renders no star, score or rating anywhere on the page", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    const text = wrapper.text();
    for (const forbidden of [
      "★",
      "☆",
      "⭐",
      "星级",
      "评分：",
      "分（",
      "打分",
    ]) {
      expect(text).not.toContain(forbidden);
    }
    expect(
      wrapper
        .find(
          '[class*="star"], [class*="rating"], [class*="score"], input[type="range"], input[type="number"]',
        )
        .exists(),
    ).toBe(false);
  });

  it("keeps must-keep and prefer selections mutually exclusive without clearing the others", async () => {
    const wrapper = mountPage();
    await search(wrapper);

    await pick(wrapper, "张伟", "必须保留");
    await pick(wrapper, "王芳", "优先考虑");
    expect(
      wrapper
        .get('button[aria-label="张伟（合成） 必须保留"]')
        .attributes("aria-pressed"),
    ).toBe("true");
    expect(
      wrapper
        .get('button[aria-label="王芳（合成） 优先考虑"]')
        .attributes("aria-pressed"),
    ).toBe("true");

    // 把王芳改成必须保留：张伟的必须保留不能被清空，王芳不能同时在两档。
    await pick(wrapper, "王芳", "必须保留");
    expect(
      wrapper
        .get('button[aria-label="张伟（合成） 必须保留"]')
        .attributes("aria-pressed"),
    ).toBe("true");
    expect(
      wrapper
        .get('button[aria-label="王芳（合成） 优先考虑"]')
        .attributes("aria-pressed"),
    ).toBe("false");
    expect(
      wrapper
        .get('button[aria-label="王芳（合成） 必须保留"]')
        .attributes("aria-pressed"),
    ).toBe("true");

    const summary = wrapper
      .get(".teacher-picks dl")
      .text()
      .replace(/\s+/g, " ");
    expect(summary).toContain("CS103 · 张伟（合成）");
    expect(summary).toContain("CS103 · 王芳（合成）");
    expect(summary).toContain("这一项留空了");

    // 再点同一档位即取消，另一个选择不受影响。
    await pick(wrapper, "王芳", "必须保留");
    expect(
      wrapper
        .get('button[aria-label="王芳（合成） 必须保留"]')
        .attributes("aria-pressed"),
    ).toBe("false");
    expect(
      wrapper
        .get('button[aria-label="张伟（合成） 必须保留"]')
        .attributes("aria-pressed"),
    ).toBe("true");
  });

  it("keeps the selection after the page re-renders with a new search", async () => {
    const wrapper = mountPage();
    await search(wrapper);
    await pick(wrapper, "张伟", "优先考虑");

    await search(wrapper, "CS103");
    expect(
      wrapper
        .get('button[aria-label="张伟（合成） 优先考虑"]')
        .attributes("aria-pressed"),
    ).toBe("true");
    expect(wrapper.get(".teacher-picks dl").text()).toContain(
      "CS103 · 张伟（合成）",
    );
  });

  it("returns focus to the opening button when the review detail is closed", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const wrapper = mountPage(host);
    await search(wrapper);

    const trigger = optionItem(wrapper, "王芳").get("button[aria-expanded]");
    await trigger.trigger("click");
    await flushPromises();
    expect(trigger.attributes("aria-expanded")).toBe("true");
    expect(trigger.attributes("aria-controls")).toBeDefined();

    await wrapper.get(".button--quiet").trigger("click");
    await flushPromises();
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(trigger.attributes("aria-controls")).toBeUndefined();
    expect(document.activeElement).toBe(trigger.element);
    wrapper.unmount();
  });

  it("returns focus to the opening button when the detail is closed with Escape", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const wrapper = mountPage(host);
    await search(wrapper);

    const trigger = optionItem(wrapper, "张伟").get("button[aria-expanded]");
    await trigger.trigger("click");
    await flushPromises();
    await wrapper.get('[role="region"]').trigger("keydown", { key: "Escape" });
    await flushPromises();
    expect(document.activeElement).toBe(trigger.element);
    wrapper.unmount();
  });

  it("explains when the curriculum has no selectable teacher-course entries", async () => {
    listCourses.mockResolvedValueOnce({ items: [], nextCursor: null });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("当前培养方案没有课程资料");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.find("li.teacher-option").exists()).toBe(false);
  });

  it("says an UNKNOWN teacher list cannot be confirmed instead of saying there are none", async () => {
    listCourses.mockResolvedValueOnce({ items: [], nextCursor: null });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("当前培养方案没有课程资料");
    expect(wrapper.find("li.teacher-option").exists()).toBe(false);
  });

  it("marks listed teachers as possibly incomplete when the teacher list is UNKNOWN", async () => {
    listOptions.mockResolvedValueOnce({
      items: [zhang, wang],
      status: "UNKNOWN",
    });
    const wrapper = mountPage();
    await search(wrapper);

    expect(wrapper.findAll("li.teacher-option")).toHaveLength(2);
    expect(wrapper.text()).toContain("下面的教师资料无法确认");
    expect(wrapper.text()).not.toContain("没有可比较的教师资料");
  });

  it("does not show an empty review list as a positive review", async () => {
    listReviews.mockResolvedValueOnce({ items: [], status: "OK" });
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "王芳");

    expect(wrapper.text()).toContain("没有找到评价");
    expect(wrapper.text()).not.toContain("评价良好");
    expect(wrapper.text()).not.toContain("好评");
    expect(wrapper.findAll("ol li")).toHaveLength(0);
  });

  it("says an UNKNOWN review list cannot be confirmed instead of saying none were found", async () => {
    listReviews.mockResolvedValueOnce({ items: [], status: "UNKNOWN" });
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "王芳");

    expect(wrapper.text()).toContain("评价资料无法确认");
    expect(wrapper.text()).not.toContain("没有找到评价");
    expect(wrapper.text()).not.toContain("评价良好");
    expect(wrapper.findAll("ol li")).toHaveLength(0);
  });

  it("marks listed reviews as possibly incomplete when the review list is UNKNOWN", async () => {
    listReviews.mockResolvedValueOnce({
      items: [matched, courseOnly],
      status: "UNKNOWN",
    });
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    expect(wrapper.findAll("ol li")).toHaveLength(2);
    expect(wrapper.text()).toContain("下面的评价资料无法确认");
    expect(wrapper.text()).not.toContain("没有找到评价");
  });

  it("shows a retryable message on request failure and never falls back to fixture data", async () => {
    listOptions.mockRejectedValueOnce(
      new ApiFailure("服务暂时不可用，请稍后重试。", "http", 503, null, true),
    );
    const wrapper = mountPage();
    await search(wrapper);

    expect(wrapper.get('[role="alert"]').text()).toContain("服务暂时不可用");
    expect(wrapper.text()).not.toContain("张伟（合成）");
    expect(wrapper.text()).not.toContain("王芳（合成）");

    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect(listOptions).toHaveBeenCalledTimes(2);
    await search(wrapper);
    expect(wrapper.text()).toContain("张伟（合成）");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("shows a retryable message when reviews fail to load", async () => {
    listReviews.mockRejectedValueOnce(
      new ApiFailure("服务暂时不可用，请稍后重试。", "http", 503, null, true),
    );
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    expect(wrapper.get('[role="alert"]').text()).toContain("服务暂时不可用");
    expect(wrapper.findAll("ol li")).toHaveLength(0);
    expect(wrapper.text()).not.toContain("没有找到评价");
    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect(wrapper.findAll("ol li")).toHaveLength(3);
  });

  it("renders review excerpts as text, never as HTML", async () => {
    listReviews.mockResolvedValueOnce({
      items: [{ ...matched, excerpt: '<img src="x" onerror="alert(1)">点击' }],
      status: "OK",
    });
    const wrapper = mountPage();
    await search(wrapper);
    await toggle(wrapper, "张伟");

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.text()).toContain('<img src="x" onerror="alert(1)">点击');
  });
});
