<script setup lang="ts">
/**
 * 规划结果页（E-F4）。
 *
 * 前半：把 store 里的 PlanningAnswer 显示出来，颜色与文案交给 domain/answer-display.ts。
 * 后半：换班（替换方案里的一门课）、删除、加课搜索。
 *   - 搜索时的「有冲突 / 可选 / 无法确认」只是预览，不是核验结论；
 *   - 只有替换接口返回的 verification（对整份新方案的判决）才是结论，原样展示；
 *   - 问题按课程归组，显示在课程卡片上；方案级问题收在顶部徽标的展开明细里（见 domain/result-issues.ts）。
 */
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  Course,
  CourseOffering,
  MustAvoidCheck,
  MustAvoidVerdict,
  Issue,
  Meeting,
  PlanItem,
  PlanningAnswer,
  PlanSection,
  PlanValidation,
  Recommendation,
  ReviewNote,
} from "../contracts";
import {
  collectUnknowns,
  describeVerification,
  type VerificationView,
} from "../domain/answer-display";
import {
  SECTION_TITLE,
  hasSections,
  sectionTone,
  UNMODELED_RULES_CODE,
  unmodeledRuleLine,
  verdictBadge,
  type SectionTone,
} from "../domain/plan-sections";
import {
  teacherReviewNotes,
  unboundReviewNotes,
} from "../domain/review-summary";
import {
  explainUnknownIssue,
  isVerificationLevelUnknown,
  unplacedReasonsFor,
  type UnknownContext,
} from "../domain/unknown-explain";
import {
  groupIssues,
  isWideLayout,
  overallBadge,
  requirementTag,
  sectionBadges,
  type CourseIssueLine,
  type GroupedIssues,
  type SectionBadge,
} from "../domain/result-issues";
import {
  isOfficialUnverified,
  planUsesSimulation,
} from "../domain/offering-selection";
import {
  meetingsText,
  resolveTimetableSources,
  type OfferingListRead,
  type TimetableSource,
} from "../domain/timetable";
import PlanTimetable from "../components/PlanTimetable.vue";
import OfferingResults from "../components/OfferingResults.vue";
import { resolveCourseQuery } from "../domain/course-query";
import CourseReviewBasis from "../components/CourseReviewBasis.vue";
import ReviewSummary from "../components/ReviewSummary.vue";
import { usePlanningStore } from "../stores/planning";

const store = usePlanningStore();
const router = useRouter();

const result = computed<PlanningAnswer | null>(() => store.planningResult);
const answeringTradeoff = ref(false);
const clarificationChoice = ref("");
const clarificationText = ref("");
const tradeoffChoices = computed(() => {
  const question = result.value?.clarification;
  if (
    result.value?.decision !== "CLARIFY" ||
    question?.questionId !== "tradeoff:teacher-vs-schedule"
  ) {
    return [];
  }
  const choicesByValue = new Map(
    question.choices.map((choice) => [choice.value, choice]),
  );
  const teacher = choicesByValue.get("KEEP_TEACHER");
  const schedule = choicesByValue.get("KEEP_SCHEDULE");
  return teacher && schedule ? [teacher, schedule] : [];
});
const clarificationRequiresQuestionnaire = computed(
  () =>
    result.value?.clarification?.requiredFor.some((target) =>
      ["motives", "priorityOrder"].includes(target),
    ) ?? false,
);

async function answerTradeoff(questionId: string, choiceValue: string) {
  if (answeringTradeoff.value) return;
  if (!store.answerTradeoffClarification(questionId, choiceValue)) return;
  answeringTradeoff.value = true;
  try {
    await store.submitPlan();
  } finally {
    answeringTradeoff.value = false;
  }
}

async function answerGeneralClarification(questionId: string) {
  if (answeringTradeoff.value) return;
  const question = result.value?.clarification;
  const text = clarificationText.value.trim();
  const response = [clarificationChoice.value, text].filter(Boolean).join("\n");
  if (!question || !store.answerClarification(questionId, response)) return;
  answeringTradeoff.value = true;
  try {
    await store.submitPlan();
  } finally {
    answeringTradeoff.value = false;
  }
}

const headline = computed(() => {
  if (store.submitStatus === "submitting") return "正在生成建议";
  const answer = result.value;
  if (!answer) return "还没有结果";
  switch (answer.decision) {
    case "CLARIFY":
      return "需要你先回答一个问题";
    case "RECOMMENDATIONS":
      return "给你这些课程建议";
    default:
      return "这一步没能确认";
  }
});

/** 一份方案在页面上的样子。替换过就是替换后的新版本，判决只用新返回的那一份。 */
interface PlanView {
  planId: string;
  items: PlanItem[];
  verification: PlanValidation | null;
  empty: boolean;
  /** 替换前的推荐 planId；未替换时为 null。 */
  replacedFrom: string | null;
}

interface PlanEntry {
  index: number;
  recommendation: Recommendation;
  plan: PlanView;
  view: VerificationView | null;
}

/** 替换或删除课程后的新版本：只保存页面要显示的三项。 */
interface ReplacedPlan {
  planId: string;
  items: PlanItem[];
  verification: PlanValidation | null;
  empty: boolean;
}

/** 服务端确认的编辑版本存放在 planning store，页面重建后继续展示当前选择。 */
const replacements = computed<Record<string, ReplacedPlan>>(
  () => store.editedPlans,
);

function currentPlan(recommendation: Recommendation): PlanView {
  const replaced = replacements.value[recommendation.planId];
  if (replaced === undefined) {
    return {
      planId: recommendation.planId,
      items: recommendation.items,
      verification: recommendation.verification,
      empty: false,
      replacedFrom: null,
    };
  }
  return {
    planId: replaced.planId,
    items: replaced.items,
    verification: replaced.verification,
    empty: replaced.empty,
    replacedFrom: recommendation.planId,
  };
}

const recommendations = computed<Recommendation[]>(
  () => result.value?.recommendations ?? [],
);

/** 未知项：答复级 + 每份当前方案的核验级（替换后只用新判决）。 */
const unknowns = computed<Issue[]>(() => {
  if (result.value === null) return [];
  const plans = recommendations.value.map((item) => currentPlan(item));
  const validations = plans
    .map((plan) => plan.verification)
    .filter((item): item is PlanValidation => item !== null);
  // 方案被换班重新核验后，原答复里的核验级未知项（如「班次来源尚未核验」）已经过时，
  // 只保留与核验无关的答复级项，核验级项只来自新判决。
  const replaced = plans.some((plan) => plan.replacedFrom !== null);
  const answerLevel = replaced
    ? result.value.unknowns.filter(
        (issue) => !isVerificationLevelUnknown(issue.code),
      )
    : result.value.unknowns;
  return collectUnknowns(answerLevel, validations);
});

/**
 * 方案所用的开课快照。优先取判决里的 offeringSnapshotId 对应的快照，取不到才用当前选中的快照。
 * 文案据此区分「学校课表待核验」与其他情况，不再笼统地说「不是模拟来源」。
 */
const planOfferingSnapshot = computed(() => {
  const id =
    recommendations.value.find(
      (item) => item.verification.offeringSnapshotId !== null,
    )?.verification.offeringSnapshotId ?? null;
  if (id === null) return store.selectedOfferingSnapshot;
  return (
    store.offeringSnapshots.find((item) => item.snapshotId === id) ??
    store.selectedOfferingSnapshot
  );
});

const unknownContext = computed<UnknownContext>(() => ({
  officialUnverified: isOfficialUnverified(planOfferingSnapshot.value),
}));

/** 显示不确定事实的用户文案；原始服务诊断只放在折叠的排查详情中。文案表见 domain/unknown-explain.ts。 */
function explainUnknown(issue: Issue): string {
  if (issue.code === UNMODELED_RULES_CODE) return unmodeledRuleLine(issue);
  return explainUnknownIssue(issue, courseNames.value, unknownContext.value);
}

/**
 * 未排进课表的原因：课程号 → 原因。跟随每份方案的当前版本（换班后用新判决），
 * 不再读换班前答复里的旧原因。规则在 domain/unknown-explain.ts 的 unplacedReasonsFor。
 */
const unplacedReasons = computed<Record<string, string>>(() =>
  unplacedReasonsFor(
    result.value?.unknowns ?? [],
    recommendations.value.map((item) => {
      const plan = currentPlan(item);
      return {
        replaced: plan.replacedFrom !== null,
        verification: plan.verification,
      };
    }),
  ),
);

/** 是否有方案用了模拟班次。横幅只跟随方案的判决，不跟随客户端模式。 */
const planIsSimulated = computed(() =>
  planUsesSimulation(
    recommendations.value.map((item) => item.verification.scope),
  ),
);

/** 展示门禁：统一交给 describeVerification，带受控缺口标记时降级。 */
function verificationView(validation: PlanValidation): VerificationView {
  let view = describeVerification(validation, unknowns.value);
  if (validation.scope === "SIMULATION") {
    view = { ...view, detail: "模拟班次不代表下学期开课情况。" };
  }
  if (validation.unknownChecks.length === 0) return view;
  return {
    ...view,
    detail: [...new Set(validation.unknownChecks.map(explainUnknown))].join(
      "；",
    ),
  };
}

const planEntries = computed<PlanEntry[]>(() =>
  recommendations.value.map((recommendation, index) => {
    const plan = currentPlan(recommendation);
    return {
      index,
      recommendation,
      plan,
      view:
        plan.verification === null ? null : verificationView(plan.verification),
    };
  }),
);

/** 两个分项（课表 / 毕业要求）。旧后端不返回 sections 时为空，页面退回合并展示。 */
function sectionsOf(validation: PlanValidation | null): PlanSection[] {
  if (validation === null || !hasSections(validation)) return [];
  return validation.sections ?? [];
}

/**
 * 分项的绿色门禁只看它自己的依据，不用整份方案的判决：
 *   - 课表分项要真实班次（REAL_TIMETABLE）；
 *   - 毕业要求分项不依赖班次，只排除模拟方案；
 *   - 两者都不能带受控缺口标记（假模型/假工具）。
 */
/** 分项的颜色档位（绿色只在真实依据下出现，见 sectionTone）。 */
function sectionToneOf(
  section: PlanSection,
  validation: PlanValidation | null,
  view: VerificationView,
): SectionTone {
  const scope = validation?.scope ?? null;
  const realCheck =
    view.tone !== "simulated" &&
    (section.scope === "TIMETABLE"
      ? scope === "REAL_TIMETABLE"
      : scope !== null && scope !== "SIMULATION");
  return sectionTone(section.verdict, realCheck);
}

function diagnosticsOf(entry: PlanEntry): Issue[] {
  return collectUnknowns(
    result.value?.unknowns ?? [],
    entry.plan.verification === null ? [] : [entry.plan.verification],
  );
}

function courseCodesOf(entry: PlanEntry): string {
  return entry.plan.items.map((item) => item.courseCode).join("、") || "无";
}

/* ---------- 布局、问题归组与顶部徽标 ---------- */

/** 宽屏（≥1024px）两栏：左课表（粘性）、右课程；窄屏上下排列。断点与 domain/result-issues.ts 一致。 */
const wideLayout = ref(readWideLayout());
function readWideLayout(): boolean {
  return (
    typeof globalThis.innerWidth === "number" &&
    isWideLayout(globalThis.innerWidth)
  );
}
function onWindowResize() {
  wideLayout.value = readWideLayout();
}
onMounted(() => globalThis.addEventListener("resize", onWindowResize));
onBeforeUnmount(() => globalThis.removeEventListener("resize", onWindowResize));

/** 顶部徽标展开的方案级明细，按方案的 planId 记录。 */
const verdictOpenFor = ref<string | null>(null);
function isVerdictOpen(entry: PlanEntry): boolean {
  return verdictOpenFor.value === entry.plan.planId;
}
function toggleVerdict(entry: PlanEntry) {
  verdictOpenFor.value = isVerdictOpen(entry) ? null : entry.plan.planId;
}

/**
 * 一份方案的问题归组：违规与未知项（替换后只用新判决，答复级的核验项已过时，同 unknowns）。
 * 结果按课程归到卡片上，其余是方案级，供展开明细使用。
 */
function groupsOf(entry: PlanEntry): GroupedIssues {
  const validation = entry.plan.verification;
  const answerLevel =
    entry.plan.replacedFrom !== null
      ? (result.value?.unknowns ?? []).filter(
          (issue) => !isVerificationLevelUnknown(issue.code),
        )
      : (result.value?.unknowns ?? []);
  const unknownList = collectUnknowns(
    answerLevel,
    validation === null ? [] : [validation],
  );
  return groupIssues(
    validation?.violations ?? [],
    unknownList,
    entry.plan.items.map((item) => item.courseCode),
    explainUnknown,
  );
}

function issuesOfCourse(
  entry: PlanEntry,
  courseCode: string,
): CourseIssueLine[] {
  return groupsOf(entry).byCourse[courseCode] ?? [];
}

function sectionToneBadge(
  section: PlanSection,
  validation: PlanValidation,
  view: VerificationView,
): SectionTone {
  return sectionToneOf(section, validation, view);
}

/** 顶部两个徽标：课表 / 毕业要求。没有分项的旧数据只给一个总判决。 */
function badgesOf(entry: PlanEntry): SectionBadge[] {
  const validation = entry.plan.verification;
  const view = entry.view;
  if (validation === null || view === null) return [];
  const officialUnverified = unknownContext.value.officialUnverified === true;
  if (!hasSections(validation)) {
    const tone: SectionTone =
      view.tone === "real-pass"
        ? "pass"
        : view.tone === "conflict"
          ? "fail"
          : "pending";
    return [overallBadge(view.label, tone)];
  }
  return sectionBadges(
    sectionsOf(validation),
    (section) => sectionToneBadge(section, validation, view),
    officialUnverified,
  );
}

/* ---------- 课程名与删除课程 ---------- */

/** 课程号 → 课程名，来自培养方案的课程目录。读不到时页面只显示课程号，并说明。 */
const courseNames = ref<Record<string, string>>({});
const courseCredits = ref<Record<string, number | null>>({});
/** 课程号 → 培养方案里的类别（用于「必修 / 选修」标签）。 */
const courseCategories = ref<Record<string, string>>({});
const courseReviews = ref<
  Record<
    string,
    {
      status: "loading" | "ready" | "error";
      notes: ReviewNote[];
      unknown: boolean;
      /** 读取失败的原因，原样显示给学生。 */
      error?: string;
    }
  >
>({});
const courseNamesStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
let courseNamesVersion = 0;
const MAX_COURSE_PAGES = 20;

async function loadCourseNames(curriculumSnapshotId: string) {
  const version = ++courseNamesVersion;
  courseNamesStatus.value = "loading";
  const names: Record<string, string> = {};
  const credits: Record<string, number | null> = {};
  const categories: Record<string, string> = {};
  try {
    let cursor: string | null = null;
    for (let page = 0; page < MAX_COURSE_PAGES; page += 1) {
      const list = await api.listCourses(curriculumSnapshotId, cursor);
      if (version !== courseNamesVersion) return;
      for (const course of list.items) {
        names[course.courseCode] = course.name;
        credits[course.courseCode] = course.credits;
        categories[course.courseCode] = course.category;
      }
      if (list.nextCursor === null) break;
      cursor = list.nextCursor;
    }
    courseNames.value = names;
    courseCredits.value = credits;
    courseCategories.value = categories;
    courseNamesStatus.value = "ready";
  } catch {
    if (version !== courseNamesVersion) return;
    courseNames.value = {};
    courseCredits.value = {};
    courseCategories.value = {};
    courseNamesStatus.value = "error";
  }
}

async function loadCourseEvidence(courseCode: string) {
  if (courseReviews.value[courseCode]?.status === "loading") return;
  courseReviews.value = {
    ...courseReviews.value,
    [courseCode]: { status: "loading", notes: [], unknown: false },
  };
  try {
    const result = await api.searchReviews(courseCode, null);
    courseReviews.value = {
      ...courseReviews.value,
      [courseCode]: {
        status: "ready",
        notes: result.items.filter((note) => note.courseCode === courseCode),
        unknown: result.status === "UNKNOWN",
      },
    };
  } catch (error) {
    courseReviews.value = {
      ...courseReviews.value,
      [courseCode]: {
        status: "error",
        notes: [],
        unknown: false,
        error: visibleError(error),
      },
    };
  }
}

/** 推荐依据里「查看评价原文」展开时调用：已经读到过就不重复请求。 */
function onReviewBasisLoad(courseCode: string) {
  if (courseReviews.value[courseCode]?.status === "ready") return;
  void loadCourseEvidence(courseCode);
}

/** 按老师读取评价：键为 课程号::教师键。只保留这门课、且 teacherKey 完全一致的记录。 */
const teacherReviews = ref<
  Record<
    string,
    {
      status: "loading" | "ready" | "error";
      notes: ReviewNote[];
      unknown: boolean;
    }
  >
>({});

function teacherReviewKey(courseCode: string, teacherKey: string): string {
  return `${courseCode}::${teacherKey}`;
}

async function loadTeacherEvidence(courseCode: string, teacherKey: string) {
  const key = teacherReviewKey(courseCode, teacherKey);
  if (teacherReviews.value[key]?.status === "loading") return;
  teacherReviews.value = {
    ...teacherReviews.value,
    [key]: { status: "loading", notes: [], unknown: false },
  };
  try {
    const result = await api.searchReviews(courseCode, teacherKey);
    teacherReviews.value = {
      ...teacherReviews.value,
      [key]: {
        status: "ready",
        notes: teacherReviewNotes(result.items, courseCode, teacherKey),
        unknown: result.status === "UNKNOWN",
      },
    };
  } catch {
    teacherReviews.value = {
      ...teacherReviews.value,
      [key]: { status: "error", notes: [], unknown: false },
    };
  }
}

/** 展开「评价」时才读取课程级与本班教师的评价，收起不发请求。 */
function onEvidenceToggle(card: PlanCourseCard, event: globalThis.Event) {
  const target = event.target as { open?: boolean } | null;
  const open = target?.open === true;
  if (!open) return;
  void loadCourseEvidence(card.courseCode);
  if (card.teacherKey !== null) {
    void loadTeacherEvidence(card.courseCode, card.teacherKey);
  }
}

/** 课程级评价里没有绑定老师的那部分（规则在 domain/review-summary.ts）。 */
function unboundNotesOf(courseCode: string): ReviewNote[] {
  return unboundReviewNotes(
    courseReviews.value[courseCode]?.notes ?? [],
    courseCode,
  );
}

/** 同一课程里已绑定到其他老师的评价条数，课程级区块要说明它们存在但不混入。 */
function boundElsewhereCount(card: PlanCourseCard): number {
  return (courseReviews.value[card.courseCode]?.notes ?? []).filter(
    (note) => note.teacherKey !== null && note.teacherKey !== card.teacherKey,
  ).length;
}

/** 删除课程正在请求的那一门；同一时间只允许一个删除请求。 */
const deleting = ref<{ planId: string; courseCode: string } | null>(null);
/** 删除失败的提示，按「原推荐的 planId」保存；原方案保留，不清空。 */
const deleteErrors = ref<Record<string, string>>({});
/** 删除后仍在新方案里的课程提示，按「原推荐的 planId」保存。 */
const deleteNotes = ref<Record<string, string>>({});
let deleteController: AbortController | null = null;
let deleteVersion = 0;
let deleteKey: string | null = null;
let deleteKeyFor: string | null = null;

/** 课程卡片的展示数据。教师与时间只取班次资料里的真实字段，不显示内部标识。 */
interface PlanCourseCard {
  courseCode: string;
  name: string | null;
  credits: number | null;
  /** 培养方案类别映射出的「必修 / 选修」标签；取不到类别时为 null。 */
  tag: "必修" | "选修" | null;
  classId: string | null;
  teacher: string;
  /** 班次资料里的教师键（与评价的 teacherKey 对应）；没有班次资料时为 null。 */
  teacherKey: string | null;
  time: string;
  rationale: NonNullable<Recommendation["courseRationales"]>[number] | null;
  rationaleWasReused: boolean;
  rationaleWasChanged: boolean;
}

function cardsOf(entry: PlanEntry): PlanCourseCard[] {
  const sources = sourcesOf(entry.plan.planId);
  return entry.plan.items.map((item) => {
    const source =
      sources?.find((candidate) => candidate.courseCode === item.courseCode) ??
      null;
    const offering = source?.offering ?? null;
    const originalItem = entry.recommendation.items.find(
      (candidate) => candidate.courseCode === item.courseCode,
    );
    const rationaleWasChanged =
      originalItem !== undefined &&
      (originalItem.classId !== item.classId ||
        originalItem.teacherKey !== item.teacherKey);
    const rationale = rationaleWasChanged
      ? null
      : (entry.recommendation.courseRationales?.find(
          (candidate) => candidate.courseCode === item.courseCode,
        ) ?? null);
    let teacher: string;
    let time: string;
    if (item.classId === null) {
      teacher = "尚未选定班次";
      time = "尚未选定班次，时间未定";
    } else if (sources === null) {
      teacher = "正在读取…";
      time = "正在读取上课时间…";
    } else if (offering === null) {
      teacher = "班次资料没读到，无法显示";
      time = "班次资料没读到，时间未知";
    } else {
      teacher = offering.teacherText.trim() || "教师未填写";
      time =
        offering.parseStatus === "PARSED"
          ? meetingsText(offering.meetings)
          : "上课时间未能解析，无法确认";
    }
    return {
      courseCode: item.courseCode,
      name: courseNames.value[item.courseCode] ?? null,
      credits: courseCredits.value[item.courseCode] ?? null,
      tag: requirementTag(courseCategories.value[item.courseCode]),
      classId: item.classId,
      teacher,
      teacherKey: offering?.teacherKey ?? null,
      time,
      rationale,
      rationaleWasReused:
        entry.plan.replacedFrom !== null && rationale !== null,
      rationaleWasChanged,
    };
  });
}

function isDeletingPlan(entry: PlanEntry): boolean {
  return deleting.value?.planId === entry.plan.planId;
}

async function deleteCourse(entry: PlanEntry, courseCode: string) {
  if (deleting.value !== null) return;
  const recommendationId = entry.recommendation.planId;
  const planId = entry.plan.planId;
  const name = courseNames.value[courseCode] ?? courseCode;
  const version = ++deleteVersion;
  deleteController?.abort();
  const controller = new AbortController();
  deleteController = controller;
  // 同一门课、同一份方案的重试复用幂等键；换了就换新键。
  const requestKey = `${planId}|${courseCode}`;
  if (deleteKeyFor !== requestKey) {
    deleteKey = newIdempotencyKey();
    deleteKeyFor = requestKey;
  }
  const key = deleteKey ?? newIdempotencyKey();
  deleting.value = { planId, courseCode };
  deleteErrors.value = { ...deleteErrors.value, [recommendationId]: "" };
  deleteNotes.value = { ...deleteNotes.value, [recommendationId]: "" };

  try {
    const answer = await api.removeSessionPlanCourse(
      { previousPlanId: planId, courseCode },
      key,
      controller.signal,
    );
    if (version !== deleteVersion) return;

    store.applyPlanEdit(recommendationId, answer);
    deleteKeyFor = null;
    deleteErrors.value = { ...deleteErrors.value, [recommendationId]: "" };
    if (answer.empty)
      deleteNotes.value = {
        ...deleteNotes.value,
        [recommendationId]:
          "课程已移除。当前方案为空，尚无核验结果；你可以返回问卷重新生成方案。",
      };
    panel.value = null;
    resetSearch();
  } catch (error) {
    if (version !== deleteVersion || isAborted(error)) return;
    deleteErrors.value = {
      ...deleteErrors.value,
      [recommendationId]: `${visibleError(error)} 删除${name}没有生效，原方案保留，可以再试一次。`,
    };
  } finally {
    if (version === deleteVersion) deleting.value = null;
  }
}

/* ---------- 搜索班次与替换 ---------- */

/** 已选课程的已知时段，用于搜索时的预览比较。 */
interface KnownPlanMeeting {
  courseCode: string;
  meetings: Meeting[];
}

interface OfferingRow {
  classId: string;
  kind: "clear" | "conflict" | "unknown";
  /** 冲突或无法确认时显示在禁用按钮上；可选时按钮文字是「选这个班次」。 */
  label: string;
  note: string;
  noteId: string;
  timeText: string;
  teacherText: string;
}

/** 当前展开的面板：某门课的换班，或加课搜索。同一时间只开一个。 */
interface OpenPanel {
  planId: string;
  mode: "swap" | "add";
  courseCode: string | null;
}
const panel = ref<OpenPanel | null>(null);
const courseInput = ref("");
const searchStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
const searchError = ref("");
/** 课程名匹配到多门时，列出来让学生点选（不猜）。 */
const courseChoices = ref<Course[]>([]);
const searchedCourse = ref<string | null>(null);
const offerings = ref<CourseOffering[]>([]);
/** 班次资料是 UNKNOWN（快照缺失或非当前）：空列表不能说成「没有班次」。 */
const offeringsUnconfirmed = ref(false);
/** Java 对每个候选班次的硬时间约束核对（必避时段）。 */
const mustAvoidChecks = ref<MustAvoidCheck[]>([]);
const knownPlanMeetings = ref<KnownPlanMeeting[]>([]);
const planGaps = ref<string[]>([]);
const selectedClassId = ref<string | null>(null);
const replaceStatus = ref<"idle" | "submitting" | "error">("idle");
const replaceError = ref("");

let searchController: AbortController | null = null;
let replaceController: AbortController | null = null;
let searchVersion = 0;
let replaceVersion = 0;
let replaceKey: string | null = null;

function newIdempotencyKey(): string {
  return `web-${crypto.randomUUID().replaceAll("-", "")}`;
}

function visibleError(error: unknown): string {
  if (error instanceof ApiFailure) return error.message;
  return "暂时无法完成请求，请稍后重试。";
}

function isAborted(error: unknown): boolean {
  return error instanceof ApiFailure && error.kind === "aborted";
}

function clearSelection() {
  replaceVersion += 1;
  replaceController?.abort();
  replaceController = null;
  selectedClassId.value = null;
  replaceKey = null;
  replaceStatus.value = "idle";
  replaceError.value = "";
}

function resetSearch() {
  searchVersion += 1;
  searchController?.abort();
  searchController = null;
  searchStatus.value = "idle";
  searchError.value = "";
  searchedCourse.value = null;
  offerings.value = [];
  offeringsUnconfirmed.value = false;
  knownPlanMeetings.value = [];
  planGaps.value = [];
  clearSelection();
}

function resetPlanEdits() {
  panel.value = null;
  resetSearch();
}

/* ---------- 方案课表 ---------- */

/**
 * 每份方案的课表来源，按 planId 保存。加载中不画课表（不能把「还没读到」画成「没有课」）。
 * epoch 每次结果换掉都会增加，迟到的旧请求结果因此被丢弃。
 */
type TimetableState =
  | { status: "loading" }
  | { status: "ready"; sources: TimetableSource[] };
const timetables = ref<Record<string, TimetableState>>({});
let timetableEpoch = 0;

/** 读取一份方案里每门已选班次所在课程的班次资料，用来找出它的上课时段。 */
async function loadTimetable(plan: PlanView) {
  const planId = plan.planId;
  const epoch = timetableEpoch;
  timetables.value = { ...timetables.value, [planId]: { status: "loading" } };
  const codes = [
    ...new Set(
      plan.items
        .filter((item) => item.classId !== null)
        .map((item) => item.courseCode),
    ),
  ];
  const settled = await Promise.all(
    codes.map(async (code): Promise<[string, OfferingListRead | null]> => {
      try {
        const list = await api.searchSessionOfferings(planId, code);
        return [code, { status: list.status, items: list.items }];
      } catch {
        // 读取失败就按「读不到」处理：对应的课不画进课表，并说明原因。
        return [code, null];
      }
    }),
  );
  if (epoch !== timetableEpoch) return;
  const lists: Record<string, OfferingListRead | undefined> = {};
  for (const [code, list] of settled) {
    if (list !== null) lists[code] = list;
  }
  timetables.value = {
    ...timetables.value,
    [planId]: {
      status: "ready",
      sources: resolveTimetableSources(plan.items, lists),
    },
  };
}

function ensureTimetables() {
  for (const entry of planEntries.value) {
    if (timetables.value[entry.plan.planId] === undefined) {
      void loadTimetable(entry.plan);
    }
  }
}

function sourcesOf(planId: string): TimetableSource[] | null {
  const state = timetables.value[planId];
  return state?.status === "ready" ? state.sources : null;
}

// 结果换了（重新提交或新答复），之前的替换和搜索都不再适用。
watch(
  () => store.planningResult,
  () => {
    resetPlanEdits();
    deleteVersion += 1;
    deleteController?.abort();
    deleteController = null;
    deleteKey = null;
    deleteKeyFor = null;
    deleting.value = null;
    deleteErrors.value = {};
    deleteNotes.value = {};
    courseReviews.value = {};
    timetableEpoch += 1;
    timetables.value = {};
    ensureTimetables();
    clarificationChoice.value = "";
    clarificationText.value = "";
  },
);

// 替换班次后出现新的 planId，需要为新版本读取课表。
watch(planEntries, () => ensureTimetables(), { immediate: true });

// 课程名按方案所用的培养方案读取；同一方案不重复读。
watch(
  () => result.value?.academicAudit.curriculumSnapshotId ?? null,
  (curriculumSnapshotId) => {
    if (curriculumSnapshotId !== null)
      void loadCourseNames(curriculumSnapshotId);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  searchController?.abort();
  replaceController?.abort();
  deleteController?.abort();
});

function panelId(index: number): string {
  return `result-panel-${index}`;
}
function courseInputId(index: number): string {
  return `result-search-course-${index}`;
}
function swapButtonId(index: number, courseCode: string): string {
  return `result-swap-${index}-${courseCode}`;
}
function planTitleId(index: number): string {
  return `result-plan-title-${index}`;
}
function addTitleId(index: number): string {
  return `result-add-title-${index}`;
}
function verdictId(index: number): string {
  return `result-verdict-${index}`;
}
const focusTargets = new Map<string, HTMLElement>();

/** 记录需要聚焦的按钮和输入框；不直接访问 document，保持页面只依赖 Vue 的引用。 */
function registerFocus(id: string, element: unknown) {
  if (element instanceof HTMLElement) focusTargets.set(id, element);
  else focusTargets.delete(id);
}

function focusById(id: string) {
  void nextTick(() => focusTargets.get(id)?.focus());
}

function isSwapOpen(entry: PlanEntry, courseCode: string): boolean {
  return (
    panel.value?.planId === entry.recommendation.planId &&
    panel.value.mode === "swap" &&
    panel.value.courseCode === courseCode
  );
}

function isAddOpen(entry: PlanEntry): boolean {
  return (
    panel.value?.planId === entry.recommendation.planId &&
    panel.value.mode === "add"
  );
}

/** 收起面板，并把焦点还给触发它的按钮。 */
function closePanel(entry: PlanEntry) {
  const previous = panel.value;
  panel.value = null;
  resetSearch();
  if (previous?.mode === "swap" && previous.courseCode !== null) {
    focusById(swapButtonId(entry.index, previous.courseCode));
  } else {
    focusById(courseInputId(entry.index));
  }
}

/** 开始一次搜索：作废上一次未完成的搜索与替换。 */
function beginSearch(): { version: number; controller: AbortController } {
  const version = ++searchVersion;
  searchController?.abort();
  const controller = new AbortController();
  searchController = controller;
  clearSelection();
  searchStatus.value = "loading";
  searchError.value = "";
  return { version, controller };
}

/** 换班：在卡片下方列出这门课的全部班次（与方案其他课程比较冲突）。再点一次收起。 */
function toggleSwap(entry: PlanEntry, courseCode: string) {
  if (isSwapOpen(entry, courseCode)) {
    closePanel(entry);
    return;
  }
  const { version, controller } = beginSearch();
  panel.value = {
    planId: entry.recommendation.planId,
    mode: "swap",
    courseCode,
  };
  void loadOfferings(entry, courseCode, version, controller);
}

/** 两段时段冲突 = 同一星期、节次区间相交、且周次有交集。周次不相交的单双周课不冲突。 */
function meetingsOverlap(a: Meeting, b: Meeting): boolean {
  return (
    a.dayOfWeek === b.dayOfWeek &&
    a.sectionStart <= b.sectionEnd &&
    b.sectionStart <= a.sectionEnd &&
    a.weeks.some((week) => b.weeks.includes(week))
  );
}

/** 加课搜索：按课程名或课程号解析出一门课，再列出它的班次。 */
async function runSearch(entry: PlanEntry) {
  const typed = courseInput.value.trim();
  panel.value = {
    planId: entry.recommendation.planId,
    mode: "add",
    courseCode: null,
  };
  if (typed === "") {
    searchStatus.value = "error";
    searchError.value = "请先输入课程名或课程号。";
    return;
  }
  const { version, controller } = beginSearch();

  let course: string;
  try {
    const snapshotId = result.value?.academicAudit.curriculumSnapshotId ?? null;
    const resolved = await resolveCourseQuery(
      typed,
      snapshotId === null
        ? null
        : async (text) =>
            (await api.listCourses(snapshotId, null, controller.signal, text))
              .items,
    );
    if (version !== searchVersion) return;
    if (!resolved.ok) {
      searchStatus.value = "error";
      searchError.value = resolved.message;
      courseChoices.value = resolved.candidates;
      return;
    }
    courseChoices.value = [];
    course = resolved.code;
  } catch (error) {
    if (version !== searchVersion || isAborted(error)) return;
    searchStatus.value = "error";
    searchError.value = visibleError(error);
    return;
  }
  await loadOfferings(entry, course, version, controller);
}

/**
 * 读取一门课的班次，并与方案中其他已选班次比较时间（只是预览）。
 * 换班与加课共用这一段；version 过期时结果被丢弃。
 */
async function loadOfferings(
  entry: PlanEntry,
  course: string,
  version: number,
  controller: AbortController,
) {
  const plan = entry.plan;
  // 方案里其他已选班次的课程：去查它们的时间，用来做搜索时的预览比较。
  const selected = plan.items.filter(
    (item) => item.classId !== null && item.courseCode !== course,
  );
  const otherCodes = [...new Set(selected.map((item) => item.courseCode))];
  try {
    const [target, otherLists] = await Promise.all([
      api.searchSessionOfferings(plan.planId, course, controller.signal),
      Promise.all(
        otherCodes.map((code) =>
          api.searchSessionOfferings(plan.planId, code, controller.signal),
        ),
      ),
    ]);
    if (version !== searchVersion) return;

    const known: KnownPlanMeeting[] = [];
    const gaps: string[] = [];
    for (const item of selected) {
      const list = otherLists[otherCodes.indexOf(item.courseCode)];
      const found = list?.items.find(
        (candidate) => candidate.classId === item.classId,
      );
      if (
        found === undefined ||
        found.parseStatus !== "PARSED" ||
        found.meetings.length === 0
      ) {
        gaps.push(item.courseCode);
      } else {
        known.push({ courseCode: item.courseCode, meetings: found.meetings });
      }
    }
    offerings.value = target.items;
    mustAvoidChecks.value = target.mustAvoidChecks;
    offeringsUnconfirmed.value = target.status === "UNKNOWN";
    knownPlanMeetings.value = known;
    planGaps.value = gaps;
    searchedCourse.value = course;
    searchStatus.value = "ready";
  } catch (error) {
    if (version !== searchVersion || isAborted(error)) return;
    searchStatus.value = "error";
    searchError.value =
      error instanceof ApiFailure && error.status === 422
        ? "请输入课程名或课程号，从列表中选择课程。"
        : visibleError(error);
  }
}

/** 从候选列表里点选一门课，直接用它的课程号查班次。 */
function chooseCourse(entry: PlanEntry, code: string) {
  courseInput.value = code;
  void runSearch(entry);
}

/**
 * 按已知时间判断一个班次。只是预览：时间未知不能当成没有冲突。
 * 只有「班次资料已确认、本班次时间完整、方案其他课时间全部读到、且没有冲突」才给 clear，
 * 与 answer-display.ts 的门禁一致：确定的结论才给绿色，其余一律落到无法确认。
 */
/**
 * 候选班次的必避时段核对结果。null 表示学生没有设定必避时段，不需要核对；
 * NOT_CHECKED 表示设定了必避时段，但服务端没有给出这个班次的核对结果，不能当作无冲突。
 */
type MustAvoidState = MustAvoidVerdict | "NOT_CHECKED" | null;

function mustAvoidStateOf(classId: string): MustAvoidState {
  const check = mustAvoidChecks.value.find((item) => item.classId === classId);
  if (check !== undefined) return check.verdict;
  return store.draft.mustSlots.length > 0 ? "NOT_CHECKED" : null;
}

function judgeOffering(
  offering: CourseOffering,
  listUnconfirmed: boolean,
  gapCodes: readonly string[],
  mustAvoid: MustAvoidState,
): Pick<OfferingRow, "kind" | "note"> {
  // 必避时段的判决来自 Java（经 Python 的 session-offerings），这里只翻译，不算时间。
  if (mustAvoid === "CONFLICT") {
    return {
      kind: "conflict",
      note: "与你设定的必避时段冲突（已由服务端核对，不能选择这个班次）。",
    };
  }
  if (offering.parseStatus !== "PARSED" || offering.meetings.length === 0) {
    return {
      kind: "unknown",
      note: "上课时间没有解析成功，无法判断是否冲突，不能直接选择。",
    };
  }
  if (offering.meetings.some((meeting) => meeting.weeks.length === 0)) {
    return {
      kind: "unknown",
      note: "上课周次没有确认，无法判断是否冲突，不能直接选择。",
    };
  }
  const conflicts = knownPlanMeetings.value
    .filter((planned) =>
      planned.meetings.some((theirs) =>
        offering.meetings.some((mine) => meetingsOverlap(mine, theirs)),
      ),
    )
    .map((planned) => planned.courseCode);
  if (conflicts.length > 0) {
    return {
      kind: "conflict",
      note: `与方案中已选的 ${conflicts.join("、")} 时间重叠（仅为预览，提交前需整份核验）。`,
    };
  }
  if (mustAvoid === "UNKNOWN") {
    return {
      kind: "unknown",
      note: "无法确认是否与你设定的必避时段冲突，不能直接选择。",
    };
  }
  if (mustAvoid === "NOT_CHECKED") {
    return {
      kind: "unknown",
      note: "还没有核对这个班次与你设定的必避时段，不能直接选择。",
    };
  }
  if (listUnconfirmed) {
    return {
      kind: "unknown",
      note: "班次资料无法确认（快照缺失或不是当前版本），不能直接选择。",
    };
  }
  if (gapCodes.length > 0) {
    return {
      kind: "unknown",
      note: `方案中 ${gapCodes.join("、")} 的时间没能读到，无法判断是否与它们冲突，不能直接选择。`,
    };
  }
  return {
    kind: "clear",
    note:
      mustAvoid === "CLEAR"
        ? "与你设定的必避时段没有冲突（服务端核对），与方案里已选课程也没有冲突（仅为预览，提交前仍需整份核验）。"
        : "按已知时间没有发现冲突（仅为预览，提交前仍需整份核验）。",
  };
}

const offeringRows = computed<OfferingRow[]>(() =>
  offerings.value.map((offering, index) => {
    const judged = judgeOffering(
      offering,
      offeringsUnconfirmed.value,
      planGaps.value,
      mustAvoidStateOf(offering.classId),
    );
    return {
      classId: offering.classId,
      kind: judged.kind,
      label:
        judged.kind === "conflict"
          ? "有冲突"
          : judged.kind === "unknown"
            ? "无法确认"
            : "选这个班次",
      note: judged.note,
      noteId: `result-offering-note-${index}`,
      timeText: offering.meetingTextRaw.trim() || "时间未填写",
      teacherText: offering.teacherText,
    };
  }),
);

const selectedOffering = computed<CourseOffering | null>(
  () =>
    offerings.value.find((item) => item.classId === selectedClassId.value) ??
    null,
);

function selectOffering(classId: string) {
  if (replaceStatus.value === "submitting") return;
  selectedClassId.value = classId;
  replaceKey = newIdempotencyKey();
  replaceStatus.value = "idle";
  replaceError.value = "";
}

function replacePreview(entry: PlanEntry, classId: string): string {
  const item = entry.plan.items.find(
    (candidate) => candidate.courseCode === searchedCourse.value,
  );
  if (item === undefined) {
    return `已选 ${classId}，但当前方案里没有这门课，替换可能会被拒绝。`;
  }
  const current =
    item.classId === null
      ? `${item.courseCode}（未选班次）`
      : `${item.courseCode} ${item.classId}`;
  return `已选 ${classId} 替换 ${current}`;
}

/** 重新核验 = 对整份新方案调用替换接口。请求进行中再点直接忽略。 */
async function recheck(entry: PlanEntry) {
  if (replaceStatus.value === "submitting") return;
  const course = searchedCourse.value;
  const classId = selectedClassId.value;
  if (course === null || classId === null) return;

  const version = ++replaceVersion;
  replaceController?.abort();
  const controller = new AbortController();
  replaceController = controller;
  const key = replaceKey ?? newIdempotencyKey();
  replaceKey = key;
  replaceStatus.value = "submitting";
  replaceError.value = "";
  try {
    const replaced = await api.replaceSessionPlanItem(
      {
        previousPlanId: entry.plan.planId,
        courseCode: course,
        selectedClassId: classId,
      },
      key,
      controller.signal,
    );
    if (version !== replaceVersion) return;
    store.applyPlanEdit(entry.recommendation.planId, {
      ...replaced,
      empty: false,
    });
    panel.value = null;
    resetSearch();
    focusById(swapButtonId(entry.index, course));
  } catch (error) {
    if (version !== replaceVersion || isAborted(error)) return;
    replaceStatus.value = "error";
    replaceError.value = visibleError(error);
  }
}

async function goBackToQuestions() {
  await router.push("/plan/questions/ready");
}
</script>

<template>
  <section class="result-page" aria-labelledby="result-title">
    <p class="eyebrow">下学期选课规划</p>
    <h1 id="result-title" tabindex="-1">{{ headline }}</h1>

    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      演示模式 · 虚构内容，不代表任何真实课程或核验结果。
    </p>
    <p v-else-if="planIsSimulated" class="notice notice--demo" role="note">
      本地测试服务 · 模拟班次不代表下学期开课情况，培养资料来源见所选方案。
    </p>

    <p
      v-if="store.submitStatus === 'submitting'"
      class="notice"
      role="status"
      aria-live="polite"
    >
      正在规划，请稍候。这一步不会重复提交。
    </p>

    <p
      v-else-if="store.submitStatus === 'error'"
      class="notice notice--error"
      role="alert"
    >
      {{ store.submitError }}
    </p>

    <p v-else-if="!result" class="notice notice--warning" role="note">
      还没有提交规划请求。回到上一页检查资料后再提交。
    </p>

    <template v-else>
      <div
        v-if="result.decision === 'CLARIFY' && result.clarification"
        class="option-section"
      >
        <h2 class="sub-label">{{ result.clarification.text }}</h2>
        <ul v-if="result.clarification.choices.length" class="summary-list">
          <li
            v-for="choice in result.clarification.choices"
            :key="choice.value"
          >
            {{ choice.label }}
          </li>
        </ul>
        <p v-else class="microcopy">可以补充文字说明。</p>
        <p v-if="tradeoffChoices.length === 2" class="microcopy">
          这个选择只记录教师与时间的优先顺序，不会取消任何 MUST
          教师或必须避开的时段；若两者冲突，仍由核验结果如实说明。
        </p>
        <div v-if="tradeoffChoices.length === 2" class="question-nav">
          <button
            v-for="choice in tradeoffChoices"
            :key="choice.value"
            class="button button--primary"
            type="button"
            :disabled="answeringTradeoff"
            @click="
              answerTradeoff(result.clarification!.questionId, choice.value)
            "
          >
            {{ choice.label }}并继续规划
          </button>
        </div>
        <div
          v-if="
            tradeoffChoices.length !== 2 &&
            !clarificationRequiresQuestionnaire &&
            (result.clarification.choices.length ||
              result.clarification.allowFreeText)
          "
          class="clarification-answer"
        >
          <label
            v-if="result.clarification.choices.length"
            class="field-label"
            :for="`clarification-choice-${result.clarification.questionId}`"
          >
            选择一个选项
          </label>
          <select
            v-if="result.clarification.choices.length"
            :id="`clarification-choice-${result.clarification.questionId}`"
            v-model="clarificationChoice"
            class="text-control"
          >
            <option value="">请选择</option>
            <option
              v-for="choice in result.clarification.choices"
              :key="choice.value"
              :value="choice.value"
            >
              {{ choice.label }}
            </option>
          </select>
          <label
            v-if="result.clarification.allowFreeText"
            class="field-label"
            :for="`clarification-text-${result.clarification.questionId}`"
          >
            补充说明
          </label>
          <textarea
            v-if="result.clarification.allowFreeText"
            :id="`clarification-text-${result.clarification.questionId}`"
            v-model="clarificationText"
            class="text-control"
            maxlength="2000"
            rows="3"
          />
          <button
            class="button button--primary"
            type="button"
            :disabled="answeringTradeoff"
            @click="
              answerGeneralClarification(result.clarification!.questionId)
            "
          >
            回答并继续规划
          </button>
        </div>
        <p v-else-if="clarificationRequiresQuestionnaire" class="microcopy">
          此问题需要更新结构化选课目标，请返回问卷修改后重新提交。
        </p>
        <p v-else-if="tradeoffChoices.length !== 2" class="microcopy">
          此问题没有可用的选项或文字回答入口，请回到问卷修改条件后再提交。
        </p>
        <p
          v-if="store.clarificationError"
          class="notice notice--error"
          role="alert"
        >
          {{ store.clarificationError }}
        </p>
      </div>

      <div v-else-if="planEntries.length" class="result-plans">
        <section
          v-for="entry in planEntries"
          :key="entry.recommendation.planId"
          class="plan-block"
          :aria-labelledby="planTitleId(entry.index)"
        >
          <div class="plan-bar">
            <h2
              :id="planTitleId(entry.index)"
              class="plan-bar__title"
              :title="entry.plan.planId"
            >
              方案 {{ entry.index + 1 }}
            </h2>
            <div
              v-if="badgesOf(entry).length"
              class="verdict-badges"
              role="group"
              aria-label="核验结论"
            >
              <button
                v-for="badge in badgesOf(entry)"
                :key="badge.scope"
                class="verdict-badge"
                :class="`verdict-badge--${badge.tone}`"
                type="button"
                :aria-expanded="isVerdictOpen(entry) ? 'true' : 'false'"
                :aria-controls="verdictId(entry.index)"
                @click="toggleVerdict(entry)"
              >
                {{ badge.label }}
              </button>
            </div>
          </div>
          <p class="result-note">
            班次搜索里的「冲突」「无法确认」只是预览；换班或加课后，以整份方案的重新核验为准。
          </p>

          <div
            v-if="isVerdictOpen(entry)"
            :id="verdictId(entry.index)"
            class="verdict-details"
          >
            <ul
              v-if="
                entry.plan.verification && hasSections(entry.plan.verification)
              "
              class="summary-list"
              aria-label="两个分项的结论"
            >
              <li
                v-for="section in sectionsOf(entry.plan.verification)"
                :key="section.scope"
              >
                {{ SECTION_TITLE[section.scope] }}：{{
                  verdictBadge(section.verdict)
                }}
              </li>
            </ul>
            <p v-if="entry.view" class="microcopy">
              {{
                entry.plan.verification && hasSections(entry.plan.verification)
                  ? `总体：${entry.view.label}（取两项中较差的结果）`
                  : `${entry.view.label}：${entry.view.detail}`
              }}
            </p>
            <ul
              v-if="groupsOf(entry).planLevel.length"
              class="summary-list"
              aria-label="方案级问题"
            >
              <li v-for="line in groupsOf(entry).planLevel" :key="line.key">
                {{ line.text }}
              </li>
            </ul>
            <p v-else class="microcopy">没有需要单独说明的方案级问题。</p>
          </div>

          <div
            v-if="entry.plan.empty"
            class="notice notice--warning"
            role="status"
          >
            <strong>空方案，尚无核验结果</strong>
            <p class="microcopy">
              课程已从方案中移除。返回问卷后可以重新生成方案。
            </p>
          </div>
          <p v-if="entry.plan.replacedFrom" class="microcopy">
            这是调整后重新核验的新版本。下面的核验结论只针对这一版。
          </p>
          <p v-if="courseNamesStatus === 'error'" class="microcopy" role="note">
            课程名称暂时读不到，下面显示的是课程号。
          </p>
          <p
            v-if="isDeletingPlan(entry)"
            class="notice"
            role="status"
            aria-live="polite"
          >
            正在重新核验整份方案，请稍候。这一步不会重复提交。
          </p>
          <p
            v-else-if="deleteErrors[entry.recommendation.planId]"
            class="notice notice--error"
            role="alert"
          >
            {{ deleteErrors[entry.recommendation.planId] }}
          </p>
          <p
            v-if="deleteNotes[entry.recommendation.planId]"
            class="notice notice--warning"
            role="note"
          >
            {{ deleteNotes[entry.recommendation.planId] }}
          </p>

          <div
            v-if="entry.plan.items.length > 0"
            class="plan-grid"
            :class="{ 'plan-grid--split': wideLayout }"
          >
            <aside class="plan-grid__timetable" aria-label="一周课表">
              <h3 class="sub-label">一周课表</h3>
              <PlanTimetable
                v-if="entry.plan.verification && sourcesOf(entry.plan.planId)"
                :scope="entry.plan.verification.scope"
                :sources="sourcesOf(entry.plan.planId) ?? []"
                :course-names="courseNames"
                :unplaced-reasons="unplacedReasons"
              />
              <p v-else class="microcopy" role="status" aria-live="polite">
                正在读取班次时间，请稍候。
              </p>
            </aside>

            <div class="plan-grid__courses">
              <section
                class="add-course"
                :aria-labelledby="addTitleId(entry.index)"
              >
                <h3 :id="addTitleId(entry.index)" class="sub-label">加课</h3>
                <form
                  class="search-form"
                  role="search"
                  @submit.prevent="runSearch(entry)"
                >
                  <label class="field-label" :for="courseInputId(entry.index)">
                    课程名或课程号（本学期开课）
                  </label>
                  <div class="search-row">
                    <input
                      :id="courseInputId(entry.index)"
                      :ref="
                        (el) => registerFocus(courseInputId(entry.index), el)
                      "
                      v-model="courseInput"
                      class="text-control"
                      type="search"
                      maxlength="32"
                      autocomplete="off"
                      placeholder="例如 数据库 或 CS103"
                    />
                    <button
                      class="button button--primary"
                      type="submit"
                      :disabled="searchStatus === 'loading'"
                    >
                      搜索
                    </button>
                  </div>
                </form>

                <template v-if="isAddOpen(entry)">
                  <p
                    v-if="searchStatus === 'loading'"
                    class="notice"
                    role="status"
                    aria-live="polite"
                  >
                    正在查找班次，请稍候。
                  </p>
                  <p
                    v-else-if="searchStatus === 'error'"
                    class="notice notice--error"
                    role="alert"
                  >
                    {{ searchError
                    }}<template v-if="!courseChoices.length">
                      可以稍后再试一次。</template
                    >
                  </p>
                  <ul
                    v-if="searchStatus === 'error' && courseChoices.length"
                    class="course-choices"
                    aria-label="匹配的课程"
                  >
                    <li
                      v-for="choice in courseChoices"
                      :key="choice.courseCode"
                    >
                      <button
                        class="button button--secondary"
                        type="button"
                        @click="chooseCourse(entry, choice.courseCode)"
                      >
                        {{ choice.courseCode }} · {{ choice.name }}
                      </button>
                    </li>
                  </ul>
                  <template v-if="searchStatus === 'ready' && searchedCourse">
                    <h4 class="sub-label">{{ searchedCourse }} 的开课班次</h4>
                    <OfferingResults
                      mode="add"
                      :course-code="searchedCourse"
                      :rows="offeringRows"
                      :unconfirmed="offeringsUnconfirmed"
                      :gap-codes="planGaps"
                      :current-class-id="null"
                      :selected-class-id="null"
                      :preview-text="''"
                      :replace-status="replaceStatus"
                      :replace-error="replaceError"
                    />
                  </template>
                  <button
                    class="button button--quiet"
                    type="button"
                    @click="closePanel(entry)"
                  >
                    收起加课搜索
                  </button>
                </template>
              </section>

              <ul class="course-cards" aria-label="方案中的课程">
                <li
                  v-for="(card, cardIndex) in cardsOf(entry)"
                  :key="`${card.courseCode}-${cardIndex}`"
                  class="course-card"
                >
                  <div class="course-card__head">
                    <div class="course-card__title">
                      <strong>{{ card.name ?? card.courseCode }}</strong>
                      <span class="course-card__code">
                        {{ card.courseCode }}
                        <template v-if="card.credits !== null">
                          · {{ card.credits }} 学分
                        </template>
                      </span>
                    </div>
                    <span
                      v-if="card.tag"
                      class="tag"
                      :class="
                        card.tag === '必修' ? 'tag--required' : 'tag--elective'
                      "
                    >
                      {{ card.tag }}
                    </span>
                  </div>
                  <dl class="course-card__facts">
                    <div>
                      <dt>教师</dt>
                      <dd>{{ card.teacher }}</dd>
                    </div>
                    <div>
                      <dt>时间</dt>
                      <dd>{{ card.time }}</dd>
                    </div>
                    <div v-if="card.classId !== null">
                      <dt>班次</dt>
                      <dd class="course-card__small">{{ card.classId }}</dd>
                    </div>
                  </dl>

                  <ul
                    v-if="issuesOfCourse(entry, card.courseCode).length"
                    class="course-card__issues"
                    aria-label="这门课的问题"
                  >
                    <li
                      v-for="line in issuesOfCourse(entry, card.courseCode)"
                      :key="line.key"
                      :class="`issue--${line.kind}`"
                    >
                      {{ line.text }}
                    </li>
                  </ul>

                  <p v-if="card.rationaleWasReused" class="microcopy">
                    以下理由来自原推荐；方案调整后未重新生成。
                  </p>
                  <details class="card-basis">
                    <summary>推荐依据与课程来源</summary>
                    <CourseReviewBasis
                      :course-code="card.courseCode"
                      :review-status="
                        courseReviews[card.courseCode]?.status ?? null
                      "
                      :review-error="
                        courseReviews[card.courseCode]?.error ?? ''
                      "
                      :reason="
                        card.rationale?.reason ??
                        (card.rationaleWasChanged
                          ? '班次已调整，此版本未生成新的推荐理由。'
                          : '暂无具体理由。')
                      "
                      :course-source-ref-ids="
                        card.rationale?.courseSourceRefIds ?? []
                      "
                      :review-basis-status="
                        card.rationale?.reviewBasisStatus ?? null
                      "
                      :rationale-source="
                        card.rationale?.rationaleSource ?? null
                      "
                      :review-note-ids="card.rationale?.reviewNoteIds ?? []"
                      :review-evidence-refs="
                        card.rationale?.reviewEvidenceRefs ?? []
                      "
                      :review-notes="
                        courseReviews[card.courseCode]?.notes ?? []
                      "
                      @load="onReviewBasisLoad(card.courseCode)"
                    />
                  </details>
                  <details @toggle="onEvidenceToggle(card, $event)">
                    <summary>查看评价维度汇总与资料</summary>
                    <p
                      v-if="
                        !courseReviews[card.courseCode] ||
                        courseReviews[card.courseCode].status === 'loading'
                      "
                    >
                      正在读取评价…
                    </p>
                    <p
                      v-else-if="
                        courseReviews[card.courseCode].status === 'error'
                      "
                    >
                      评价读取失败，请重新展开重试。
                    </p>
                    <ReviewSummary
                      v-if="
                        courseReviews[card.courseCode]?.status === 'ready' &&
                        unboundNotesOf(card.courseCode).length > 0
                      "
                      title="课程整体评价（未绑定老师）"
                      :course-code="card.courseCode"
                      :notes="unboundNotesOf(card.courseCode)"
                      :unconfirmed="courseReviews[card.courseCode].unknown"
                    />
                    <p
                      v-if="
                        card.teacherKey !== null &&
                        teacherReviews[
                          teacherReviewKey(card.courseCode, card.teacherKey)
                        ]?.status === 'loading'
                      "
                      class="microcopy"
                    >
                      正在读取本班教师的评价…
                    </p>
                    <template
                      v-if="
                        card.teacherKey !== null &&
                        teacherReviews[
                          teacherReviewKey(card.courseCode, card.teacherKey)
                        ]?.status === 'ready'
                      "
                    >
                      <ReviewSummary
                        v-if="
                          teacherReviews[
                            teacherReviewKey(card.courseCode, card.teacherKey)
                          ].notes.length > 0
                        "
                        :title="`本班教师评价（${card.teacher}）`"
                        :course-code="card.courseCode"
                        :notes="
                          teacherReviews[
                            teacherReviewKey(card.courseCode, card.teacherKey)
                          ].notes
                        "
                        :unconfirmed="
                          teacherReviews[
                            teacherReviewKey(card.courseCode, card.teacherKey)
                          ].unknown
                        "
                      />
                      <p v-else class="microcopy">
                        这位老师暂无绑定到本人的评价记录。
                      </p>
                    </template>
                    <p v-if="boundElsewhereCount(card) > 0" class="microcopy">
                      另有
                      {{ boundElsewhereCount(card) }}
                      条评价绑定到其他老师，未计入本班教师。
                    </p>
                    <p
                      v-else-if="
                        courseReviews[card.courseCode]?.status === 'ready' &&
                        !courseReviews[card.courseCode].unknown
                      "
                      class="microcopy"
                    >
                      暂无评价记录。
                    </p>
                  </details>
                  <div class="course-card__actions">
                    <button
                      :id="swapButtonId(entry.index, card.courseCode)"
                      :ref="
                        (el) =>
                          registerFocus(
                            swapButtonId(entry.index, card.courseCode),
                            el,
                          )
                      "
                      class="button button--secondary"
                      type="button"
                      :aria-expanded="
                        isSwapOpen(entry, card.courseCode) ? 'true' : 'false'
                      "
                      :aria-controls="
                        isSwapOpen(entry, card.courseCode)
                          ? panelId(entry.index)
                          : undefined
                      "
                      @click="toggleSwap(entry, card.courseCode)"
                    >
                      {{ card.classId === null ? "选班次" : "换班" }}
                      <span class="visually-hidden">
                        （{{ card.name ?? card.courseCode }}）
                      </span>
                    </button>
                    <button
                      class="button button--quiet course-card__delete"
                      type="button"
                      :disabled="deleting !== null"
                      @click="deleteCourse(entry, card.courseCode)"
                    >
                      删除这门课
                      <span class="visually-hidden">
                        （{{ card.name ?? card.courseCode }}）
                      </span>
                    </button>
                  </div>

                  <section
                    v-if="isSwapOpen(entry, card.courseCode)"
                    :id="panelId(entry.index)"
                    class="swap-panel"
                    :aria-label="`${card.name ?? card.courseCode} 的换班选项`"
                    @keydown.esc="closePanel(entry)"
                  >
                    <p
                      v-if="searchStatus === 'loading'"
                      class="notice"
                      role="status"
                      aria-live="polite"
                    >
                      正在查找班次，请稍候。
                    </p>
                    <p
                      v-else-if="searchStatus === 'error'"
                      class="notice notice--error"
                      role="alert"
                    >
                      {{ searchError }} 可以稍后再试一次。
                    </p>
                    <OfferingResults
                      v-else-if="
                        searchStatus === 'ready' &&
                        searchedCourse === card.courseCode
                      "
                      mode="swap"
                      :course-code="card.courseCode"
                      :rows="offeringRows"
                      :unconfirmed="offeringsUnconfirmed"
                      :gap-codes="planGaps"
                      :current-class-id="card.classId"
                      :selected-class-id="selectedClassId"
                      :preview-text="
                        selectedOffering
                          ? replacePreview(entry, selectedOffering.classId)
                          : ''
                      "
                      :replace-status="replaceStatus"
                      :replace-error="replaceError"
                      @select="selectOffering"
                      @recheck="recheck(entry)"
                    />
                    <button
                      class="button button--quiet"
                      type="button"
                      @click="closePanel(entry)"
                    >
                      收起
                    </button>
                  </section>
                </li>
              </ul>
            </div>
          </div>
          <p v-else class="microcopy">这份方案里还没有课程。</p>

          <p v-if="!entry.plan.replacedFrom" class="microcopy">
            {{ entry.recommendation.explanation }}
          </p>
          <section
            v-if="entry.recommendation.explorationDirections?.length"
            aria-label="发展方向探索"
          >
            <h3>职业与科研方向探索</h3>
            <p class="microcopy">以下是 AI 生成的探索建议。</p>
            <article
              v-for="direction in entry.recommendation.explorationDirections"
              :key="direction.title"
            >
              <h4>{{ direction.title }}</h4>
              <p>{{ direction.description }}</p>
              <ol>
                <li v-for="step in direction.steps" :key="step">{{ step }}</li>
              </ol>
            </article>
          </section>
          <details class="debug-id">
            <summary>排查编号与详情</summary>
            <p>
              方案编号：<code>{{ entry.plan.planId }}</code>
            </p>
            <p v-if="store.planningHandoff">
              核验模式：<code>{{ store.planningHandoff.mode }}</code>
            </p>
            <p v-if="entry.plan.verification">
              判决范围：<code>{{ entry.plan.verification.scope }}</code> ·
              判决：<code>{{ entry.plan.verification.verdict }}</code> ·
              核验编号：<code>{{
                entry.plan.verification.verifierResultId
              }}</code>
            </p>
            <p>
              课程编号：<code>{{ courseCodesOf(entry) }}</code>
            </p>
            <ul v-if="entry.plan.verification?.sourceRefIds.length">
              <li
                v-for="sourceRef in entry.plan.verification.sourceRefIds"
                :key="sourceRef"
              >
                来源编号：<code>{{ sourceRef }}</code>
              </li>
            </ul>
            <ul v-if="diagnosticsOf(entry).length">
              <li
                v-for="issue in diagnosticsOf(entry)"
                :key="issue.code + issue.message"
              >
                <strong>{{ issue.code }}</strong>
                <span v-if="issue.field"> · 字段：{{ issue.field }}</span>
                <span> · 可重试：{{ issue.retryable ? "是" : "否" }}</span>
                <p>{{ issue.message }}</p>
              </li>
            </ul>
          </details>
        </section>
      </div>
    </template>

    <nav class="question-nav" aria-label="结果导航">
      <button
        class="button button--secondary"
        type="button"
        @click="goBackToQuestions"
      >
        回去修改条件
      </button>
      <button
        v-if="
          (result && result.decision !== 'CLARIFY') ||
          store.submitStatus === 'error'
        "
        class="button button--primary"
        type="button"
        :disabled="store.submitStatus === 'submitting'"
        @click="store.submitPlan()"
      >
        重新提交
      </button>
    </nav>
  </section>
</template>

<style scoped>
/* 结果页：宽屏两栏（左课表粘性，右课程），窄屏上下排列。颜色与卡片沿用全局变量。 */
.result-page {
  min-width: 0;
}

.result-plans {
  margin-top: 8px;
}

.plan-block {
  margin-top: 30px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

.plan-block:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.plan-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 16px;
}

.plan-bar__title {
  margin: 0;
  color: var(--ink);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.4px;
}

.verdict-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.verdict-badge {
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink);
  font-size: 12px;
  font-weight: 550;
  line-height: 1.4;
}

.verdict-badge--pass {
  color: var(--green);
  background: #e7f4ec;
  border-color: #bfe0cc;
}

.verdict-badge--fail {
  color: #8b3c31;
  background: #fff4f2;
  border-color: #efc4bd;
}

.verdict-badge--pending {
  color: #875817;
  background: #fff8ed;
  border-color: #ecd6b0;
}

.verdict-details .summary-list {
  margin: 6px 0 0;
  font-size: 13px;
}

.result-note {
  margin: 8px 0 0;
  color: var(--soft);
  font-size: 12px;
}

.verdict-details {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
}

.plan-grid {
  display: grid;
  gap: 16px;
  margin-top: 16px;
  align-items: start;
}

.plan-grid__timetable,
.plan-grid__courses {
  min-width: 0;
}

.plan-grid__timetable {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
}

/* 宽屏：左课表粘在视口里，右边课程卡片可以独立滚动。 */
.plan-grid--split {
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 24px;
}

.plan-grid--split .plan-grid__timetable {
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 32px);
  overflow: auto;
}

.add-course {
  padding: 14px 16px;
  border: 1px dashed var(--line);
  border-radius: 12px;
  background: var(--canvas);
}

.search-form {
  margin: 0;
}

.search-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.search-row .text-control {
  flex: 1;
  min-width: 0;
  width: auto;
  /* 全局 .text-control 为多行文本框设置了 85px 高度，单行搜索框要压回按钮高度。 */
  min-height: 0;
  height: 43px;
  padding: 10px 12px;
}

.course-choices {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.5rem 0;
  padding: 0;
}

.course-cards {
  display: grid;
  gap: 12px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

/* 课程卡片：浅绿色圆角，沿用全局 --wash / --line。 */
.course-card {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--wash);
}

.course-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.course-card__title {
  min-width: 0;
}

.course-card__title strong {
  display: block;
  color: var(--ink);
  font-size: 16px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.course-card__code {
  display: block;
  color: var(--soft);
  font-size: 12px;
}

.tag {
  flex: none;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
}

.tag--required {
  color: var(--green);
  background: #e7f4ec;
}

.tag--elective {
  color: #3b5f8a;
  background: #eaf1f9;
}

.course-card__facts {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
}

.course-card__facts div {
  display: grid;
  grid-template-columns: 3.5em minmax(0, 1fr);
  gap: 8px;
}

.course-card__facts dt {
  color: var(--soft);
  font-size: 12px;
}

.course-card__facts dd {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.course-card__facts .course-card__small {
  color: var(--soft);
  font-size: 12px;
}

/* 课程级问题只出现在本卡片上：未排进课表用橙色，违规用红色，无法确认用橙色浅底。 */
.course-card__issues {
  margin: 10px 0 0;
  padding: 8px 10px;
  list-style: none;
  border-radius: 8px;
  color: #875817;
  background: #fff8ed;
  font-size: 12px;
}

.course-card__issues li + li {
  margin-top: 4px;
}

.course-card__issues .issue--violation {
  color: #8b3c31;
}

.card-basis {
  margin-top: 10px;
  color: var(--soft);
  font-size: 12px;
}

.card-basis summary {
  width: fit-content;
  cursor: pointer;
}

/* 课程卡片里的「查看评价」展开项：与推荐依据同样的小字，不抢课程名的视觉层级。 */
.course-card details > summary {
  width: fit-content;
  margin-top: 8px;
  color: var(--soft);
  font-size: 12px;
  cursor: pointer;
}

.course-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.course-card__delete {
  min-height: 36px;
  padding: 6px 10px;
  color: #8b3c31;
  font-size: 13px;
}

.course-card__delete:hover:not(:disabled) {
  color: #6e2e25;
}

.swap-panel {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
}

.debug-id {
  margin: 12px 0 0;
  color: var(--soft);
  font-size: 12px;
}

.debug-id summary {
  width: fit-content;
  cursor: pointer;
}

.debug-id code {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
}

@media (max-width: 540px) {
  .search-row {
    flex-direction: column;
  }
}
</style>
