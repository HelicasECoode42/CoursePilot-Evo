import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import type { SnapshotSummary } from "../contracts";
import { emptyPlanningDraft } from "../domain/question-flow";
import { dayKeys, sectionKeys } from "../domain/schedule-grid";
import { usePlanningStore } from "../stores/planning";
import QuestionView from "./QuestionView.vue";

const curriculum: SnapshotSummary = {
  snapshotId: "curriculum-computer-science-2026",
  kind: "CURRICULUM",
  state: "PUBLISHED",
  sourceKind: "CURRICULUM_FILE",
  termId: null,
  createdAt: "2026-10-01T00:00:00Z",
  sourceValidation: "VERIFIED",
};

describe("student question page", () => {
  let router: ReturnType<typeof createRouter>;
  let store: ReturnType<typeof usePlanningStore>;
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(async () => {
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
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/plan/questions/:questionId", component: QuestionView },
      ],
    });
    await router.push("/plan/questions/goals");
    await router.isReady();
  });

  const next = async (wrapper: ReturnType<typeof mount>) => {
    await wrapper.get("button.button--primary").trigger("click");
    await flushPromises();
  };
  const back = async (wrapper: ReturnType<typeof mount>) => {
    await wrapper.get("button.button--quiet").trigger("click");
    await flushPromises();
  };
  const mountPage = () =>
    mount(
      { template: "<RouterView />" },
      { global: { plugins: [router, pinia] } },
    );

  it("shows every question in order for every student and preserves answers when returning", async () => {
    const wrapper = mountPage();
    expect(wrapper.findAll("h1")).toHaveLength(1);
    expect(wrapper.text()).toContain("下学期你最在意什么？");
    expect(wrapper.text()).toContain("留空即可跳过");
    expect(wrapper.find("#career-notes").exists()).toBe(false);

    await wrapper.get('input[value="LOW_WORKLOAD"]').setValue(true);
    await wrapper.get('input[value="CAREER"]').setValue(true);
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/preferences");
    await wrapper.get('input[value="LOWER_HOMEWORK"]').setValue(true);
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/interest");

    await wrapper.get("#career-notes").setValue("数据科学");
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/teacher");
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/schedule");
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/priorities");

    await back(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/schedule");
    await back(wrapper);
    await back(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/interest");
    expect(
      (wrapper.get("#career-notes").element as HTMLTextAreaElement).value,
    ).toBe("数据科学");
    await back(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/preferences");
    expect(
      (wrapper.get('input[value="LOWER_HOMEWORK"]').element as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(store.draft.motives).toEqual(["LOW_WORKLOAD", "CAREER"]);
  });

  it("uses next-term language for the planning flow", async () => {
    const wrapper = mountPage();
    expect(wrapper.text()).toContain("下学期你最在意什么？");
    expect(wrapper.text()).not.toContain("本学期目标");
    await next(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toContain(
      "请至少选择一个下学期的目标。",
    );

    await router.push("/plan/questions/schedule");
    await flushPromises();
    expect(wrapper.text()).toContain("下学期上课时间待确认");

    await router.push("/plan/questions/ready");
    await flushPromises();
    expect(wrapper.find(".summary-list").text()).toContain("下学期目标");
  });

  it("labels the session start as next-term enrollment planning", async () => {
    store.sessionStatus = "idle";
    const wrapper = mountPage();
    expect(wrapper.text()).toContain("下学期选课规划");
    expect(wrapper.text()).not.toContain("本学期课程规划");
  });

  it("describes a USER_IMPORT record accurately in simulation mode", async () => {
    const apiMode = Object.getOwnPropertyDescriptor(api, "mode");
    Object.defineProperty(api, "mode", {
      configurable: true,
      value: "simulation",
    });
    store.$patch({
      records: [
        {
          academicRecordId: "record:user-import",
          revision: 1,
          curriculumSnapshotId: curriculum.snapshotId,
          completedCourses: [],
          transcriptComplete: false,
          sourceKind: "USER_IMPORT",
          createdAt: "2026-10-29T00:00:00Z",
        },
      ],
      selectedRecordId: "record:user-import",
    });
    await router.push("/plan/questions/ready");
    const wrapper = mountPage();
    expect(wrapper.text()).toContain("已选择学业记录");
    expect(wrapper.text()).not.toContain("已选择虚构学业记录");
    if (apiMode) Object.defineProperty(api, "mode", apiMode);
  });

  it("paints time cells and keeps the chosen strength for the next cell", async () => {
    store.setMotives(["SCHEDULE"]);
    await router.push("/plan/questions/schedule");
    const wrapper = mountPage();

    const first = wrapper.get('[data-slot="1-3"]');
    expect(first.attributes("aria-label")).toBe("周一 第3节 未选择");
    expect(first.attributes("aria-pressed")).toBe("false");
    await first.trigger("click");
    await flushPromises();
    expect(store.draft.mustSlots).toEqual(["1-3"]);
    expect(wrapper.get('[data-slot="1-3"]').attributes("aria-label")).toBe(
      "周一 第3节 必须避开",
    );
    expect(wrapper.get('[data-slot="1-3"]').attributes("aria-pressed")).toBe(
      "true",
    );
    expect(wrapper.get('[data-slot="1-3"]').classes()).toContain("is-must");

    await wrapper.findAll(".seg button")[1].trigger("click");
    await wrapper.get('[data-slot="5-2"]').trigger("click");
    await flushPromises();
    expect(store.draft.preferSlots).toEqual(["5-2"]);
    expect(store.draft.mustSlots).toEqual(["1-3"]);
    expect(wrapper.get('button[aria-pressed="true"]').text()).toBe("尽量避开");

    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/priorities");
    await back(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/schedule");
    expect(store.draft.mustSlots).toEqual(["1-3"]);
    expect(store.draft.preferSlots).toEqual(["5-2"]);
    expect(wrapper.get('[data-slot="1-3"]').classes()).toContain("is-must");
    expect(wrapper.get('[data-slot="5-2"]').classes()).toContain("is-prefer");
  });

  it("toggles a whole weekday column and a whole section row", async () => {
    store.setMotives(["SCHEDULE"]);
    await router.push("/plan/questions/schedule");
    const wrapper = mountPage();

    await wrapper.get('button[aria-label="整列选择 周一"]').trigger("click");
    await flushPromises();
    expect(store.draft.mustSlots).toEqual(dayKeys(1));
    await wrapper.get('button[aria-label="整列选择 周一"]').trigger("click");
    await flushPromises();
    expect(store.draft.mustSlots).toEqual([]);

    await wrapper.get('button[aria-label="整行选择 第4节"]').trigger("click");
    await flushPromises();
    expect(store.draft.mustSlots).toEqual(sectionKeys(4));
  });

  it("moves a drag gesture by the start cell's state across every cell it touches", async () => {
    store.setMotives(["SCHEDULE"]);
    await router.push("/plan/questions/schedule");
    const wrapper = mountPage();

    await wrapper
      .get('[data-slot="2-3"]')
      .trigger("pointerdown", { button: 0 });
    await wrapper.get('[data-slot="2-4"]').trigger("pointerover");
    await wrapper.get('[data-slot="2-5"]').trigger("pointerover");
    document.dispatchEvent(new Event("pointerup"));
    await flushPromises();
    expect(store.draft.mustSlots).toEqual(["2-3", "2-4", "2-5"]);
  });

  it("erases instead of paints when the drag starts on an already painted cell", async () => {
    store.setMotives(["SCHEDULE"]);
    store.paintScheduleSlots(["3-3", "3-4"], "must", "paint");
    await router.push("/plan/questions/schedule");
    const wrapper = mountPage();

    await wrapper
      .get('[data-slot="3-3"]')
      .trigger("pointerdown", { button: 0 });
    await wrapper.get('[data-slot="3-4"]').trigger("pointerover");
    document.dispatchEvent(new Event("pointerup"));
    await flushPromises();
    expect(store.draft.mustSlots).toEqual([]);
  });

  it("allows an empty shared time page to be continued", async () => {
    store.setMotives(["SCHEDULE"]);
    await router.push("/plan/questions/schedule");
    const wrapper = mountPage();
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/priorities");
    expect(store.draft.mustReviewed).toBe(true);
    expect(store.draft.preferReviewed).toBe(true);
    expect(store.draft.mustSlots).toEqual([]);
    expect(store.draft.preferSlots).toEqual([]);
  });

  it("allows the class-preference page to be left empty", async () => {
    store.setMotives(["GPA"]);
    const wrapper = mountPage();
    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/preferences");
    expect(wrapper.findAll(".choice-card input:checked")).toHaveLength(0);

    await next(wrapper);
    expect(router.currentRoute.value.path).toBe("/plan/questions/interest");
    expect(store.draft.classPreferences).toEqual([]);
    expect(store.draft.classPreferencesReviewed).toBe(true);
  });

  it("hands teacher choice off to the comparison page instead of picking one inline", async () => {
    // 教师必须和具体课程一起选，而这一步没有课程资料，所以这里不提供选择，
    // 只给一个去比较页的入口。比较页在那里按课程列出教师与历史评价。
    store.setMotives(["SPECIFIC_TEACHER"]);
    await router.push("/plan/questions/teacher");
    const wrapper = mountPage();

    expect(router.currentRoute.value.path).toBe("/plan/questions/teacher");
    expect(wrapper.find("select").exists()).toBe(false);
    const handoff = wrapper.find('a[href="/plan/teachers"]');
    expect(handoff.exists()).toBe(true);
    expect(handoff.text()).toContain("比较课程与教师");
  });

  it("asks students to choose when multiple curricula exist without showing internal IDs", async () => {
    vi.spyOn(api, "getSchoolProgress").mockResolvedValue(null);
    const second = {
      ...curriculum,
      snapshotId: "opaque-snapshot-id-2026",
      createdAt: "2026-09-30T23:30:00Z",
    };
    store.$patch({
      curricula: [curriculum, second],
      selectedCurriculumId: null,
    });
    await router.replace("/plan/questions/curriculum");
    const wrapper = mountPage();

    expect(wrapper.findAll("#curriculum-select option")).toHaveLength(3);
    expect(wrapper.text()).not.toContain(second.snapshotId);
    expect(wrapper.text()).toContain("10月1日");
    await wrapper.get("#curriculum-select").setValue(second.snapshotId);
    await wrapper.get("button.button--primary").trigger("click");
    await flushPromises();

    expect(store.selectedCurriculumId).toBe(second.snapshotId);
    expect(router.currentRoute.value.path).toBe("/plan/questions/goals");
  });

  it("shows the confirmed priority, time, interest, and career details for review", async () => {
    store.$patch({
      draft: {
        ...emptyPlanningDraft(),
        motives: ["SCHEDULE", "INTEREST", "CAREER", "GPA"],
        priorityOrder: ["CAREER", "GPA", "SCHEDULE", "INTEREST"],
        prioritiesConfirmed: true,
        mustSlots: [...dayKeys(1), ...sectionKeys(2)],
        mustReviewed: true,
        preferSlots: [...dayKeys(2), ...dayKeys(5), ...sectionKeys(3)],
        preferReviewed: true,
        classPreferences: ["GRADING_FEEDBACK", "LOWER_HOMEWORK"],
        classPreferencesReviewed: true,
        interestTags: ["机器人", "数据可视化"],
        interestReviewed: true,
        careerText: "数据科学",
        careerReviewed: true,
      },
    });
    await router.replace("/plan/questions/ready");
    const wrapper = mountPage();

    const orderedGoals = wrapper
      .findAll(".summary-priorities li")
      .map((item) => item.text().replace(/\s+/g, " ").trim());
    expect(wrapper.get(".summary-priorities").element.tagName).toBe("OL");
    expect(orderedGoals).toEqual([
      "了解职业方向",
      "提高绩点",
      "安排合适的上课时间",
      "学习感兴趣的内容",
    ]);
    const summaryRows = new Map(
      wrapper
        .findAll(".summary-list > div")
        .map((row) => [
          row.get("dt").text(),
          row.get("dd").text().replace(/\s+/g, " ").trim(),
        ]),
    );
    expect(summaryRows.get("必须避开")).toBe("周一（整天）、每天第2节");
    expect(summaryRows.get("尽量避开")).toBe(
      "周二（整天）、周五（整天）、每天第3节",
    );
    expect(summaryRows.get("上课与考核偏好")).toBe(
      "给分反馈更友好、作业量少一些",
    );
    const summary = wrapper.find(".summary-list").text().replace(/\s+/g, " ");
    expect(summary).toContain("机器人、数据可视化");
    expect(summary).toContain("数据科学");
    expect(summary).not.toContain(curriculum.snapshotId);
    expect(wrapper.text()).toContain("尚未读取，真实规划暂不能继续");
    expect(wrapper.text()).toContain("为什么还缺学业记录？");
    expect(wrapper.find(".record-help summary").exists()).toBe(true);
    await wrapper.get(".record-help summary").trigger("click");
    expect(
      (wrapper.get(".record-help").element as HTMLDetailsElement).open,
    ).toBe(true);
    await wrapper.get("button.button--secondary").trigger("click");
    expect(store.planningHandoff).toBeNull();
    expect(wrapper.get(".missing-list").text()).toContain("学业记录");
    expect(wrapper.text()).not.toContain("已生成推荐");
  });

  it("explains an over-fragmented schedule with an actionable hint on the confirmation page", async () => {
    const scattered: string[] = [];
    for (let day = 1; day <= 7; day += 1) {
      for (let section = day; section <= day + 4; section += 1) {
        scattered.push(`${day}-${section}`);
      }
    }
    store.$patch({
      draft: {
        ...emptyPlanningDraft(),
        motives: ["SCHEDULE"],
        priorityOrder: ["SCHEDULE"],
        prioritiesConfirmed: true,
        classPreferencesReviewed: true,
        mustSlots: scattered,
        mustReviewed: true,
        preferReviewed: true,
      },
    });
    await router.replace("/plan/questions/ready");
    const wrapper = mountPage();

    await wrapper.get("button.button--secondary").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("上限 30");
    expect(wrapper.text()).toContain("返回修改时间安排");
  });

  it("requires an explicit priority confirmation before continuing", async () => {
    store.setMotives(["GPA", "CAREER"]);
    store.updateDraft("careerReviewed", true);
    await router.replace("/plan/questions/priorities");
    const wrapper = mountPage();

    expect(wrapper.text()).toContain("当前顺序只是初始排列");
    await wrapper.get("button.button--primary").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/plan/questions/priorities");
    expect(wrapper.get('[role="alert"]').text()).toContain("请先勾选确认框");

    await wrapper.get(".confirm-row input").setValue(true);
    await wrapper.get("button.button--primary").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/plan/questions/ready");
  });

  it("shows selected course and teacher on the confirmation page", async () => {
    store.$patch({
      teacherPickDisplayNames: { "CS101::T_ZHANG": "张老师" },
      draft: {
        ...emptyPlanningDraft(),
        teacherPicks: [
          { courseCode: "CS101", teacherKey: "T_ZHANG", mode: "MUST" },
        ],
      },
    });
    await router.replace("/plan/questions/ready");
    const wrapper = mountPage();
    expect(wrapper.text()).toContain("CS101 · 张老师 · 必须保留");
    expect(wrapper.text()).not.toContain("T_ZHANG");
    expect(wrapper.text()).not.toContain("尚未选择具体课程与教师");
  });

  it("always exposes school import and the selected curriculum on the ready page", async () => {
    store.$patch({
      curricula: [{ ...curriculum, displayName: "计算机科学与技术培养方案" }],
    });
    await router.replace("/plan/questions/ready");
    const wrapper = mountPage();
    expect(wrapper.get('[aria-label="规划所用资料"]').text()).toContain(
      "计算机科学与技术培养方案",
    );
    expect(wrapper.get('a[href="/records?import=school"]').text()).toBe(
      "导入我的学业进度",
    );
  });

  it("uses fill-or-blank wording on the confirmation page for every unanswered item", async () => {
    store.$patch({
      draft: {
        ...emptyPlanningDraft(),
        motives: ["GPA"],
        priorityOrder: ["GPA"],
        prioritiesConfirmed: true,
        classPreferencesReviewed: true,
        interestReviewed: true,
        careerReviewed: true,
        teacherHandoffAccepted: true,
        mustReviewed: true,
        preferReviewed: true,
      },
    });
    await router.replace("/plan/questions/ready");
    const wrapper = mountPage();

    const text = wrapper.text();
    expect(text).toContain("这一项留空了");
    expect(text).toContain("尚未选择具体课程与教师");
    for (const forbidden of [
      "未选择此目标",
      "未选择兴趣方向",
      "未选择职业方向",
      "未选择时间目标",
      "未选择相关目标",
      "未填写",
      "暂未填写",
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });
});
