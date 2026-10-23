import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  CourseOffering,
  Meeting,
  PlanItem,
  PlanningAnswer,
  PlanValidation,
  Recommendation,
  SessionOfferingList,
  SessionPlanReplacement,
} from "../contracts";
import { usePlanningStore } from "../stores/planning";
import ResultView from "./ResultView.vue";

const PLAN_ID = "plan-test-1";
const WEEKS = Array.from({ length: 16 }, (_, index) => index + 1);
const MON_1_2: Meeting = {
  dayOfWeek: 1,
  sectionStart: 1,
  sectionEnd: 2,
  weeks: WEEKS,
};
const THU_7_8: Meeting = {
  dayOfWeek: 4,
  sectionStart: 7,
  sectionEnd: 8,
  weeks: WEEKS,
};

/** 测试用班次：只关心时间和解析状态，其他字段给中性值。 */
function offering(
  courseCode: string,
  classId: string,
  meetings: Meeting[],
  parseStatus: CourseOffering["parseStatus"] = "PARSED",
): CourseOffering {
  return {
    courseCode,
    classId,
    teacherKey: null,
    teacherText: "测试教师（合成）",
    credits: 3,
    capacity: 60,
    meetingTextRaw: meetings.length > 0 ? "测试时间" : "时间待定",
    meetings,
    parseStatus,
    sourceRefId: `source:${classId}`,
  };
}

const DEFAULT_OFFERINGS: Record<string, CourseOffering[]> = {
  CS102: [offering("CS102", "CS102-01", [MON_1_2])],
  CS103: [
    offering("CS103", "CS103-01", [MON_1_2]),
    offering("CS103", "CS103-02", [THU_7_8]),
    offering("CS103", "CS103-03", [], "UNPARSED"),
  ],
};

function validation(partial: Partial<PlanValidation>): PlanValidation {
  return {
    verifierResultId: "verifier-test",
    verdict: "VALID",
    scope: "REAL_TIMETABLE",
    curriculumSnapshotId: "curriculum-test",
    offeringSnapshotId: "offering-test",
    recordRevision: 1,
    violations: [],
    unknownChecks: [],
    performedChecks: [],
    sourceRefIds: [],
    ...partial,
  };
}

/** 初始方案：CS102 已定班次，CS103 尚未选班次；初始判决只是课程层通过。 */
const INITIAL_ITEMS: PlanItem[] = [
  { courseCode: "CS102", teacherKey: "teacher-li-01", classId: "CS102-01" },
  { courseCode: "CS103", teacherKey: null, classId: null },
];

function recommendation(): Recommendation {
  return {
    planId: PLAN_ID,
    items: INITIAL_ITEMS,
    explanation: "测试说明",
    reviewNoteIds: [],
    verification: validation({ scope: "COURSE_ONLY" }),
  };
}

function answer(): PlanningAnswer {
  return {
    taskId: "task-test",
    traceId: "trace-test",
    decision: "RECOMMENDATIONS",
    academicAudit: {
      curriculumSnapshotId: "curriculum-test",
      academicRecordId: "record-test",
      recordRevision: 1,
      transcriptComplete: true,
      requirements: [],
      suggestedCourseCodes: [],
      unknowns: [],
    },
    recommendations: [recommendation()],
    clarification: null,
    unknowns: [],
    usage: {
      inputTokens: null,
      outputTokens: null,
      toolCalls: 0,
      elapsedMs: 0,
    },
  };
}

function replacement(verification: PlanValidation): SessionPlanReplacement {
  return {
    previousPlanId: PLAN_ID,
    planId: `${PLAN_ID}-CS103-02`,
    items: [
      { courseCode: "CS102", teacherKey: "teacher-li-01", classId: "CS102-01" },
      {
        courseCode: "CS103",
        teacherKey: "teacher-wang-03",
        classId: "CS103-02",
      },
    ],
    hardConstraints: [],
    verification,
  };
}

function stubOfferings(overrides: Record<string, CourseOffering[]> = {}) {
  return vi
    .spyOn(api, "searchSessionOfferings")
    .mockImplementation(async (previousPlanId, courseCode) => {
      const items =
        overrides[courseCode] ?? DEFAULT_OFFERINGS[courseCode] ?? [];
      const list: SessionOfferingList = {
        previousPlanId,
        courseCode,
        items: structuredClone(items),
      };
      return list;
    });
}

describe("result page course search and replacement", () => {
  let router: ReturnType<typeof createRouter>;
  let store: ReturnType<typeof usePlanningStore>;
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(async () => {
    pinia = createPinia();
    setActivePinia(pinia);
    store = usePlanningStore();
    store.$patch({ sessionStatus: "ready", planningResult: answer() });
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/plan/result", component: ResultView },
        {
          path: "/plan/questions/:questionId",
          component: { render: () => null },
        },
      ],
    });
    await router.push("/plan/result");
    await router.isReady();
  });

  const mountPage = () =>
    mount(ResultView, { global: { plugins: [router, pinia] } });

  const buttonByText = (wrapper: ReturnType<typeof mountPage>, text: string) =>
    wrapper.findAll("button").find((item) => item.text() === text);

  const openAndSearch = async (
    wrapper: ReturnType<typeof mountPage>,
    course: string,
  ) => {
    await wrapper.get("#result-search-entry-0").trigger("click");
    await wrapper.get("#result-search-course-0").setValue(course);
    await wrapper.get("form.search-form").trigger("submit");
    await flushPromises();
  };

  const rowOf = (wrapper: ReturnType<typeof mountPage>, classId: string) =>
    wrapper
      .findAll("li.offering-row")
      .find((row) => row.text().includes(classId));

  const selectClass = async (
    wrapper: ReturnType<typeof mountPage>,
    classId: string,
  ) => {
    await rowOf(wrapper, classId)?.get("button").trigger("click");
    await flushPromises();
  };

  const recheck = async (wrapper: ReturnType<typeof mountPage>) => {
    await buttonByText(wrapper, "重新核验这份方案")?.trigger("click");
    await flushPromises();
  };

  it("shows conflicting, selectable, and unparsed offerings as three distinct states", async () => {
    stubOfferings();
    const wrapper = mountPage();
    expect(
      wrapper.get("#result-search-entry-0").attributes("aria-expanded"),
    ).toBe("false");

    await openAndSearch(wrapper, "CS103");
    expect(
      wrapper.get("#result-search-entry-0").attributes("aria-expanded"),
    ).toBe("true");

    const conflict = rowOf(wrapper, "CS103-01");
    expect(conflict?.get(".offering-tag--conflict").text()).toBe("有冲突");
    expect(
      conflict?.get(".offering-tag--conflict").attributes("disabled"),
    ).toBeDefined();
    expect(conflict?.text()).not.toContain("选这个班次");

    const clear = rowOf(wrapper, "CS103-02");
    expect(clear?.get("button").text()).toBe("选这个班次");
    expect(clear?.get("button").attributes("disabled")).toBeUndefined();
    expect(clear?.find(".offering-tag").exists()).toBe(false);

    const unknown = rowOf(wrapper, "CS103-03");
    expect(unknown?.get(".offering-tag--unknown").text()).toBe("无法确认");
    expect(
      unknown?.get(".offering-tag--unknown").attributes("disabled"),
    ).toBeDefined();
    expect(unknown?.text()).not.toContain("选这个班次");
  });

  it("does not let conflicting or unknown offerings be selected", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    await rowOf(wrapper, "CS103-01")?.get("button").trigger("click");
    await rowOf(wrapper, "CS103-03")?.get("button").trigger("click");
    await flushPromises();

    expect(buttonByText(wrapper, "重新核验这份方案")).toBeUndefined();
    expect(wrapper.find('[role="group"][aria-label="替换预览"]').exists()).toBe(
      false,
    );
  });

  it("says a course has no offerings in the current snapshot instead of reporting an error", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS999");

    expect(wrapper.text()).toContain("这门课在当前快照下没有班次");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("shows a replacement preview and a reminder to re-verify the whole plan after selection", async () => {
    stubOfferings();
    const replaceSpy = vi.spyOn(api, "replaceSessionPlanItem");
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");

    expect(wrapper.text()).toContain("已选 CS103-02 替换 CS103（未选班次）");
    expect(wrapper.text()).toContain("提交前必须重新核验整份方案");
    expect(buttonByText(wrapper, "重新核验这份方案")).toBeDefined();
    expect(replaceSpy).not.toHaveBeenCalled();
  });

  it("lists violations and does not show a pass when re-verification is INVALID", async () => {
    stubOfferings();
    vi.spyOn(api, "replaceSessionPlanItem").mockResolvedValue(
      replacement(
        validation({
          verdict: "INVALID",
          violations: [
            {
              code: "TIME_CONFLICT",
              message: "CS103-02 与 CS102-01 在周四第 7-8 节时间重叠",
              field: null,
              retryable: false,
            },
          ],
        }),
      ),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");
    await recheck(wrapper);

    expect(wrapper.text()).toContain("存在冲突或不满足项");
    expect(wrapper.text()).toContain(
      "CS103-02 与 CS102-01 在周四第 7-8 节时间重叠",
    );
    expect(wrapper.find(".notice--success").exists()).toBe(false);
  });

  it("states that the result is unknown rather than fine when re-verification is UNKNOWN", async () => {
    stubOfferings();
    vi.spyOn(api, "replaceSessionPlanItem").mockResolvedValue(
      replacement(
        validation({
          verdict: "UNKNOWN",
          unknownChecks: [
            {
              code: "TIME_UNPARSED",
              message: "CS103-02 的周次无法确认",
              field: null,
              retryable: false,
            },
          ],
        }),
      ),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");
    await recheck(wrapper);

    expect(wrapper.text()).toContain("部分条件无法确认");
    expect(wrapper.text()).toContain("CS103-02 的周次无法确认");
    expect(wrapper.find(".notice--success").exists()).toBe(false);
  });

  it("does not show a green pass for VALID with SIMULATION scope", async () => {
    stubOfferings();
    vi.spyOn(api, "replaceSessionPlanItem").mockResolvedValue(
      replacement(validation({ verdict: "VALID", scope: "SIMULATION" })),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");
    await recheck(wrapper);

    expect(wrapper.text()).toContain("模拟核验通过");
    expect(wrapper.find(".notice--success").exists()).toBe(false);
  });

  it("shows a green pass only for VALID with REAL_TIMETABLE scope", async () => {
    stubOfferings();
    vi.spyOn(api, "replaceSessionPlanItem").mockResolvedValue(
      replacement(validation({ verdict: "VALID", scope: "REAL_TIMETABLE" })),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");
    await recheck(wrapper);

    expect(wrapper.get(".notice--success").text()).toContain(
      "本次快照下核验通过",
    );
  });

  it("replaces the old verdict with the new one returned for the whole replaced plan", async () => {
    stubOfferings();
    vi.spyOn(api, "replaceSessionPlanItem").mockResolvedValue(
      replacement(
        validation({
          verdict: "INVALID",
          violations: [
            {
              code: "TIME_CONFLICT",
              message: "新方案仍有冲突",
              field: null,
              retryable: false,
            },
          ],
        }),
      ),
    );
    const wrapper = mountPage();
    expect(wrapper.text()).toContain("课程层通过，时间待确认");

    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");
    await recheck(wrapper);

    expect(wrapper.text()).toContain("这是替换后的新版本");
    expect(wrapper.text()).toContain("新方案仍有冲突");
    expect(wrapper.text()).not.toContain("课程层通过，时间待确认");
    expect(wrapper.text()).toContain(`方案 ${PLAN_ID}-CS103-02`);
  });

  it("ignores repeated clicks on re-verify while the request is in flight", async () => {
    stubOfferings();
    let finish: (value: SessionPlanReplacement) => void = () => undefined;
    const replaceSpy = vi
      .spyOn(api, "replaceSessionPlanItem")
      .mockImplementation(
        () =>
          new Promise<SessionPlanReplacement>((resolve) => {
            finish = resolve;
          }),
      );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    await selectClass(wrapper, "CS103-02");

    const button = buttonByText(wrapper, "重新核验这份方案")?.element as
      | HTMLButtonElement
      | undefined;
    button?.click();
    button?.click();
    await flushPromises();
    expect(replaceSpy).toHaveBeenCalledTimes(1);

    finish(replacement(validation({})));
    await flushPromises();
  });

  it("shows a retryable message when offering search fails", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => {
        if (courseCode === "CS103") {
          throw new ApiFailure("班次服务暂时不可用。", "http", 503);
        }
        return { previousPlanId, courseCode, items: DEFAULT_OFFERINGS.CS102 };
      },
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    const alert = wrapper.get('[role="alert"]');
    expect(alert.text()).toContain("班次服务暂时不可用。");
    expect(alert.text()).toContain("可以稍后再试一次");
    expect(wrapper.find("li.offering-row").exists()).toBe(false);
  });
});
