import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  AcademicRecord,
  Course,
  CourseOffering,
  Meeting,
  PlanItem,
  PlanningAnswer,
  PlanningRequest,
  PlanValidation,
  Recommendation,
  SnapshotSummary,
  SessionOfferingList,
  SessionPlanReplacement,
} from "../contracts";
import { usePlanningStore } from "../stores/planning";
import { SAVED_PLANS_KEY } from "../domain/saved-plans";
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

/** 课程目录（合成数据）：课程名用于卡片大字，课程号只作小字。 */
const COURSES: Course[] = [
  {
    courseCode: "CS102",
    name: "程序设计基础（测试）",
    credits: 3,
    category: "必修",
    sourceRefIds: [],
  },
  {
    courseCode: "CS103",
    name: "数据结构（测试）",
    credits: 3,
    category: "必修",
    sourceRefIds: [],
  },
];

/** 规划条件（合成数据）：固定了 CS102 的教师，删除 CS102 时这条固定应一并去掉。 */
const HANDOFF = {
  schemaVersion: "test",
  promptText: "尽量不要早八",
  intent: {
    motives: [],
    priorityOrder: [],
    hardConstraints: [],
    softPreferences: [],
    pinnedTeacherCoursePairs: [
      { courseCode: "CS102", teacherKey: "teacher-li-01", mode: "MUST" },
    ],
    interestTags: [],
    careerDirectionIds: [],
  },
  previousPlanId: null,
} as unknown as PlanningRequest;

function removal(verification: PlanValidation) {
  return {
    previousPlanId: PLAN_ID,
    planId: "plan-after-delete",
    items: [{ courseCode: "CS103", teacherKey: null, classId: null }],
    hardConstraints: [],
    verification,
    empty: false,
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
        mustAvoidChecks: [],
        courseCode,
        items: structuredClone(items),
        status: "OK",
      };
      return list;
    });
}

/** 未建模培养规则的 unknown（Java 原文格式，合成数据）。 */
const UNMODELED_RULES_ISSUE = {
  code: "UNMODELED_CURRICULUM_RULES",
  message: "本培养方案有 1 条规则系统未建模、不参与核验（原表位置：测试表!A7）",
  field: "curriculumSnapshotId",
  retryable: false,
};

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
    vi.spyOn(api, "listCourses").mockResolvedValue({
      items: structuredClone(COURSES),
      nextCursor: null,
    });
    store.$patch({ planningHandoff: HANDOFF });
  });

  const mountPage = () =>
    mount(ResultView, { global: { plugins: [router, pinia] } });

  it("shows course-specific reasons and exploration steps", async () => {
    const result = answer();
    result.recommendations[0].courseRationales = [
      { courseCode: "CS102", reason: "适合作为基础课", reviewNoteIds: [] },
    ];
    result.recommendations[0].explorationDirections = [
      {
        title: "研究方向探索",
        description: "了解研究问题",
        steps: ["阅读入门资料"],
      },
    ];
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.text()).toContain("下学期选课规划");
    // 推荐依据收在展开的课程行里，先打开 CS102 那一行。
    await courseCard(wrapper, "程序设计基础（测试）")!
      .get(".course-row__toggle")
      .trigger("click");
    expect(wrapper.text()).toContain("适合作为基础课");
    expect(wrapper.text()).toContain("研究方向探索");
    expect(wrapper.text()).toContain("阅读入门资料");
    expect(wrapper.text()).toContain("学分");
  });

  it("renders course source and review status supplied with the recommendation", async () => {
    const result = answer();
    result.recommendations[0].courseRationales = [
      {
        courseCode: "CS102",
        reason: "课程内容覆盖基础编程",
        reviewNoteIds: [],
        courseSourceRefIds: ["curriculum:cs102"],
        reviewBasisStatus: "NO_RECORDS",
        rationaleSource: "COURSE_FACTS",
      },
    ];
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();
    await courseCard(wrapper, "程序设计基础（测试）")!
      .get(".course-row__toggle")
      .trigger("click");
    expect(wrapper.text()).toContain("课程目录事实：课程内容覆盖基础编程");
    expect(wrapper.text()).toContain("培养方案资料");
    expect(wrapper.text()).toContain("curriculum:cs102");
    expect(wrapper.text()).toContain("暂无评价依据。");
  });

  it("shows plain-language unknowns and keeps raw diagnostics in collapsed details", async () => {
    const answerRawMessage =
      "W2 FAKE_MODEL mode=REAL source=SYNTHETIC courseCodes=CS102";
    const validationRawMessage =
      "TIME_UNPARSEABLE offeringSnapshot=UNKNOWN mode=REAL courseCode=CS103";
    const result = answer();
    result.unknowns = [
      {
        code: "FAKE_MODEL",
        message: answerRawMessage,
        field: "mode",
        retryable: false,
      },
    ];
    result.recommendations[0].verification = validation({
      verdict: "UNKNOWN",
      scope: "COURSE_ONLY",
      unknownChecks: [
        {
          code: "TIME_UNPARSEABLE",
          message: validationRawMessage,
          field: "meetings",
          retryable: false,
        },
      ],
    });
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    // 方案级问题收在顶部徽标的展开明细里，不在页面上堆一块大提示。
    await wrapper.get(".verdict-badge").trigger("click");
    const notice = wrapper.get('[aria-label="方案级问题"]');
    expect(notice.text()).toContain("当前建议由演示模型生成。");
    expect(notice.text()).not.toContain("FAKE_MODEL");
    expect(notice.text()).not.toContain("W2");
    // 时间无法识别的问题归到 CS103 卡片上，只写一次，不带原始字段。
    const cardIssues = wrapper.get('[aria-label="这门课的问题"]');
    expect(cardIssues.text()).toContain(
      "部分班次的上课时间无法识别，无法确认是否冲突。",
    );
    expect(cardIssues.text()).not.toContain("TIME_UNPARSEABLE");
    expect(cardIssues.text()).not.toContain("offeringSnapshot");
    const details = wrapper.get("details.debug-id");
    expect((details.element as HTMLDetailsElement).open).toBe(false);
    expect(details.text()).toContain("FAKE_MODEL");
    expect(details.text()).toContain(answerRawMessage);
    expect(details.text()).toContain(validationRawMessage);
    expect(details.text()).toContain("mode");
  });

  const buttonByText = (wrapper: ReturnType<typeof mountPage>, text: string) =>
    wrapper.findAll("button").find((item) => item.text() === text);

  /** 换班：点这门课卡片上的「选班次 / 换班」按钮，列出它的班次。 */
  const openAndSearch = async (
    wrapper: ReturnType<typeof mountPage>,
    course: string,
  ) => {
    await wrapper.get(`#result-swap-0-${course}`).trigger("click");
    await flushPromises();
  };

  /** 加课：在右栏顶部的加课框里输入课程名或课程号并搜索。 */
  const searchAdd = async (
    wrapper: ReturnType<typeof mountPage>,
    course: string,
  ) => {
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
      wrapper.get("#result-swap-0-CS103").attributes("aria-expanded"),
    ).toBe("false");

    await openAndSearch(wrapper, "CS103");
    expect(
      wrapper.get("#result-swap-0-CS103").attributes("aria-expanded"),
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

  it("search preview flags a section that Java says hits a must-avoid time, and never calls it clear", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        courseCode,
        status: "OK",
        items: structuredClone(DEFAULT_OFFERINGS[courseCode] ?? []),
        mustAvoidChecks: [
          { classId: "CS103-01", verdict: "CONFLICT" },
          { classId: "CS103-02", verdict: "CLEAR" },
        ],
      }),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    const hit = rowOf(wrapper, "CS103-01");
    expect(hit?.text()).toContain("有冲突");
    expect(hit?.text()).toContain("与你设定的必避时段冲突");
    expect(hit?.text()).not.toContain("没有发现冲突");
    expect(hit?.text()).not.toContain("选这个班次");
    const clear = rowOf(wrapper, "CS103-02");
    expect(clear?.text()).toContain("与你设定的必避时段没有冲突");
  });

  it("lets a section pass the must-avoid check on unverified data, with the source caveat, and still blocks a real hit", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        courseCode,
        status: "OK",
        items: structuredClone(DEFAULT_OFFERINGS[courseCode] ?? []),
        mustAvoidChecks: [
          { classId: "CS103-01", verdict: "CONFLICT" },
          { classId: "CS103-02", verdict: "CLEAR_UNVERIFIED" },
        ],
      }),
    );
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");

    const clear = rowOf(wrapper, "CS103-02");
    expect(clear?.get("button").text()).toBe("选这个班次");
    expect(clear?.get("button").attributes("disabled")).toBeUndefined();
    expect(clear?.text()).toContain("按未核验课表");
    expect(clear?.text()).not.toContain("无法确认是否与你设定的必避时段冲突");
    expect(rowOf(wrapper, "CS103-01")?.text()).toContain(
      "与你设定的必避时段冲突",
    );
  });

  it("does not claim a section is conflict-free when the student has must-avoid times but Java gave no check for it", async () => {
    const wrapper = mountPage();
    store.$patch({
      draft: { ...store.draft, mustSlots: ["5-1"] },
    });
    stubOfferings();
    await openAndSearch(wrapper, "CS103");

    const row = rowOf(wrapper, "CS103-02");
    expect(row?.text()).toContain("还没有核对这个班次与你设定的必避时段");
    expect(row?.text()).not.toContain("没有发现冲突");
    expect(row?.text()).not.toContain("选这个班次");
  });

  it("says a course has no offerings in the current snapshot instead of reporting an error", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await searchAdd(wrapper, "CS999");

    expect(wrapper.text()).toContain("CS999 在当前快照下没有开课班次");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("does not say a course has no offerings when the offering list is UNKNOWN", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        mustAvoidChecks: [],
        courseCode,
        items: [],
        status: "UNKNOWN",
      }),
    );
    const wrapper = mountPage();
    await searchAdd(wrapper, "CS999");

    expect(wrapper.text()).toContain("班次无法确认");
    expect(wrapper.text()).not.toContain("在当前快照下没有开课班次");
    expect(wrapper.find("li.offering-row").exists()).toBe(false);
  });

  it("does not let any offering be selected when the offering list is UNKNOWN", async () => {
    vi.spyOn(api, "searchSessionOfferings").mockImplementation(
      async (previousPlanId, courseCode) => ({
        previousPlanId,
        mustAvoidChecks: [],
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
        mustAvoidChecks: [],
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
    expect(wrapper.find(".verdict-badge--pass").exists()).toBe(false);
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
    expect(wrapper.find(".verdict-badge--pass").exists()).toBe(false);
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
    expect(wrapper.find(".verdict-badge--pass").exists()).toBe(false);
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

    expect(wrapper.get(".verdict-badge--pass").text()).toContain(
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

    expect(wrapper.text()).toContain("这是调整后重新核验的新版本");
    await wrapper.get(".verdict-badge").trigger("click");
    expect(wrapper.text()).toContain("新方案仍有冲突");
    expect(wrapper.text()).not.toContain("课程层通过，时间待确认");
    expect(wrapper.get("h2.plan-bar__title").text()).toBe("方案 1");
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
          mustAvoidChecks: [],
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
        mustAvoidChecks: [],
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

  const courseCard = (wrapper: ReturnType<typeof mountPage>, name: string) =>
    wrapper
      .findAll("li.course-card")
      .find((card) => card.text().includes(name));

  it("draws each plan course as a card with its name, code, real teacher and human time", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    const card = courseCard(wrapper, "程序设计基础（测试）");
    expect(card).toBeDefined();
    // 默认是紧凑行：课程名、学分、老师与短时间。
    expect(card!.text()).toContain("测试教师（合成）");
    expect(card!.text()).toContain("周一1-2 · 1-16周");
    expect(card!.text()).not.toContain("teacher-li-01");
    expect(card!.text()).not.toContain("{第");
    // 课程号与完整时间收在展开的详情里。
    expect(card!.find(".course-row__detail").exists()).toBe(false);
    await card!.get(".course-row__toggle").trigger("click");
    expect(card!.get(".course-row__detail").text()).toContain("CS102");
    expect(card!.get(".course-row__detail").text()).toContain(
      "周一 第1-2节 · 第1–16周",
    );
  });

  it("shows a plan number instead of the raw plan id, which stays in a collapsed debug section", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    const heading = wrapper.get("h2.plan-bar__title");
    expect(heading.text()).toBe("方案 1");
    expect(heading.attributes("title")).toBe(PLAN_ID);
    expect(wrapper.get(".debug-id summary").text()).toBe("排查编号与详情");
    expect(wrapper.get(".debug-id code").text()).toBe(PLAN_ID);
  });

  it("deleting a course calls deterministic plan removal and shows the returned verdict", async () => {
    stubOfferings();
    const submit = vi
      .spyOn(api, "removeSessionPlanCourse")
      .mockResolvedValue(
        removal(validation({ verdict: "VALID", scope: "REAL_TIMETABLE" })),
      );
    const wrapper = mountPage();
    await flushPromises();

    await courseCard(wrapper, "程序设计基础（测试）")!
      .get("button.course-card__delete")
      .trigger("click");
    await flushPromises();

    expect(submit).toHaveBeenCalledTimes(1);
    const [request, key] = submit.mock.calls[0];
    expect(request).toEqual({ previousPlanId: PLAN_ID, courseCode: "CS102" });
    expect(key).toMatch(/^web-/);
    expect(wrapper.text()).toContain("这是调整后重新核验的新版本");
    expect(wrapper.get(".verdict-badge--pass").text()).toContain(
      "本次快照下核验通过",
    );
    expect(courseCard(wrapper, "程序设计基础（测试）")).toBeUndefined();
    expect(courseCard(wrapper, "数据结构（测试）")?.text()).toContain(
      "尚未选定班次",
    );
    expect(store.editedPlans[PLAN_ID]).toMatchObject({
      planId: "plan-after-delete",
      items: [{ courseCode: "CS103" }],
      verification: { verdict: "VALID" },
      empty: false,
    });
  });

  it("hides the timetable after deleting the last course from a plan", async () => {
    const result = answer();
    result.recommendations[0].items = [INITIAL_ITEMS[0]];
    store.$patch({ planningResult: result });
    stubOfferings();
    vi.spyOn(api, "removeSessionPlanCourse").mockResolvedValue({
      previousPlanId: PLAN_ID,
      planId: "plan-empty-after-delete",
      items: [],
      hardConstraints: [],
      verification: validation({ verdict: "UNKNOWN", scope: "COURSE_ONLY" }),
      empty: true,
    });
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.get("button.course-card__delete").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("空方案，尚无核验结果");
    expect(wrapper.text()).toContain(
      "课程已从方案中移除。返回问卷后可以重新生成方案。",
    );
    expect(wrapper.text()).not.toContain("一周课表");
    expect(wrapper.text()).not.toContain("正在读取班次时间，请稍候。");
    expect(wrapper.find(".course-cards li").exists()).toBe(false);
  });

  it("keeps the original plan and its old verdict when deleting fails", async () => {
    stubOfferings();
    vi.spyOn(api, "removeSessionPlanCourse").mockRejectedValue(
      new ApiFailure("服务暂时不可用。", "http", 503),
    );
    const wrapper = mountPage();
    await flushPromises();

    await courseCard(wrapper, "程序设计基础（测试）")!
      .get("button.course-card__delete")
      .trigger("click");
    await flushPromises();

    expect(
      wrapper
        .findAll(".notice--error")
        .map((item) => item.text())
        .join(""),
    ).toContain("原方案保留");
    expect(courseCard(wrapper, "程序设计基础（测试）")).toBeDefined();
    expect(courseCard(wrapper, "数据结构（测试）")).toBeDefined();
    expect(wrapper.text()).toContain("课程层通过，时间待确认");
    expect(wrapper.text()).not.toContain("这是调整后重新核验的新版本");
  });

  it("shows an UNKNOWN verdict after deleting as unconfirmed, never as a pass", async () => {
    stubOfferings();
    vi.spyOn(api, "removeSessionPlanCourse").mockResolvedValue(
      removal(
        validation({
          verdict: "UNKNOWN",
          scope: "REAL_TIMETABLE",
          unknownChecks: [
            {
              code: "TIME_UNKNOWN",
              message: "剩余课程的时间无法确认（测试）",
              field: null,
              retryable: false,
            },
          ],
        }),
      ),
    );
    const wrapper = mountPage();
    await flushPromises();

    await courseCard(wrapper, "程序设计基础（测试）")!
      .get("button.course-card__delete")
      .trigger("click");
    await flushPromises();

    expect(wrapper.find(".verdict-badge--pass").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("核验通过");
    expect(wrapper.text()).toContain("剩余课程的时间无法确认（测试）");
  });

  it("shows a final-course deletion as an empty plan without retaining the old verdict", async () => {
    stubOfferings();
    const singleCourseAnswer = answer();
    singleCourseAnswer.recommendations[0].items = [
      { courseCode: "CS102", teacherKey: "teacher-li-01", classId: "CS102-01" },
    ];
    store.$patch({ planningResult: singleCourseAnswer });
    vi.spyOn(api, "removeSessionPlanCourse").mockResolvedValue({
      previousPlanId: PLAN_ID,
      planId: "plan-empty",
      items: [],
      hardConstraints: [],
      verification: null,
      empty: true,
    });
    const wrapper = mountPage();
    await flushPromises();
    await courseCard(wrapper, "程序设计基础（测试）")!
      .get("button.course-card__delete")
      .trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("空方案，尚无核验结果");
    expect(wrapper.text()).not.toContain("课程层通过，时间待确认");
    expect(wrapper.findAll(".course-card")).toHaveLength(0);
    expect(store.editedPlans[PLAN_ID]).toMatchObject({
      planId: "plan-empty",
      items: [],
      verification: null,
      empty: true,
    });
  });

  it("shows timetable and curriculum as two blocks with separate verdicts and an overall line", async () => {
    const result = answer();
    result.recommendations[0].verification = validation({
      verdict: "UNKNOWN",
      scope: "REAL_TIMETABLE",
      unknownChecks: [UNMODELED_RULES_ISSUE],
      sections: [
        {
          scope: "TIMETABLE",
          verdict: "VALID",
          violations: [],
          unknownChecks: [],
        },
        {
          scope: "CURRICULUM",
          verdict: "UNKNOWN",
          violations: [],
          unknownChecks: [UNMODELED_RULES_ISSUE],
        },
      ],
    });
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();
    const badges = wrapper.findAll(".verdict-badge");
    expect(badges).toHaveLength(2);
    expect(badges[0].text()).toBe("课表：通过");
    expect(badges[0].classes()).toContain("verdict-badge--pass");
    expect(badges[1].text()).toBe("毕业要求：需人工确认 1 条");
    expect(badges[1].classes()).toContain("verdict-badge--pending");
    await badges[1].trigger("click");
    const details = wrapper.get(".verdict-details");
    expect(details.text()).toContain("本学期课表核验：通过");
    expect(details.text()).toContain("毕业要求核对：无法确认");
    expect(details.text()).toContain("有 1 条培养方案说明需人工确认");
    expect(details.text()).not.toContain("测试表!A7");
    expect(details.text()).toContain(
      "总体：部分条件无法确认（取两项中较差的结果）",
    );
  });

  it("shows a timetable conflict as its own failing block and keeps each block's own pass state", async () => {
    const result = answer();
    result.recommendations[0].verification = validation({
      verdict: "INVALID",
      scope: "REAL_TIMETABLE",
      violations: [
        {
          code: "TIME_CONFLICT",
          message: "周一 1-2 节两门课冲突",
          field: "items",
          retryable: false,
        },
      ],
      sections: [
        {
          scope: "TIMETABLE",
          verdict: "INVALID",
          violations: [
            {
              code: "TIME_CONFLICT",
              message: "周一 1-2 节两门课冲突",
              field: "items",
              retryable: false,
            },
          ],
          unknownChecks: [],
        },
        {
          scope: "CURRICULUM",
          verdict: "VALID",
          violations: [],
          unknownChecks: [],
        },
      ],
    });
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();
    const badges = wrapper.findAll(".verdict-badge");
    expect(badges[0].text()).toBe("课表：不通过");
    expect(badges[0].classes()).toContain("verdict-badge--fail");
    expect(badges[1].text()).toBe("毕业要求：通过");
    // 毕业要求分项不依赖班次，真实的 VALID 仍可是通过；课表冲突不会把它拉成不通过。
    expect(badges[1].classes()).toContain("verdict-badge--pass");
    await badges[0].trigger("click");
    expect(wrapper.get(".verdict-details").text()).toContain(
      "周一 1-2 节两门课冲突",
    );
  });

  it("uses two columns at 1440px and stacks below 1024px", async () => {
    const original = globalThis.innerWidth;
    try {
      Object.defineProperty(globalThis, "innerWidth", {
        configurable: true,
        value: 1440,
      });
      stubOfferings();
      const wide = mountPage();
      await flushPromises();
      expect(wide.find(".plan-grid--split").exists()).toBe(true);
      expect(wide.find(".plan-grid__timetable").exists()).toBe(true);
      expect(wide.find(".plan-grid__courses").exists()).toBe(true);
      wide.unmount();

      Object.defineProperty(globalThis, "innerWidth", {
        configurable: true,
        value: 390,
      });
      const narrow = mountPage();
      await flushPromises();
      expect(narrow.find(".plan-grid--split").exists()).toBe(false);
      expect(narrow.find(".plan-grid").exists()).toBe(true);
      narrow.unmount();
    } finally {
      Object.defineProperty(globalThis, "innerWidth", {
        configurable: true,
        value: original,
      });
    }
  });

  it("shows one unplaced line per course, with the specific reason, on that course's card", async () => {
    const result = answer();
    result.unknowns = [
      {
        code: "SECTION_NOT_ASSIGNED",
        message: "课程 CS103：与其他推荐课程的时间冲突",
        field: null,
        retryable: false,
      },
    ];
    result.recommendations[0].verification = validation({
      verdict: "UNKNOWN",
      scope: "COURSE_ONLY",
      unknownChecks: [
        {
          code: "SECTION_UNASSIGNED",
          message: "课程 CS103 未指定班次，无法核验其时间与班次归属",
          field: null,
          retryable: false,
        },
      ],
    });
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    const card = courseCard(wrapper, "数据结构（测试）")!;
    const lines = card.findAll(".course-card__issues li");
    expect(lines).toHaveLength(1);
    expect(lines[0].text()).toBe("未排进课表：与其他推荐课程的时间冲突");
    expect(wrapper.text().match(/没有选定班次/g) ?? []).toHaveLength(0);
    expect(wrapper.text()).not.toContain("暂时无法确认");
  });

  it("adds a clear offering through add-course and shows the re-verified new version", async () => {
    stubOfferings();
    const addSpy = vi.spyOn(api, "addSessionPlanCourse").mockResolvedValue({
      previousPlanId: PLAN_ID,
      planId: "plan-after-add",
      items: [
        ...INITIAL_ITEMS,
        {
          courseCode: "CS103",
          teacherKey: "teacher-wang-03",
          classId: "CS103-02",
        },
      ],
      hardConstraints: [],
      verification: validation({ verdict: "VALID", scope: "COURSE_ONLY" }),
      empty: false,
    });
    const wrapper = mountPage();
    await searchAdd(wrapper, "CS103");

    const addButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "加入方案");
    expect(addButton).toBeDefined();
    await addButton!.trigger("click");
    await flushPromises();

    expect(addSpy).toHaveBeenCalledTimes(1);
    const [body, key] = addSpy.mock.calls[0];
    expect(body).toEqual({
      previousPlanId: PLAN_ID,
      courseCode: "CS103",
      classId: "CS103-02",
    });
    expect(key).toMatch(/^web-/);
    expect(store.editedPlans[PLAN_ID]?.planId).toBe("plan-after-add");
    expect(wrapper.text()).toContain("这是调整后重新核验的新版本");
  });

  it("maps add-course error codes to plain text and keeps the plan unchanged", async () => {
    stubOfferings();
    vi.spyOn(api, "addSessionPlanCourse").mockRejectedValue(
      new ApiFailure("服务端原文", "http", 422, "COURSE_ALREADY_TAKEN"),
    );
    const wrapper = mountPage();
    await searchAdd(wrapper, "CS103");
    const addButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "加入方案");
    await addButton!.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain(
      "你已修过或正在修这门课，不能再加入方案。",
    );
    expect(wrapper.text()).not.toContain("服务端原文");
    expect(store.editedPlans[PLAN_ID]).toBeUndefined();
  });

  it("shows the reused-reason notice once above the course list after an edit", async () => {
    const result = answer();
    result.recommendations[0].courseRationales = [
      { courseCode: "CS102", reason: "适合作为基础课", reviewNoteIds: [] },
    ];
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();
    // 未调整前不出现该说明。
    expect(wrapper.text()).not.toContain("以下理由来自原推荐");

    store.applyPlanEdit(PLAN_ID, {
      previousPlanId: PLAN_ID,
      planId: "plan-after-edit",
      items: structuredClone(INITIAL_ITEMS),
      hardConstraints: [],
      verification: validation({ verdict: "VALID", scope: "COURSE_ONLY" }),
      empty: false,
    });
    await flushPromises();

    const notes = wrapper.findAll(".course-list__note");
    expect(notes).toHaveLength(1);
    expect(notes[0].text()).toBe("以下理由来自原推荐：方案调整后未重新生成。");
    expect(
      wrapper
        .findAll(".course-card")
        .some((card) => card.text().includes("以下理由来自原推荐")),
    ).toBe(false);
  });

  it("collapses the career section by default and renames the regenerate button", async () => {
    const result = answer();
    result.recommendations[0].explorationDirections = [
      {
        title: "研究方向探索",
        description: "了解研究问题",
        steps: ["阅读入门资料"],
      },
    ];
    store.$patch({ planningResult: result });
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    const career = wrapper.get("details.career-details");
    expect(career.attributes("open")).toBeUndefined();
    expect(career.get("summary").text()).toBe(
      "职业与科研方向探索（AI 生成，仅供参考）",
    );
    const regenerate = wrapper
      .findAll("button")
      .find((button) => button.text() === "让 AI 重新生成方案");
    expect(regenerate).toBeDefined();
    expect(wrapper.text()).toContain(
      "会按当前条件重新推荐，已做的换班/加课会被替换",
    );
    expect(wrapper.findAll("button").some((b) => b.text() === "重新提交")).toBe(
      false,
    );
  });

  it("puts the add-course action in the right column toolbar", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();
    const addButton = wrapper
      .get(".plan-actions")
      .findAll("button")
      .find((button) => button.text() === "加课");
    expect(addButton).toBeDefined();
    expect(wrapper.find(".plan-grid__courses .add-course").exists()).toBe(true);
  });

  it("closes the swap panel with Escape and returns focus to its card button", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await openAndSearch(wrapper, "CS103");
    expect(wrapper.find(".swap-panel").exists()).toBe(true);

    await wrapper.get(".swap-panel").trigger("keydown", { key: "Escape" });
    await flushPromises();
    expect(wrapper.find(".swap-panel").exists()).toBe(false);
    expect(
      wrapper.get("#result-swap-0-CS103").attributes("aria-expanded"),
    ).toBe("false");
  });

  it("keeps each course row collapsed until it is opened, with 换班 and 删除 beside it", async () => {
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    const card = courseCard(wrapper, "程序设计基础（测试）")!;
    const toggle = card.get(".course-row__toggle");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(card.get(".course-row__tools").text()).toContain("换班");
    expect(card.get(".course-row__tools").text()).toContain("删除");
    await toggle.trigger("click");
    expect(card.get(".course-row__toggle").attributes("aria-expanded")).toBe(
      "true",
    );
    await card.get(".course-row__toggle").trigger("click");
    expect(card.find(".course-row__detail").exists()).toBe(false);
  });

  it("saves a plan copy to this browser without grades and reopens it read-only", async () => {
    localStorage.clear();
    stubOfferings();
    const wrapper = mountPage();
    await flushPromises();

    await buttonByText(wrapper, "保存方案")!.trigger("click");
    const menuItem = wrapper
      .findAll('[role="menuitem"]')
      .find((item) => item.text().startsWith("保存到本机浏览器"));
    await menuItem!.trigger("click");
    await flushPromises();

    const raw = localStorage.getItem(SAVED_PLANS_KEY);
    expect(raw).not.toBeNull();
    const saved = JSON.parse(raw!);
    expect(saved).toHaveLength(1);
    expect(saved[0].planId).toBe(PLAN_ID);
    expect(
      saved[0].courses.map((c: { courseCode: string }) => c.courseCode),
    ).toEqual(["CS102", "CS103"]);
    expect(raw).not.toMatch(/grade|transcript|token|password/i);
    expect(wrapper.text()).toContain("非最新核验结果");

    const list = wrapper.get('[aria-label="本机保存的方案"]');
    expect(list.text()).toContain("方案 1");
    await list.get("button").trigger("click");
    const view = wrapper.get('[aria-label="保存的方案副本（只读）"]');
    expect(view.text()).toContain("程序设计基础（测试）");
    expect(view.find("button").text()).toContain("删除这份副本");
    localStorage.clear();
  });

  it("opens the browser print dialog from the save menu and marks .ics as unavailable", async () => {
    stubOfferings();
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    const wrapper = mountPage();
    await flushPromises();

    await buttonByText(wrapper, "保存方案")!.trigger("click");
    expect(wrapper.text()).toContain("缺少开学日期和节次的上课钟点");
    const menuItem = wrapper
      .findAll('[role="menuitem"]')
      .find((item) => item.text().startsWith("打印"));
    await menuItem!.trigger("click");

    expect(print).toHaveBeenCalledTimes(1);
    expect(wrapper.find('[role="menu"]').exists()).toBe(false);
    print.mockRestore();
  });
});
