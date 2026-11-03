import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { usePlanningStore } from "../stores/planning";
import { api } from "../api";
import RecordsView from "./RecordsView.vue";

describe("学业资料", () => {
  const showModal = Object.getOwnPropertyDescriptor(
    HTMLDialogElement.prototype,
    "showModal",
  );
  const close = Object.getOwnPropertyDescriptor(
    HTMLDialogElement.prototype,
    "close",
  );
  beforeEach(() => {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.setAttribute("open", "");
      },
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.removeAttribute("open");
        this.dispatchEvent(new Event("close"));
      },
    });
    vi.spyOn(api, "listCourses").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
  });
  afterEach(() => {
    if (showModal)
      Object.defineProperty(
        HTMLDialogElement.prototype,
        "showModal",
        showModal,
      );
    else
      delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>)
        .showModal;
    if (close)
      Object.defineProperty(HTMLDialogElement.prototype, "close", close);
    else
      delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
  });
  it("从资料确认页进入时直接打开学校导入弹窗", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({ sessionStatus: "ready", sessionId: "session-test" });
    const startSession = vi.spyOn(store, "startSession");
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
    await flushPromises();
    expect(
      wrapper.get('[aria-labelledby="school-import-title"]').text(),
    ).toContain("导入学校学业情况");
    expect(
      wrapper.get('[aria-labelledby="school-import-title"]').attributes("open"),
    ).toBeDefined();
    expect(startSession).not.toHaveBeenCalled();
  });
  it("新标签页直达学校导入时先准备会话，保留已有会话时不重建", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    const startSession = vi
      .spyOn(store, "startSession")
      .mockImplementation(async () => {
        store.$patch({
          sessionStatus: "ready",
          sessionId: "session-cold",
          selectedCurriculumId: "curr-test",
          recordsStatus: "ready",
        });
      });
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
    await flushPromises();
    expect(startSession).toHaveBeenCalledOnce();
    expect(store.sessionId).toBe("session-cold");
    expect(
      wrapper.get("#school-progress-file").attributes("disabled"),
    ).toBeUndefined();
    expect(
      wrapper.get('[aria-labelledby="school-import-title"]').attributes("open"),
    ).toBeDefined();
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
      auditStatus: "error",
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
    expect(
      wrapper.findAll(".school-category h3").map((el) => el.text()),
    ).toEqual(["公共基础课", "公共基础课"]);
    expect(wrapper.findAll(".school-category")).toHaveLength(2);
    expect(wrapper.text()).toMatch(/查看关联课程\s*·\s*1 门课程/);
    expect(wrapper.text()).toContain("虚构课程 · CP001");
    expect(wrapper.text()).toContain("状态待确认");
    expect(wrapper.text()).toContain("学校汇总不替代 Java 核验结果");
    expect(importSpy).toHaveBeenCalledOnce();
    expect(
      wrapper.get('[aria-labelledby="school-import-title"]').attributes("open"),
    ).toBeUndefined();
    expect(wrapper.get('[role="status"]').text()).toContain(
      "已保存 1 条课程记录和 2 个学校分类",
    );
    expect(wrapper.get('[role="status"]').text()).toContain(
      "学业核对未完成，请在下方重试",
    );
    expect(wrapper.get('[role="status"]').text()).not.toContain(
      "更新后的学业核对",
    );

    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("从学校教务导入"))!
      .trigger("click");
    importSpy.mockResolvedValue(false);
    await input.trigger("change");
    await flushPromises();
    expect(
      wrapper.get('[aria-labelledby="school-import-title"]').attributes("open"),
    ).toBeDefined();
    const dialog = wrapper.get('[aria-labelledby="school-import-title"]');
    expect(dialog.get('[role="status"]').text()).toContain("保存失败");
    expect(dialog.get('[role="status"]').text()).not.toContain("已保存");
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

describe("学业资料 · 学校报告后的课程名与核对摘要", () => {
  it("记录和核对摘要用学校导入的课程名，并能一键去勾选「记录已完整」", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      selectedCurriculumId: "curr-test",
      recordsStatus: "ready",
      selectedRecordId: "rec-school",
      records: [
        {
          academicRecordId: "rec-school",
          revision: 1,
          curriculumSnapshotId: "curr-test",
          completedCourses: [
            {
              courseCode: "2200R200",
              earnedCredits: null,
              outcome: "IN_PROGRESS",
              completedTerm: null,
            },
            {
              courseCode: "0200R012",
              earnedCredits: 2,
              outcome: "PASSED",
              completedTerm: "2025-2026:1",
            },
          ],
          transcriptComplete: false,
          sourceKind: "USER_IMPORT",
          createdAt: "2026-10-30T00:00:00Z",
        },
      ],
      schoolProgress: {
        receipt: {
          schoolProgressId: "progress-1",
          contentHash: "hash-1",
          importedAt: "2026-10-30T00:00:00Z",
          reused: false,
        },
        snapshot: {
          format: "coursepilot-shu-academic-progress",
          version: 1,
          capturedAt: "2026-10-30T00:00:00Z",
          source: "fixture",
          nodes: [
            {
              nodeId: "n1",
              parentId: null,
              schoolNodeId: null,
              leaf: true,
              name: "",
              requiredCredits: 2,
              earnedCredits: 2,
              remainingCredits: 0,
            },
          ],
          courses: [
            {
              nodeId: "n1",
              courseCode: "0200R012",
              name: "形势与政策",
              credits: 2,
              outcome: "PASSED",
              completedYear: null,
              completedTerm: null,
              grade: null,
              makeup: null,
              retake: null,
              suggestedYear: null,
              suggestedTerm: null,
            },
            {
              nodeId: "n1",
              courseCode: "2200R200",
              name: "",
              credits: null,
              outcome: "IN_PROGRESS",
              completedYear: null,
              completedTerm: null,
              grade: null,
              makeup: null,
              retake: null,
              suggestedYear: null,
              suggestedTerm: null,
            },
          ],
        },
        academicRecord: {},
      } as never,
      audit: {
        curriculumSnapshotId: "curr-test",
        academicRecordId: "rec-school",
        recordRevision: 1,
        transcriptComplete: false,
        requirements: [],
        suggestedCourseCodes: [],
        unknowns: [
          {
            code: "PENDING_COURSE",
            message: "课程 2200R200 在修或结果未知，通识 类别的缺口不能确定",
            field: "completedCourses",
            retryable: false,
          },
          {
            code: "COURSE_NOT_IN_CATALOG",
            message: "课程 9999X 不在课程库中，无法归类",
            field: "completedCourses",
            retryable: false,
          },
        ],
      } as never,
    });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "loadSchoolProgress").mockResolvedValue();
    vi.spyOn(api, "listCourses").mockResolvedValue({
      items: [],
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
      attachTo: document.body,
    });
    await flushPromises();
    expect(wrapper.text()).toContain("形势与政策 · 0200R012");
    expect(wrapper.text()).not.toContain("2200R200 在修");
    expect(wrapper.text()).toContain("本地核对暂无法给出结论");
    expect(wrapper.text()).toContain("9999X");
    const cta = wrapper
      .findAll("button")
      .find((button) => button.text() === "核对无误后勾选「记录已完整」");
    expect(cta).toBeDefined();
    await cta!.trigger("click");
    await flushPromises();
    const checkbox = wrapper.get<HTMLInputElement>("#transcript-complete");
    expect(checkbox.element.checked).toBe(false);
    expect(document.activeElement).toBe(checkbox.element);
    wrapper.unmount();
  });
});
