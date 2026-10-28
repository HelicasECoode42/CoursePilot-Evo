<script setup lang="ts">
/**
 * 规划结果页（E-F4）。
 *
 * 前半：把 store 里的 PlanningAnswer 显示出来，颜色与文案交给 domain/answer-display.ts。
 * 后半：在结果页搜索某门课的开课班次，并替换方案里的一门课。
 *   - 搜索时的「有冲突 / 可选 / 无法确认」只是预览，不是核验结论；
 *   - 只有替换接口返回的 verification（对整份新方案的判决）才是结论，原样展示。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type {
  CourseOffering,
  Issue,
  Meeting,
  PlanItem,
  PlanValidation,
  PlanningAnswer,
  Recommendation,
  SessionPlanReplacement,
} from "../contracts";
import {
  collectUnknowns,
  describeVerification,
  type VerificationView,
} from "../domain/answer-display";
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
  verification: PlanValidation;
  /** 替换前的推荐 planId；未替换时为 null。 */
  replacedFrom: string | null;
}

interface PlanEntry {
  index: number;
  recommendation: Recommendation;
  plan: PlanView;
  view: VerificationView;
}

/** 替换结果按「原推荐的 planId」保存，结果页重新提交时整体清空。 */
const replacements = ref<Record<string, SessionPlanReplacement>>({});

function currentPlan(recommendation: Recommendation): PlanView {
  const replaced = replacements.value[recommendation.planId];
  if (replaced === undefined) {
    return {
      planId: recommendation.planId,
      items: recommendation.items,
      verification: recommendation.verification,
      replacedFrom: null,
    };
  }
  return {
    planId: replaced.planId,
    items: replaced.items,
    verification: replaced.verification,
    replacedFrom: recommendation.planId,
  };
}

const recommendations = computed<Recommendation[]>(
  () => result.value?.recommendations ?? [],
);

/** 未知项：答复级 + 每份当前方案的核验级（替换后只用新判决）。 */
const unknowns = computed<Issue[]>(() =>
  result.value === null
    ? []
    : collectUnknowns(
        result.value.unknowns,
        recommendations.value.map((item) => currentPlan(item).verification),
      ),
);

/** 展示门禁：统一交给 describeVerification，带受控缺口标记时降级。 */
function verificationView(validation: PlanValidation): VerificationView {
  return describeVerification(validation, unknowns.value);
}

const planEntries = computed<PlanEntry[]>(() =>
  recommendations.value.map((recommendation, index) => {
    const plan = currentPlan(recommendation);
    return {
      index,
      recommendation,
      plan,
      view: verificationView(plan.verification),
    };
  }),
);

function verdictClass(view: VerificationView): string {
  if (view.allowGreenPass) return "notice--success";
  if (view.tone === "conflict") return "notice--error";
  return "notice--warning";
}

function issuesOf(validation: PlanValidation): Issue[] {
  return [...validation.violations, ...validation.unknownChecks];
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

const openKey = ref<string | null>(null);
const courseInput = ref("");
const searchStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
const searchError = ref("");
const searchedCourse = ref<string | null>(null);
const offerings = ref<CourseOffering[]>([]);
/** 班次资料是 UNKNOWN（快照缺失或非当前）：空列表不能说成「没有班次」。 */
const offeringsUnconfirmed = ref(false);
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
  openKey.value = null;
  replacements.value = {};
  resetSearch();
}

// 结果换了（重新提交或新答复），之前的替换和搜索都不再适用。
watch(
  () => store.planningResult,
  () => {
    resetPlanEdits();
    clarificationChoice.value = "";
    clarificationText.value = "";
  },
);

onBeforeUnmount(() => {
  searchController?.abort();
  replaceController?.abort();
});

function entryButtonId(index: number): string {
  return `result-search-entry-${index}`;
}
function panelId(index: number): string {
  return `result-search-panel-${index}`;
}
function courseInputId(index: number): string {
  return `result-search-course-${index}`;
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

function isOpen(entry: PlanEntry): boolean {
  return openKey.value === entry.recommendation.planId;
}

function togglePanel(entry: PlanEntry) {
  if (isOpen(entry)) {
    closePanel(entry);
    return;
  }
  resetSearch();
  courseInput.value = "";
  openKey.value = entry.recommendation.planId;
  focusById(courseInputId(entry.index));
}

function closePanel(entry: PlanEntry) {
  openKey.value = null;
  resetSearch();
  focusById(entryButtonId(entry.index));
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

async function runSearch(entry: PlanEntry) {
  const course = courseInput.value.trim();
  if (course === "") {
    searchStatus.value = "error";
    searchError.value = "请先输入课程号。";
    return;
  }
  const plan = entry.plan;
  const version = ++searchVersion;
  searchController?.abort();
  const controller = new AbortController();
  searchController = controller;
  clearSelection();
  searchStatus.value = "loading";
  searchError.value = "";

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
    offeringsUnconfirmed.value = target.status === "UNKNOWN";
    knownPlanMeetings.value = known;
    planGaps.value = gaps;
    searchedCourse.value = course;
    searchStatus.value = "ready";
  } catch (error) {
    if (version !== searchVersion || isAborted(error)) return;
    searchStatus.value = "error";
    searchError.value = visibleError(error);
  }
}

/**
 * 按已知时间判断一个班次。只是预览：时间未知不能当成没有冲突。
 * 只有「班次资料已确认、本班次时间完整、方案其他课时间全部读到、且没有冲突」才给 clear，
 * 与 answer-display.ts 的门禁一致：确定的结论才给绿色，其余一律落到无法确认。
 */
function judgeOffering(
  offering: CourseOffering,
  listUnconfirmed: boolean,
  gapCodes: readonly string[],
): Pick<OfferingRow, "kind" | "note"> {
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
    note: "按已知时间没有发现冲突（仅为预览，提交前仍需整份核验）。",
  };
}

const offeringRows = computed<OfferingRow[]>(() =>
  offerings.value.map((offering, index) => {
    const judged = judgeOffering(
      offering,
      offeringsUnconfirmed.value,
      planGaps.value,
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
    replacements.value = {
      ...replacements.value,
      [entry.recommendation.planId]: replaced,
    };
    openKey.value = null;
    resetSearch();
    focusById(entryButtonId(entry.index));
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
  <section class="question-card" aria-labelledby="result-title">
    <p class="eyebrow">规划结果</p>
    <h1 id="result-title" tabindex="-1">{{ headline }}</h1>

    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      演示模式 · 虚构内容，不代表任何真实课程或核验结果。
    </p>
    <p
      v-else-if="api.mode === 'simulation'"
      class="notice notice--demo"
      role="note"
    >
      服务联调模式 · 虚构数据，结果不代表真实课程或本学期课表。
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

      <div v-else-if="planEntries.length" class="option-section">
        <article
          v-for="entry in planEntries"
          :key="entry.recommendation.planId"
        >
          <h2 class="sub-label">方案 {{ entry.plan.planId }}</h2>
          <p v-if="entry.plan.replacedFrom" class="microcopy">
            这是替换后的新版本（替换前为
            {{ entry.plan.replacedFrom }}）。下面的核验结论只针对这一版。
          </p>
          <div class="notice" :class="verdictClass(entry.view)" role="status">
            <strong>{{ entry.view.label }}</strong>
            <ul
              v-if="issuesOf(entry.plan.verification).length"
              class="summary-list"
            >
              <li
                v-for="issue in issuesOf(entry.plan.verification)"
                :key="issue.code + issue.message"
              >
                {{ issue.message }}
              </li>
            </ul>
            <p v-else class="microcopy">{{ entry.view.detail }}</p>
          </div>
          <ul class="summary-list">
            <li v-for="item in entry.plan.items" :key="item.courseCode">
              {{ item.courseCode }}
              <template v-if="item.teacherKey">
                · 教师 {{ item.teacherKey }}
              </template>
              <template v-if="item.classId">· 班次 {{ item.classId }}</template>
            </li>
          </ul>
          <p v-if="!entry.plan.replacedFrom" class="microcopy">
            {{ entry.recommendation.explanation }}
          </p>

          <button
            :id="entryButtonId(entry.index)"
            :ref="(el) => registerFocus(entryButtonId(entry.index), el)"
            class="button button--secondary"
            type="button"
            :aria-expanded="isOpen(entry) ? 'true' : 'false'"
            :aria-controls="panelId(entry.index)"
            @click="togglePanel(entry)"
          >
            搜课程，调整这份方案
          </button>

          <section
            v-if="isOpen(entry)"
            :id="panelId(entry.index)"
            class="search-panel"
            aria-label="搜课程，调整这份方案"
          >
            <p class="microcopy">
              搜索结果里的「有冲突」「无法确认」只是预览，不是核验结论。选中班次后，必须重新核验整份方案，以核验结果为准。
            </p>
            <form
              class="search-form"
              role="search"
              @submit.prevent="runSearch(entry)"
            >
              <label class="field-label" :for="courseInputId(entry.index)">
                课程号
              </label>
              <div class="search-row">
                <input
                  :id="courseInputId(entry.index)"
                  :ref="(el) => registerFocus(courseInputId(entry.index), el)"
                  v-model="courseInput"
                  class="text-control"
                  type="search"
                  maxlength="32"
                  autocomplete="off"
                  placeholder="例如 CS103"
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
            <template v-else-if="searchStatus === 'ready' && searchedCourse">
              <h3 class="sub-label">{{ searchedCourse }} 的开课班次</h3>
              <p
                v-if="offeringsUnconfirmed"
                class="notice notice--warning"
                role="note"
              >
                这门课的班次无法确认：当前快照缺失或不是当前版本，不能据此说没有班次，下面的班次也都不能直接选择。
              </p>
              <p
                v-else-if="offeringRows.length === 0"
                class="notice notice--warning"
                role="note"
              >
                这门课在当前快照下没有班次。
              </p>
              <template v-if="offeringRows.length > 0">
                <ul
                  class="offering-list"
                  :aria-label="`${searchedCourse} 的开课班次`"
                >
                  <li
                    v-for="row in offeringRows"
                    :key="row.classId"
                    class="offering-row"
                  >
                    <div>
                      <strong>班次 {{ row.classId }}</strong>
                      <p>
                        {{ row.timeText }}
                        <template v-if="row.teacherText">
                          · {{ row.teacherText }}
                        </template>
                      </p>
                      <p :id="row.noteId">{{ row.note }}</p>
                    </div>
                    <button
                      v-if="row.kind === 'clear'"
                      class="button button--secondary"
                      type="button"
                      :aria-describedby="row.noteId"
                      @click="selectOffering(row.classId)"
                    >
                      {{ row.label }}
                    </button>
                    <button
                      v-else
                      class="offering-tag"
                      :class="`offering-tag--${row.kind}`"
                      type="button"
                      disabled
                      :aria-describedby="row.noteId"
                    >
                      {{ row.label }}
                    </button>
                  </li>
                </ul>
                <p v-if="planGaps.length" class="microcopy">
                  方案中
                  {{ planGaps.join("、") }}
                  的时间没能从当前快照读到，上面的冲突判断只比较已知时间。
                </p>
              </template>

              <div
                v-if="selectedOffering"
                class="notice notice--warning"
                role="group"
                aria-label="替换预览"
              >
                <strong>{{
                  replacePreview(entry, selectedOffering.classId)
                }}</strong>
                <p class="microcopy">
                  提交前必须重新核验整份方案。上面的预览不能代替核验结果。
                </p>
                <p
                  v-if="replaceStatus === 'submitting'"
                  role="status"
                  aria-live="polite"
                >
                  正在重新核验整份方案，请稍候。这一步不会重复提交。
                </p>
                <p
                  v-else-if="replaceStatus === 'error'"
                  class="notice notice--error"
                  role="alert"
                >
                  {{ replaceError }} 可以再点一次重新核验。
                </p>
                <button
                  class="button button--primary"
                  type="button"
                  :disabled="replaceStatus === 'submitting'"
                  @click="recheck(entry)"
                >
                  重新核验这份方案
                </button>
              </div>
            </template>

            <button
              class="button button--quiet"
              type="button"
              @click="closePanel(entry)"
            >
              收起搜索
            </button>
          </section>
        </article>
      </div>

      <div v-if="unknowns.length" class="notice notice--warning" role="note">
        <p>以下内容目前无法确认，不能算通过：</p>
        <ul class="summary-list">
          <li v-for="issue in unknowns" :key="issue.code + issue.message">
            {{ issue.message }}
          </li>
        </ul>
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
.search-panel {
  margin: 14px 0 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 9px;
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
}

.offering-list {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--line);
}

.offering-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}

.offering-row strong {
  color: var(--ink);
  font-size: 14px;
  font-weight: 550;
}

.offering-row p {
  margin: 3px 0 0;
  color: var(--soft);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.offering-tag {
  font: inherit;
  font-size: 12px;
  font-weight: 550;
  white-space: nowrap;
  padding: 9px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
}

.offering-tag:disabled {
  opacity: 1;
  cursor: not-allowed;
}

.offering-tag--conflict {
  color: #8b3c31;
  background: #fff4f2;
  border-color: #efc4bd;
}

.offering-tag--unknown {
  color: #875817;
  background: #fff8ed;
  border-color: #ecd6b0;
}

@media (max-width: 540px) {
  .search-row {
    flex-direction: column;
  }

  .offering-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
