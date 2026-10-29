<script setup lang="ts">
/**
 * 凑学分选课页（购物车模式）。
 *
 * 学生一门一门勾选课程，页面实时算账：还差多少、超出多少。
 * 剩余缺口很小时才给「刚好补齐」的建议（1 到 2 门课），剩余大时不列组合。
 * 勾选的课程会加入本次规划，并交由后端核验。
 *
 * 缺口、类别、学分、已修课程都来自 Java 的学业核对与课程目录；规则在 domain/credit-plan.ts。
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type { AcademicRecord, Course, Issue } from "../contracts";
import {
  MAX_SUGGESTION_COURSES,
  UNMODELED_RULES_CODE,
  buildCategoryPlan,
  suggestCompletions,
  suggestionsApply,
  summarizeSelection,
  type CategoryCreditPlan,
  type PlanCourse,
  type SelectionLedger,
} from "../domain/credit-plan";
import { explainAuditUnknown } from "../domain/academic-record";
import { usePlanningStore } from "../stores/planning";

/** 课程目录按后端 cursor 翻页读全；上限防止异常分页死循环。 */
const MAX_CATALOG_PAGES = 20;
const COURSE_PAGE_SIZE = 8;

const store = usePlanningStore();
const router = useRouter();

const catalog = ref<Course[]>([]);
const catalogStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
const catalogError = ref("");
let catalogVersion = 0;

/** 已勾选的课程保存在当前规划草稿中，切换页面后仍保留。 */
const selectedCodes = computed({
  get: () => store.draft.selectedCourseCodes,
  set: (value: string[]) => store.updateDraft("selectedCourseCodes", value),
});
const selectionMessage = ref("");
/** 每个类别的筛选词与当前页，key 为 requirementId。 */
const filterOf = ref<Record<string, string>>({});
const pageOf = ref<Record<string, number>>({});

const audit = computed(() => store.audit);
const auditMatchesCurriculum = computed(
  () =>
    audit.value !== null &&
    audit.value.curriculumSnapshotId === store.selectedCurriculumId,
);
const sourceRecord = computed<AcademicRecord | null>(() => {
  if (!audit.value) return null;
  return (
    store.records.find(
      (record) => record.academicRecordId === audit.value?.academicRecordId,
    ) ?? null
  );
});
const completedCodes = computed(
  () =>
    new Set(
      (sourceRecord.value?.completedCourses ?? [])
        .filter((course) => course.outcome === "PASSED")
        .map((course) => course.courseCode.trim()),
    ),
);
const recordedCredits = computed(() => {
  const passed = (sourceRecord.value?.completedCourses ?? []).filter(
    (course) => course.outcome === "PASSED",
  );
  return {
    total: passed.reduce((sum, course) => sum + (course.earnedCredits ?? 0), 0),
    missing: passed.filter((course) => course.earnedCredits === null).length,
    duplicates:
      new Set(passed.map((course) => course.courseCode)).size < passed.length,
  };
});
const chineseWordSegmenter = new (
  Intl as unknown as {
    Segmenter: new (
      locale: string,
      options: { granularity: "word" },
    ) => {
      segment(
        input: string,
      ): Iterable<{ segment: string; isWordLike?: boolean }>;
    };
  }
).Segmenter("zh", { granularity: "word" });
const interestTags = computed(() => {
  const tags = store.draft.interestTags
    .map((tag) => tag.trim())
    .filter(Boolean);
  const careerTerms = [...chineseWordSegmenter.segment(store.draft.careerText)]
    .filter((part) => part.isWordLike)
    .map((part) => part.segment.trim())
    .filter(Boolean);
  return [...new Set([...tags, ...careerTerms])];
});
const plans = computed<CategoryCreditPlan[]>(() => {
  if (!audit.value || catalogStatus.value !== "ready") return [];
  return audit.value.requirements.map((requirement) =>
    buildCategoryPlan(
      requirement,
      catalog.value,
      completedCodes.value,
      interestTags.value,
    ),
  );
});
function schoolCategoryReference(category: string | null): string | null {
  if (!category || !store.schoolProgress) return null;
  const matches = store.schoolProgress.snapshot.nodes.filter(
    (node) => node.name === category,
  );
  if (matches.length === 1) {
    const node = matches[0]!;
    return `学校报告（类别 ${node.schoolNodeId ?? "未提供编号"}）记录未获 ${node.remainingCredits ?? "未知"} 学分；此数值来自学校报告，供参考。`;
  }
  if (matches.length > 1) {
    return `学校报告中有 ${matches.length} 个同名类别，保留各节点的父子层级，无法将其唯一对应到此培养要求。`;
  }
  return null;
}
const unmodeledIssues = computed<Issue[]>(
  () =>
    audit.value?.unknowns.filter(
      (issue) => issue.code === UNMODELED_RULES_CODE,
    ) ?? [],
);
const otherIssues = computed<Issue[]>(
  () =>
    audit.value?.unknowns.filter(
      (issue) => issue.code !== UNMODELED_RULES_CODE,
    ) ?? [],
);
const canLoad = computed(
  () => store.sessionStatus === "ready" && Boolean(store.selectedCurriculumId),
);

/** 页面顶部的已选清单：只列可计入的已选课程。 */
const selectedCourses = computed<PlanCourse[]>(() => {
  const picked: PlanCourse[] = [];
  for (const plan of plans.value) {
    for (const course of plan.countable) {
      if (selectedCodes.value.includes(course.courseCode)) picked.push(course);
    }
  }
  return picked;
});

function ledgerOf(plan: CategoryCreditPlan): SelectionLedger {
  return summarizeSelection(plan, selectedCodes.value);
}

function formatCredits(value: number): string {
  return Number.isInteger(value)
    ? `${value}`
    : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

/** 账本一行：要求 X · 已修 Y · 已选 Z · 还差 W（或 已超出 N）。 */
function ledgerLine(plan: CategoryCreditPlan): string {
  const ledger = ledgerOf(plan);
  const required =
    plan.requiredCredits === null
      ? "未知"
      : formatCredits(plan.requiredCredits);
  const earned =
    plan.earnedCredits === null ? "未知" : formatCredits(plan.earnedCredits);
  const head = `要求 ${required} · 已修 ${earned} · 已选 ${formatCredits(ledger.selectedCredits)}`;
  if (plan.gapCredits === null) return `${head} · 还差无法确定`;
  if (ledger.overCredits > 0)
    return `${head} · 已超出 ${formatCredits(ledger.overCredits)} 学分`;
  if (ledger.remainingCredits === 0) return `${head} · 已凑满`;
  return `${head} · 还差 ${formatCredits(ledger.remainingCredits ?? 0)} 学分`;
}

const suggestionsByRequirement = computed(
  () =>
    new Map(
      plans.value.map((plan) => [
        plan.requirementId,
        suggestCompletions(
          plan,
          selectedCodes.value,
          ledgerOf(plan).remainingCredits,
        ),
      ]),
    ),
);

function suggestionsOf(plan: CategoryCreditPlan) {
  return suggestionsByRequirement.value.get(plan.requirementId) ?? [];
}

function showsSuggestionArea(plan: CategoryCreditPlan): boolean {
  return suggestionsApply(ledgerOf(plan).remainingCredits);
}

function isSelected(code: string): boolean {
  return selectedCodes.value.includes(code);
}

function toggleCourse(code: string) {
  if (!isSelected(code) && selectedCodes.value.length >= 10) {
    selectionMessage.value = "一次最多选择 10 门课程，请先移除不需要的课程。";
    return;
  }
  selectionMessage.value = "";
  selectedCodes.value = isSelected(code)
    ? selectedCodes.value.filter((item) => item !== code)
    : [...selectedCodes.value, code];
}

function addAll(codes: readonly string[]) {
  const next = [...selectedCodes.value];
  for (const code of codes) if (!next.includes(code)) next.push(code);
  if (next.length > 10) {
    selectionMessage.value = "一次最多选择 10 门课程，请先移除不需要的课程。";
    return;
  }
  selectionMessage.value = "";
  selectedCodes.value = next;
}

function clearSelection() {
  selectedCodes.value = [];
}

async function loadCatalog() {
  const curriculumId = store.selectedCurriculumId;
  const version = ++catalogVersion;
  if (!curriculumId) {
    catalog.value = [];
    catalogStatus.value = "idle";
    return;
  }
  catalogStatus.value = "loading";
  catalogError.value = "";
  const items: Course[] = [];
  try {
    let cursor: string | null = null;
    for (let page = 0; page < MAX_CATALOG_PAGES; page += 1) {
      const result = await api.listCourses(curriculumId, cursor);
      if (version !== catalogVersion) return;
      items.push(...result.items);
      cursor = result.nextCursor;
      if (cursor === null) break;
    }
    if (cursor !== null) {
      throw new Error("课程目录超过读取上限，无法确认候选课程是否完整。");
    }
    catalog.value = items;
    catalogStatus.value = "ready";
  } catch (error) {
    if (version !== catalogVersion) return;
    catalog.value = [];
    catalogError.value =
      error instanceof ApiFailure
        ? error.message
        : error instanceof Error &&
            error.message.startsWith("课程目录超过读取上限")
          ? error.message
          : "课程目录读取失败，请稍后重试。";
    catalogStatus.value = "error";
  }
}

onMounted(() => {
  if (canLoad.value) void loadCatalog();
});

watch(
  () => store.selectedCurriculumId,
  () => {
    pageOf.value = {};
    filterOf.value = {};
    selectedCodes.value = [];
    if (canLoad.value) void loadCatalog();
  },
);

/** 类别内的候选：先按筛选词过滤（课程号或课程名），再分页。 */
function visibleCourses(plan: CategoryCreditPlan): PlanCourse[] {
  const needle = (filterOf.value[plan.requirementId] ?? "")
    .trim()
    .toLowerCase();
  if (needle === "") return plan.countable;
  return plan.countable.filter(
    (course) =>
      course.courseCode.toLowerCase().includes(needle) ||
      course.name.toLowerCase().includes(needle),
  );
}

function pageKey(plan: CategoryCreditPlan): string {
  return `${plan.requirementId}:countable`;
}

function currentPage(plan: CategoryCreditPlan): number {
  return pageOf.value[pageKey(plan)] ?? 0;
}

function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / COURSE_PAGE_SIZE));
}

function pageItems(plan: CategoryCreditPlan): PlanCourse[] {
  const items = visibleCourses(plan);
  const start = currentPage(plan) * COURSE_PAGE_SIZE;
  return items.slice(start, start + COURSE_PAGE_SIZE);
}

function movePage(plan: CategoryCreditPlan, delta: number) {
  const total = visibleCourses(plan).length;
  const next = Math.min(
    Math.max(currentPage(plan) + delta, 0),
    pageCount(total) - 1,
  );
  pageOf.value = { ...pageOf.value, [pageKey(plan)]: next };
}

function setFilter(plan: CategoryCreditPlan, value: string) {
  filterOf.value = { ...filterOf.value, [plan.requirementId]: value };
  pageOf.value = { ...pageOf.value, [pageKey(plan)]: 0 };
}

function removeSelected(code: string) {
  selectedCodes.value = selectedCodes.value.filter((item) => item !== code);
}

function nameOf(plan: CategoryCreditPlan, code: string): string {
  return (
    plan.countable.find((course) => course.courseCode === code)?.name ?? code
  );
}

function courseLine(course: PlanCourse): string {
  return `${course.courseCode} · ${course.name} · ${formatCredits(course.credits)} 学分`;
}

function goToTeacher(code: string) {
  void router.push({ path: "/plan/teachers", query: { course: code } });
}

function goToRecords() {
  void router.push("/records");
}

function interestNote(): string {
  return interestTags.value.length > 0
    ? `按兴趣关键词与发展方向排序：${interestTags.value.join("、")}。命中的课程名排在前面。`
    : "没有填写兴趣关键词，按课程号排序。";
}

const suggestionCourseLimit = MAX_SUGGESTION_COURSES;
</script>

<template>
  <section class="question-card" aria-labelledby="credits-title">
    <p class="eyebrow">凑学分选课</p>
    <h1 id="credits-title" tabindex="-1">一门一门挑，看还差多少</h1>
    <p class="lead">
      在下面勾选想学的课，页面实时算出还差或超出的学分。学分与缺口都来自培养方案。
    </p>
    <p class="notice" role="note">
      勾选的课程会加入本次规划，并交由后端重新核验。
    </p>

    <p v-if="!canLoad" class="notice notice--warning" role="note">
      还没有可用会话。请先回到引导页开始。
    </p>

    <template v-else>
      <!-- 必须显示：跨类别抵扣系统没有建模，凑分只按单个类别计算。 -->
      <div
        v-for="issue in unmodeledIssues"
        :key="issue.code"
        class="notice notice--warning credits-unmodeled"
        role="note"
      >
        <p><strong>系统没有算跨类别抵扣。</strong></p>
        <p>{{ issue.message }}</p>
        <p class="microcopy">
          凑学分只按单个类别计算。跨类别的抵扣系统算不了，请以教务认定为准。
        </p>
      </div>

      <p v-if="!audit" class="notice notice--warning" role="note">
        还没有学业核对结果，无法知道每个类别还差多少学分。
        <button
          class="button button--secondary"
          type="button"
          @click="goToRecords"
        >
          去学业资料核对
        </button>
      </p>
      <p
        v-else-if="!auditMatchesCurriculum"
        class="notice notice--warning"
        role="note"
      >
        当前的核对结果不是这份培养方案的，请回到学业资料页重新核对。
        <button
          class="button button--secondary"
          type="button"
          @click="goToRecords"
        >
          去学业资料核对
        </button>
      </p>
      <template v-else>
        <p v-if="!sourceRecord" class="notice notice--warning" role="note">
          没有找到这次核对所用的学业记录，无法确认哪些课已修。候选里可能仍有已修课程。
        </p>
        <p
          v-if="catalogStatus === 'loading' || catalogStatus === 'idle'"
          class="notice"
          role="status"
          aria-live="polite"
        >
          正在读取课程目录…
        </p>
        <div
          v-else-if="catalogStatus === 'error'"
          class="notice notice--error"
          role="alert"
        >
          <p>{{ catalogError }}</p>
          <button
            class="button button--secondary"
            type="button"
            @click="loadCatalog"
          >
            重试读取课程
          </button>
        </div>

        <!-- 已选清单：全页共用，实时反映勾选。 -->
        <section class="credits-cart" aria-label="已选课程">
          <p v-if="sourceRecord" class="credits-total">
            记录中已通过课程的已填学分：{{
              formatCredits(recordedCredits.total)
            }}
          </p>
          <p v-if="recordedCredits.missing" class="microcopy">
            {{ recordedCredits.missing }} 门已通过课程的学分待确认。
          </p>
          <p v-if="recordedCredits.duplicates" class="microcopy">
            记录中有重复课程，合计需要核对。
          </p>
          <h2 class="sub-label">已选 {{ selectedCourses.length }} 门</h2>
          <p class="credits-total">
            已选学分：{{
              formatCredits(
                selectedCourses.reduce(
                  (sum, course) => sum + course.credits,
                  0,
                ),
              )
            }}
          </p>
          <p v-if="selectionMessage" role="status">{{ selectionMessage }}</p>
          <p v-if="selectedCourses.length === 0" class="microcopy">
            还没有勾选课程。在下面每个类别里勾选想学的课。
          </p>
          <ul v-else class="credits-list">
            <li v-for="course in selectedCourses" :key="course.courseCode">
              <span>{{ courseLine(course) }}</span>
              <button
                class="button button--quiet"
                type="button"
                @click="removeSelected(course.courseCode)"
              >
                移除
              </button>
            </li>
          </ul>
          <button
            v-if="selectedCodes.length > 0"
            class="button button--quiet"
            type="button"
            @click="clearSelection"
          >
            清空已选
          </button>
        </section>

        <p class="microcopy">{{ interestNote() }}</p>
        <p v-if="otherIssues.length" class="notice notice--warning" role="note">
          <span
            v-for="issue in otherIssues"
            :key="issue.code"
            class="credits-issue"
          >
            {{ explainAuditUnknown(issue.code, issue.message) }}
          </span>
        </p>

        <details
          v-for="plan in plans"
          :key="plan.requirementId"
          class="option-section credits-category"
          :aria-label="plan.category ?? '未命名类别'"
        >
          <summary>
            <strong>{{ plan.category ?? "未命名类别" }}</strong> ·
            {{ ledgerLine(plan) }}
          </summary>

          <p v-if="schoolCategoryReference(plan.category)" class="microcopy">
            {{ schoolCategoryReference(plan.category) }}下方候选和组合按 Java
            核验的培养方案缺口计算。
          </p>

          <p
            v-if="plan.category === null"
            class="notice notice--warning"
            role="note"
          >
            这个要求没有类别名，无法匹配课程。
          </p>
          <p
            v-else-if="plan.state === 'UNKNOWN_GAP'"
            class="notice notice--warning"
            role="note"
          >
            这个类别的缺口无法确定，先补全学业记录。
          </p>
          <p
            v-else-if="plan.state === 'SATISFIED'"
            class="notice"
            role="status"
          >
            这个类别已满足，不需要再选。仍可以自由勾选。
          </p>

          <!-- 候选课程：筛选 + 分页，勾选才计入账本。 -->
          <div v-if="plan.countable.length" class="credits-block">
            <label class="field-label" :for="`filter-${plan.requirementId}`">
              在这个类别里找课（课程号或课程名）
            </label>
            <input
              :id="`filter-${plan.requirementId}`"
              class="text-control"
              type="search"
              maxlength="120"
              :value="filterOf[plan.requirementId] ?? ''"
              @input="
                setFilter(plan, ($event.target as HTMLInputElement).value)
              "
            />
            <p
              v-if="visibleCourses(plan).length === 0"
              class="microcopy"
              role="status"
            >
              没有符合筛选条件的课程。
            </p>
            <ul class="credits-list">
              <li v-for="course in pageItems(plan)" :key="course.courseCode">
                <label class="credits-check">
                  <input
                    type="checkbox"
                    :checked="isSelected(course.courseCode)"
                    @change="toggleCourse(course.courseCode)"
                  />
                  <span>{{ courseLine(course) }}</span>
                </label>
                <button
                  class="button button--quiet"
                  type="button"
                  @click="goToTeacher(course.courseCode)"
                >
                  看这门课的教师（不等于加入规划）
                </button>
              </li>
            </ul>
            <div
              v-if="visibleCourses(plan).length > COURSE_PAGE_SIZE"
              class="credits-pager"
            >
              <button
                class="button button--secondary"
                type="button"
                :disabled="currentPage(plan) === 0"
                @click="movePage(plan, -1)"
              >
                ← 上一页
              </button>
              <span class="microcopy"
                >第 {{ currentPage(plan) + 1 }} /
                {{ pageCount(visibleCourses(plan).length) }} 页</span
              >
              <button
                class="button button--secondary"
                type="button"
                :disabled="
                  currentPage(plan) + 1 >=
                  pageCount(visibleCourses(plan).length)
                "
                @click="movePage(plan, 1)"
              >
                下一页 →
              </button>
            </div>
          </div>
          <p
            v-else-if="plan.category !== null && plan.uncountable.length === 0"
            class="microcopy"
          >
            这个类别的课程目录里没有可选课程。
          </p>

          <!-- 无法纳入凑分的课程：单独列出，不当成 0。 -->
          <div v-if="plan.uncountable.length" class="credits-block">
            <h3 class="credits-subhead">待确认课程</h3>
            <ul class="credits-list">
              <li
                v-for="course in plan.uncountable"
                :key="`${course.courseCode}:${course.name}`"
              >
                <span>{{ course.courseCode }} · {{ course.name }}</span>
                <span class="microcopy">
                  {{
                    course.reason === "AMBIGUOUS_COURSE_CODE"
                      ? "课程编号重复或待确认，暂不能确定是否已修及计入学分"
                      : course.reason === "CREDITS_UNKNOWN"
                        ? "学分待确认，无法纳入凑分"
                        : "学分为 0，无法纳入凑分"
                  }}
                </span>
              </li>
            </ul>
          </div>

          <!-- 依学分差额展示组合建议。 -->
          <div
            v-if="showsSuggestionArea(plan)"
            class="credits-block credits-suggest"
          >
            <h3 class="credits-subhead">
              学分组合（还差
              {{ formatCredits(ledgerOf(plan).remainingCredits ?? 0) }} 学分）
            </h3>
            <p class="microcopy">
              每组最多 {{ suggestionCourseLimit }} 门，优先显示刚好补齐的组合；
              计算有数量上限，完整课程仍可在上方选择。
            </p>
            <p
              v-if="suggestionsOf(plan).length === 0"
              class="microcopy"
              role="status"
            >
              暂无可计算的课程组合。
            </p>
            <ul v-else class="credits-list">
              <li
                v-for="suggestion in suggestionsOf(plan)"
                :key="suggestion.courseCodes.join('+')"
              >
                <span>
                  {{
                    suggestion.courseCodes
                      .map((code) => nameOf(plan, code))
                      .join(" + ")
                  }}
                  = {{ formatCredits(suggestion.totalCredits) }} 学分
                  <span v-if="suggestion.category === 'EXACT'">
                    · 刚好补齐</span
                  >
                  <span v-else-if="suggestion.category === 'OVER'">
                    · 超出 {{ formatCredits(suggestion.difference) }} 学分</span
                  >
                  <span v-else>
                    · 还差 {{ formatCredits(suggestion.difference) }} 学分</span
                  >
                  <span class="microcopy"
                    >（{{ suggestion.courseCodes.join(" + ") }}）</span
                  >
                </span>
                <button
                  class="button button--secondary"
                  type="button"
                  @click="addAll(suggestion.courseCodes)"
                >
                  勾选这组
                </button>
              </li>
            </ul>
          </div>
        </details>
      </template>
    </template>

    <nav class="question-nav" aria-label="凑学分导航">
      <button
        class="button button--secondary"
        type="button"
        @click="router.push('/records')"
      >
        返回学业资料
      </button>
      <button
        class="button button--primary"
        type="button"
        @click="router.push('/plan/questions/ready')"
      >
        返回规划，生成方案
      </button>
    </nav>
  </section>
</template>

<style scoped>
.credits-unmodeled {
  margin-bottom: 1rem;
}

.credits-cart {
  border: 1px solid #dbe3e8;
  border-radius: 12px;
  padding: 1rem;
  margin: 1rem 0;
  background: #f8fafb;
  position: sticky;
  top: 0;
  z-index: 3;
  max-height: 35vh;
  overflow-y: auto;
}

.credits-total {
  font-weight: 600;
}

.credits-category {
  margin-top: 1.25rem;
}

.credits-ledger {
  font-weight: 600;
  color: #164f55;
  margin: 0.25rem 0 0.5rem;
  overflow-wrap: anywhere;
}

.credits-block {
  margin: 0.75rem 0;
}

.credits-subhead {
  font-size: 1rem;
  margin: 0.5rem 0 0.25rem;
}

.credits-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0;
  display: grid;
  gap: 0.5rem;
}

.credits-list > li {
  border: 1px solid #dbe3e8;
  border-radius: 12px;
  padding: 0.75rem 1rem;
  background: #fff;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: center;
  min-width: 0;
}

.credits-check {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  min-width: 0;
  overflow-wrap: anywhere;
}

.credits-check input {
  margin-top: 0.3rem;
  width: 18px;
  height: 18px;
  flex: none;
}

.credits-pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.credits-suggest {
  border-top: 1px dashed #dbe3e8;
  padding-top: 0.5rem;
}

.credits-issue {
  display: block;
}

@media (max-width: 480px) {
  .credits-list > li {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
