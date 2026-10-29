import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { usePlanningStore } from "../stores/planning";
import { api } from "../api";
import RecordsView from "./RecordsView.vue";

describe("学业资料", () => {
  it("从资料确认页进入时直接打开学校导入弹窗", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({ sessionStatus: "ready", sessionId: "session-test" });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/records", component: RecordsView }],
    });
    await router.push("/records?import=school");
    await router.isReady();
    const wrapper = mount(RecordsView, {
      global: { plugins: [pinia, router] },
    });
    expect(
      wrapper.get('[aria-labelledby="school-import-title"]').text(),
    ).toContain("导入学校学业情况");
  });
  it("持久化教务导入后展示保留父子关系的学校类别", async () => {
    const apiMode = Object.getOwnPropertyDescriptor(api, "mode");
    Object.defineProperty(api, "mode", {
      configurable: true,
      value: "simulation",
    });
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      selectedCurriculumId: "curr-test",
    });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
    const snapshot = {
      format: "coursepilot-shu-academic-progress" as const,
      version: 1 as const,
      capturedAt: "2026-10-29T00:00:00Z",
      source: "fictional fixture",
      nodes: [
        {
          nodeId: "parent",
          parentId: null,
          schoolNodeId: "98",
          leaf: false,
          name: "公共基础课",
          requiredCredits: 12,
          earnedCredits: 6,
          remainingCredits: 6,
        },
        {
          nodeId: "child",
          parentId: "parent",
          schoolNodeId: "54",
          leaf: true,
          name: "公共基础课",
          requiredCredits: 4,
          earnedCredits: 2,
          remainingCredits: 2,
        },
      ],
      courses: [
        {
          nodeId: "child",
          courseCode: "CP001",
          name: "虚构课程",
          credits: 2,
          outcome: "UNKNOWN" as const,
          completedYear: null,
          completedTerm: null,
          grade: null,
          makeup: null,
          retake: null,
          suggestedYear: null,
          suggestedTerm: null,
        },
      ],
    };
    store.$patch({
      schoolProgress: {
        receipt: {
          schoolProgressId: "school:demo",
          contentHash: "a".repeat(64),
          importedAt: "2026-10-29T00:00:00Z",
          reused: false,
        },
        snapshot,
        academicRecord: {
          academicRecordId: "record:demo",
          revision: 1,
          curriculumSnapshotId: "curr-test",
          completedCourses: [],
          transcriptComplete: false,
          sourceKind: "USER_IMPORT",
          createdAt: "2026-10-29T00:00:00Z",
        },
      },
    });
    const importSpy = vi
      .spyOn(store, "importSchoolProgress")
      .mockResolvedValue(true);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/records", component: RecordsView }],
    });
    await router.push("/records");
    await router.isReady();
    const wrapper = mount(RecordsView, {
      global: { plugins: [pinia, router] },
    });
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("从学校教务导入"))!
      .trigger("click");
    const input = wrapper.get("#school-progress-file");
    const file = new File(["{}"], "progress.json", {
      type: "application/json",
    });
    file.text = async () =>
      JSON.stringify({
        ...snapshot,
      });
    Object.defineProperty(input.element, "files", {
      value: [file],
      configurable: true,
    });
    await input.trigger("change");
    await flushPromises();
    expect(wrapper.text()).toContain("公共基础课（学校类别 98）");
    expect(wrapper.text()).toContain("公共基础课（学校类别 54）");
    expect(wrapper.text()).toContain("学校汇总不替代 Java 核验结果");
    expect(importSpy).toHaveBeenCalledOnce();
    if (apiMode) Object.defineProperty(api, "mode", apiMode);
  });
  it("按年级生成待确认课程并填入学分，未修课程可以修改", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      selectedCurriculumId: "curr-test",
      recordsStatus: "ready",
    });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
    vi.spyOn(api, "listCourses").mockResolvedValue({
      items: [
        {
          courseCode: "CS101",
          name: "基础课",
          credits: 4,
          category: "公共基础课",
          suggestedTerm: "第一学年 第1学期",
          sourceRefIds: ["source:1"],
        },
      ],
      nextCursor: null,
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/records", component: RecordsView }],
    });
    await router.push("/records");
    await router.isReady();
    const wrapper = mount(RecordsView, {
      global: { plugins: [pinia, router] },
    });
    await flushPromises();
    await wrapper.get("#study-year").setValue("3");
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("按年级生成"))!
      .trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("已生成 1 门待确认基础课程");
    expect((wrapper.get("#credits-0").element as HTMLInputElement).value).toBe(
      "4",
    );
    await wrapper.get("#outcome-0").setValue("FAILED");
    expect((wrapper.get("#credits-0").element as HTMLInputElement).value).toBe(
      "",
    );
    vi.restoreAllMocks();
  });
  it("用易读的记录名称展示核对结果并返回资料确认", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      selectedCurriculumId: "curr-test",
      recordsStatus: "ready",
      selectedRecordId: "session:internal-id",
      records: [
        {
          academicRecordId: "session:internal-id",
          revision: 1,
          curriculumSnapshotId: "curr-test",
          completedCourses: [
            {
              courseCode: "CS101",
              earnedCredits: 3,
              outcome: "PASSED",
              completedTerm: null,
            },
          ],
          transcriptComplete: false,
          sourceKind: "SYNTHETIC",
          createdAt: "2026-01-01T00:00:00Z",
        },
      ],
    });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
    vi.spyOn(store, "runAudit").mockImplementation(async () => {
      store.$patch({
        auditStatus: "ready",
        audit: {
          curriculumSnapshotId: "curr-test",
          academicRecordId: "session:internal-id",
          recordRevision: 1,
          transcriptComplete: false,
          requirements: [
            {
              requirementId: "req-1",
              courseCodes: ["CS101"],
              requiredCredits: 4,
              earnedCredits: 3,
              gapCredits: null,
              state: "UNKNOWN",
              sourceRefIds: ["source:demo"],
            },
          ],
          suggestedCourseCodes: [],
          unknowns: [
            {
              code: "TRANSCRIPT_COMPLETENESS_UNKNOWN",
              message: "技术说明",
              field: null,
              retryable: false,
            },
          ],
        },
      });
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/records", component: RecordsView },
        {
          path: "/plan/questions/ready",
          component: { template: "<p>资料确认</p>" },
        },
      ],
    });
    await router.push("/records");
    await router.isReady();
    const wrapper = mount(RecordsView, {
      global: { plugins: [pinia, router] },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("学业记录 1 · 1 门课程");
    expect(wrapper.text()).not.toContain("session:internal-id");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "修改已填写课程")!
      .trigger("click");
    expect(wrapper.get(".course-picker__selected").text()).toContain("CS101");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "核对培养要求")!
      .trigger("click");
    expect(wrapper.text()).toContain("核对结果");
    expect(wrapper.text()).toContain("暂时无法确定剩余要求");
    expect(wrapper.text()).not.toContain("req-1");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "返回资料确认")!
      .trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/plan/questions/ready");
  });
});

describe("按年级生成的空结果", () => {
  it("没选培养方案时说明原因，而不是点了没反应", async () => {
    // 原先这里直接 return，按钮点下去什么都不发生，看着像功能坏了。
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      // 补录表单只在「记录已读取且一条都没有」时出现。
      recordsStatus: "ready",
      records: [],
    });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/records", component: RecordsView }],
    });
    await router.push("/records");
    await router.isReady();
    const wrapper = mount(RecordsView, {
      global: { plugins: [pinia, router] },
    });
    // 没选年级时按钮是禁用的，所以先选年级，才能走到「没选培养方案」这条分支。
    await wrapper.get("#study-year").setValue("2");
    const button = wrapper
      .findAll("button")
      .find((b) => b.text().includes("按年级生成"))!;
    await button.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("还没有选定培养方案");
  });
});
