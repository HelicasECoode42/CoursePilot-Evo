import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  AcademicRecord,
  CourseOffering,
  Meeting,
  PlanItem,
  PlanningAnswer,
  PlanValidation,
  Recommendation,
  SnapshotSummary,
  SessionOfferingList,
  SessionPlanReplacement,
} from "../contracts";
import { usePlanningStore } from "../stores/planning";
import ResultView from "./ResultView.vue";

const PLAN_ID = "plan-test-1";
const CLARIFY_ANSWER: PlanningAnswer = {
  ...{
    taskId: "task-clarify",
    traceId: "trace-clarify",
    decision: "CLARIFY",
    academicAudit: {
      curriculumSnapshotId: "curriculum-clarify",
      academicRecordId: "record-clarify",
      recordRevision: 1,
      transcriptComplete: true,
      requirements: [],
      suggestedCourseCodes: [],
      unknowns: [],
    },
    recommendations: [],
    clarification: {
      questionId: "tradeoff:teacher-vs-schedule",
      text: "请确认指定教师和硬时间的优先顺序。",
      choices: [
        { value: "KEEP_TEACHER", label: "先保留指定教师" },
        { value: "KEEP_SCHEDULE", label: "先保证硬时间" },
      ],
      allowFreeText: false,
      requiredFor: ["teacher_vs_schedule"],
    },
    unknowns: [],
    usage: { inputTokens: 1, outputTokens: 1, toolCalls: 1, elapsedMs: 1 },
  },
};
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
      const list: SessionOfferingList & { status: "OK" } = {
        previousPlanId,
        courseCode,
        items: structuredClone(items),
        status: "OK",
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

  it("shows the supported tradeoff and resubmits the answered request", async () => {
    const curriculum: SnapshotSummary = {
      snapshotId: "curriculum-clarify",
      kind: "CURRICULUM",
      state: "PUBLISHED",
      sourceKind: "CURRICULUM_FILE",
      termId: null,
      createdAt: "2026-10-01T00:00:00Z",
      sourceValidation: "VERIFIED",
    };
    const record: AcademicRecord = {
      academicRecordId: "record-clarify",
      revision: 1,
      curriculumSnapshotId: curriculum.snapshotId,
      completedCourses: [],
      transcriptComplete: true,
      sourceKind: "USER_IMPORT",
      createdAt: "2026-10-01T00:00:00Z",
    };
    const calls: Array<{
      request: import("../contracts").PlanningRequest;
      key: string;
    }> = [];
    const submit = vi
      .spyOn(api, "submitPlanning")
      .mockImplementation(async (request, key) => {
        calls.push({ request, key });
        return calls.length === 1 ? CLARIFY_ANSWER : answer();
      });
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-clarify",
      expiresAt: "2099-01-01T00:00:00Z",
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
      records: [record],
      selectedRecordId: record.academicRecordId,
      draft: {
        ...store.draft,
        motives: ["GPA"],
        priorityOrder: ["GPA"],
        teacherPicks: [
          { courseCode: "CS101", teacherKey: "teacher:demo", mode: "MUST" },
        ],
        mustSlots: ["5-1"],
        mustReviewed: true,
        preferReviewed: true,
        classPreferencesReviewed: true,
        prioritiesConfirmed: true,
      },
    });
    await store.submitPlan();
    const wrapper = mountPage();

    expect(wrapper.text()).toContain("不会取消任何 MUST 教师");
    expect(wrapper.text()).toContain("若两者冲突");
    await buttonByText(wrapper, "先保证硬时间并继续规划")?.trigger("click");
    await flushPromises();

    expect(submit).toHaveBeenCalledTimes(2);
    expect(calls[1].key).not.toBe(calls[0].key);
    expect(calls[1].request.intent.priorityOrder).toEqual([
      "GPA",
      "SCHEDULE",
      "SPECIFIC_TEACHER",
    ]);
    expect(calls[1].request.intent.hardConstraints).toHaveLength(1);
    expect(calls[1].request.intent.pinnedTeacherCoursePairs).toEqual([
      { courseCode: "CS101", teacherKey: "teacher:demo", mode: "MUST" },
    ]);
    expect(store.planningResult?.decision).toBe("RECOMMENDATIONS");
  });

  it("submits both the selected clarification option and supplemental text", async () => {
    store.planningResult = {
      ...CLARIFY_ANSWER,
      clarification: {
        questionId: "clarify:preference",
        text: "请选择你的偏好",
        choices: [{ value: "light", label: "课程压力较小" }],
        allowFreeText: true,
        requiredFor: [],
      },
    };
    const answerSpy = vi
      .spyOn(store, "answerClarification")
      .mockReturnValue(true);
    const submitSpy = vi.spyOn(store, "submitPlan").mockResolvedValue();
    const wrapper = mountPage();
    await wrapper
      .get("#clarification-choice-clarify\\:preference")
      .setValue("light");
    await wrapper
      .get("#clarification-text-clarify\\:preference")
      .setValue("周五尽量空闲");
    await buttonByText(wrapper, "回答并继续规划")?.trigger("click");
    expect(answerSpy).toHaveBeenCalledWith(
      "clarify:preference",
      "light\n周五尽量空闲",
    );
    expect(submitSpy).toHaveBeenCalledTimes(1);
  });

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

  it("does not say a course has no offerings when the offering list is UNKNOWN", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        courseCode,
        items: [],
        status: "UNKNOWN",
      }),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS999");

    expect(wrapper.text()).toContain("班次无法确认");
    expect(wrapper.text()).not.toContain("这门课在当前快照下没有班次");
    expect(wrapper.find("li.offering-row").exists()).toBe(false);
  });

  it("does not let any offering be selected when the offering list is UNKNOWN", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        courseCode,
        items: structuredClone(DEFAULT_OFFERINGS[courseCode] ?? []),
        status: "UNKNOWN",
      }),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    const clear = rowOf(wrapper, "CS103-02");
    expect(clear?.get(".offering-tag--unknown").text()).toBe("无法确认");
    expect(clear?.text()).not.toContain("选这个班次");
    expect(wrapper.findAll("li.offering-row")).toHaveLength(3);
    expect(wrapper.text()).toContain("班次无法确认");
  });

  it("does not offer a clear choice while another course's time cannot be read", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        courseCode,
        // 方案里的 CS102-01 在快照中找不到，它的时间就成了缺口。
        items:
          courseCode === "CS102"
            ? []
            : structuredClone(DEFAULT_OFFERINGS[courseCode] ?? []),
        status: "OK",
      }),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    const row = rowOf(wrapper, "CS103-02");
    expect(row?.get(".offering-tag--unknown").text()).toBe("无法确认");
    expect(row?.text()).not.toContain("选这个班次");
    expect(row?.text()).toContain("没能读到");
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
        return {
          previousPlanId,
          courseCode,
          items: DEFAULT_OFFERINGS.CS102,
          status: "OK" as const,
        };
      },
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    const alert = wrapper.get('[role="alert"]');
    expect(alert.text()).toContain("班次服务暂时不可用。");
    expect(alert.text()).toContain("可以稍后再试一次");
    expect(wrapper.find("li.offering-row").exists()).toBe(false);
  });

  it("draws the planned class on the weekly timetable grid", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    const monday1 = wrapper
      .findAll("table.timetable tbody tr")[0]
      .findAll("td")[0];
    expect(monday1.text()).toContain("CS102");
    expect(monday1.text()).toContain("CS102-01");
    // CS103 尚未选班次：它不进课表，并且页面写明原因。
    expect(wrapper.find(".timetable-gaps").text()).toContain(
      "CS103：还没有选定班次，时间未知，未纳入课表。",
    );
  });

  it("keeps an unparsed planned class out of the grid on the result page", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        courseCode,
        items:
          courseCode === "CS102"
            ? [offering("CS102", "CS102-01", [MON_1_2], "UNPARSED")]
            : [],
        status: "OK",
      }),
    );
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.find("table.timetable").exists()).toBe(false);
    expect(wrapper.find(".timetable-gaps").text()).toContain(
      "CS102（班次 CS102-01）：这门课的时间无法解析，未纳入课表。",
    );
  });

  it("shows the unverified-timetable warning when the plan scope is not REAL_TIMETABLE", async () => {
    stubOfferings();
    store.$patch({
      planningResult: {
        ...answer(),
        recommendations: [
          {
            ...recommendation(),
            verification: validation({ scope: "SIMULATION" }),
          },
        ],
      },
    });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain(
      "此课表来自未经核验的班次资料，不代表真实课表，不构成无冲突证明。",
    );
  });
});
