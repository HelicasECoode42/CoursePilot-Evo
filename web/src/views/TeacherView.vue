<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type { Course, ReviewNote, TeacherCourseOption } from "../contracts";
import { usePlanningStore } from "../stores/planning";

type TeacherMode = "MUST" | "PREFER";
type ReviewDimension = ReviewNote["dimensions"][number];

/**
 * 一条选择 = 一门课 + 一位老师，并且只能处于一种强度。字段与 contracts 里的
 * TeacherPreference 同形（mode: MUST | PREFER）。
 */
interface TeacherPick {
  courseCode: string;
  teacherKey: string;
  teacherDisplayName: string;
  mode: TeacherMode;
}

interface ReviewState {
  status: "loading" | "ready" | "error";
  notes: ReviewNote[];
  error: string;
  /** 评价资料是 UNKNOWN：空列表不能说成「没有找到评价」，有内容时也要提示可能不完整。 */
  unconfirmed: boolean;
}

const MODE_LABEL: Record<TeacherMode, string> = {
  MUST: "必须保留",
  PREFER: "优先考虑",
};
const AVAILABILITY_LABEL: Record<TeacherCourseOption["availability"], string> =
  {
    CURRENT_VERIFIED: "本学期已核验",
    HISTORICAL_ONLY: "仅有历史资料",
    UNKNOWN: "本学期状态未知",
  };
const SOURCE_LABEL: Record<ReviewNote["sourceKind"], string> = {
  OFFICIAL_SYLLABUS: "官方课程大纲",
  USER_IMPORT: "用户导入资料",
  EXTERNAL_LINK: "外部链接资料",
  SYNTHETIC: "合成样例（非真实评价）",
};
const MATCH_LABEL: Record<ReviewNote["matchStatus"], string> = {
  COURSE_TEACHER_MATCHED: "课程与教师均已对应",
  COURSE_ONLY: "依据有限：只能确认是这门课，不能确认是这位老师",
  UNVERIFIED: "依据有限：来源未经核验，不能当作这位老师的评价",
};
const MATCH_SHORT: Record<ReviewNote["matchStatus"], string> = {
  COURSE_TEACHER_MATCHED: "课程与教师均已对应",
  COURSE_ONLY: "只能确认课程",
  UNVERIFIED: "来源未核验",
};
const DIMENSION_LABEL: Record<ReviewDimension, string> = {
  GRADING: "给分方式",
  ATTENDANCE: "签到",
  WORKLOAD: "工作量",
  EXAM: "考试",
  GROUP_WORK: "小组任务",
  PRESENTATION: "汇报展示",
  TEACHING: "授课",
  OVERALL: "整体印象",
};
const DIMENSION_ORDER = Object.keys(DIMENSION_LABEL) as ReviewDimension[];

const store = usePlanningStore();
const heading = ref<HTMLElement | null>(null);
const courseInput = ref("");
const inputMessage = ref("");
const searchedCourse = ref<string | null>(null);
const searchStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
const searchError = ref("");
const options = ref<TeacherCourseOption[]>([]);
const courseReviews = ref<ReviewNote[]>([]);
const courseReviewsLoaded = ref(false);
const courseReviewError = ref("");
const courses = ref<Course[]>([]);
const courseCatalogStatus = ref<"loading" | "ready" | "error">("loading");
const courseCatalogError = ref("");
/** 教师资料是 UNKNOWN（快照缺失或非当前）：空列表不能说成「没有可比较的教师」。 */
const optionsUnconfirmed = ref(false);
const expandedKey = ref<string | null>(null);
const reviewStates = ref<Record<string, ReviewState>>({});
/**
 * 选择存进规划草稿，不是只存在这个页面里。
 *
 * TRD 的 E-F3 要求「保留选择」，而契约的 GoalIntent 早就留好了
 * pinnedTeacherCoursePairs（元素是 TeacherPreference）。只存在组件内存里，
 * 学生一离开这页就没了，规划请求里也永远是空数组——等于白选。
 *
 * 草稿里只放契约认的三个字段；教师显示名是渲染用的，留在本页。学生答案本来
 * 就只在内存里、刷新即清空，所以两者生命周期一致。
 */
const displayNames = ref<Record<string, string>>({});
const pickKey = (courseCode: string, teacherKey: string) =>
  `${courseCode}::${teacherKey}`;

const picks = computed<TeacherPick[]>(() =>
  store.draft.teacherPicks.map((pick) => ({
    ...pick,
    teacherDisplayName:
      displayNames.value[pickKey(pick.courseCode, pick.teacherKey)] ??
      pick.teacherKey,
  })),
);

function savePicks(next: readonly TeacherPick[]): void {
  store.updateDraft(
    "teacherPicks",
    next.map(({ courseCode, teacherKey, mode }) => ({
      courseCode,
      teacherKey,
      mode,
    })),
  );
}

// 只在模板外使用，不需要响应式。
// Structural type: the lint globals do not declare the DOM HTMLButtonElement.
type FocusTarget = { focus: () => void };
const triggers = new Map<string, FocusTarget>();
let searchSeq = 0;
const reviewSeq = new Map<string, number>();

const ready = computed(
  () => store.sessionStatus === "ready" && Boolean(store.selectedCurriculumId),
);
const courseChoices = computed(() =>
  [...courses.value].sort((left, right) =>
    left.courseCode.localeCompare(right.courseCode),
  ),
);
const mustPicks = computed(() =>
  picks.value.filter((pick) => pick.mode === "MUST"),
);
const preferPicks = computed(() =>
  picks.value.filter((pick) => pick.mode === "PREFER"),
);

onMounted(() => {
  heading.value?.focus();
  void loadCourseCatalog();
});

async function loadCourseCatalog() {
  if (!ready.value || !store.selectedCurriculumId) {
    courseCatalogStatus.value = "ready";
    return;
  }
  courseCatalogStatus.value = "loading";
  try {
    const items: Course[] = [];
    let cursor: string | null = null;
    do {
      const result = await api.listCourses(store.selectedCurriculumId, cursor);
      items.push(...result.items);
      cursor = result.nextCursor;
    } while (cursor);
    courses.value = items;
    courseCatalogStatus.value = "ready";
  } catch (error) {
    courseCatalogError.value = failureMessage(error);
    courseCatalogStatus.value = "error";
  }
}

function optionKey(option: TeacherCourseOption): string {
  return `${option.courseCode}/${option.teacherKey}`;
}

function panelId(option: TeacherCourseOption): string {
  return `review-panel-${option.courseCode}-${option.teacherKey}`;
}

function bindTrigger(option: TeacherCourseOption, el: unknown) {
  const key = optionKey(option);
  if (el && typeof (el as FocusTarget).focus === "function") {
    triggers.set(key, el as FocusTarget);
  } else {
    triggers.delete(key);
  }
}

function pickOf(option: TeacherCourseOption): TeacherPick | null {
  return (
    picks.value.find(
      (pick) =>
        pick.courseCode === option.courseCode &&
        pick.teacherKey === option.teacherKey,
    ) ?? null
  );
}

/** 同一对「课程+教师」在两档之间互斥；点当前档位再点一次取消。其他选择不受影响。 */
function setStrength(option: TeacherCourseOption, mode: TeacherMode) {
  const current = pickOf(option);
  // 按「课程+教师」比，不要按对象引用比：picks 是 computed，每次都生成新对象，
  // 引用比较会永远不相等，互斥就失效了。
  const samePair = (pick: TeacherPick) =>
    pick.courseCode === option.courseCode &&
    pick.teacherKey === option.teacherKey;

  if (current?.mode === mode) {
    savePicks(picks.value.filter((pick) => !samePair(pick)));
    return;
  }
  displayNames.value = {
    ...displayNames.value,
    [pickKey(option.courseCode, option.teacherKey)]: option.teacherDisplayName,
  };
  if (current) {
    savePicks(
      picks.value.map((pick) => (samePair(pick) ? { ...pick, mode } : pick)),
    );
    return;
  }
  savePicks([
    ...picks.value,
    {
      courseCode: option.courseCode,
      teacherKey: option.teacherKey,
      teacherDisplayName: option.teacherDisplayName,
      mode,
    },
  ]);
}

function pickLabel(pick: TeacherPick): string {
  return `${pick.courseCode} · ${pick.teacherDisplayName}`;
}

function failureMessage(error: unknown): string {
  return error instanceof ApiFailure
    ? error.message
    : "读取失败，请检查网络后重试。";
}

function classCountText(option: TeacherCourseOption): string {
  return option.classIds.length > 0
    ? `${option.classIds.length} 个班次`
    : "暂无班次资料";
}

async function searchTeachers() {
  inputMessage.value = "";
  const code = courseInput.value.trim();
  if (
    !code ||
    !courseChoices.value.some((course) => course.courseCode === code)
  ) {
    inputMessage.value = "请从当前培养方案的课程列表中选择课程。";
    return;
  }
  if (!ready.value || !store.selectedCurriculumId) {
    inputMessage.value = "请先在规划页开始会话并选择培养方案，再来比较教师。";
    return;
  }
  const seq = ++searchSeq;
  searchedCourse.value = code;
  searchStatus.value = "loading";
  courseReviews.value = [];
  courseReviewsLoaded.value = false;
  courseReviewError.value = "";
  expandedKey.value = null;
  try {
    if (courseCatalogStatus.value === "error") await loadCourseCatalog();
    if (seq !== searchSeq) return;
    if (courseCatalogStatus.value === "error") {
      searchError.value = courseCatalogError.value;
      searchStatus.value = "error";
      return;
    }
    const result = await api.listTeacherCourseOptions(
      store.selectedCurriculumId,
      code,
    );
    if (seq !== searchSeq) return;
    options.value = result.items.filter((option) => option.courseCode === code);
    optionsUnconfirmed.value = result.status === "UNKNOWN";
    searchStatus.value = "ready";
  } catch (error) {
    if (seq !== searchSeq) return;
    options.value = [];
    optionsUnconfirmed.value = false;
    searchError.value = failureMessage(error);
    searchStatus.value = "error";
  }
}

async function loadCourseReviews() {
  const code = searchedCourse.value;
  if (!code) return;
  const seq = searchSeq;
  courseReviewError.value = "";
  try {
    const reviews = await api.searchReviews(code, null);
    if (seq === searchSeq) {
      courseReviews.value = reviews.items.filter(
        (note) => note.courseCode === code && note.teacherKey === null,
      );
      courseReviewsLoaded.value = true;
    }
  } catch (error) {
    if (seq === searchSeq) courseReviewError.value = failureMessage(error);
  }
}

async function loadReviews(option: TeacherCourseOption) {
  const key = optionKey(option);
  const seq = (reviewSeq.get(key) ?? 0) + 1;
  reviewSeq.set(key, seq);
  reviewStates.value = {
    ...reviewStates.value,
    [key]: { status: "loading", notes: [], error: "", unconfirmed: false },
  };
  try {
    const result = await api.searchReviews(
      option.courseCode,
      option.teacherKey,
    );
    if (reviewSeq.get(key) !== seq) return;
    // 只保留这门课、且是这位老师或未指明老师的评价，不混入别的老师。
    const own = result.items.filter(
      (note) =>
        note.courseCode === option.courseCode &&
        (note.teacherKey === null || note.teacherKey === option.teacherKey),
    );
    reviewStates.value = {
      ...reviewStates.value,
      [key]: {
        status: "ready",
        notes: own,
        error: "",
        unconfirmed: result.status === "UNKNOWN",
      },
    };
  } catch (error) {
    if (reviewSeq.get(key) !== seq) return;
    reviewStates.value = {
      ...reviewStates.value,
      [key]: {
        status: "error",
        notes: [],
        error: failureMessage(error),
        unconfirmed: false,
      },
    };
  }
}

function reviewStateOf(option: TeacherCourseOption): ReviewState | undefined {
  return reviewStates.value[optionKey(option)];
}

async function toggleReviews(option: TeacherCourseOption) {
  const key = optionKey(option);
  if (expandedKey.value === key) {
    await collapseReviews(option);
    return;
  }
  expandedKey.value = key;
  const state = reviewStateOf(option);
  if (!state || state.status === "error") await loadReviews(option);
}

/** 关闭详情后把焦点还给打开它的按钮（TRD：详情关回原焦点）。 */
async function collapseReviews(option: TeacherCourseOption) {
  const key = optionKey(option);
  expandedKey.value = null;
  await nextTick();
  triggers.get(key)?.focus();
}

interface ReviewSummary {
  synthetic: boolean;
  hasMatched: boolean;
  divergenceNotes: string[];
}

function summarizeReviews(notes: ReviewNote[]): ReviewSummary {
  const statuses = [...new Set(notes.map((note) => note.matchStatus))];
  const synthetic = notes.some((note) => note.sourceKind === "SYNTHETIC");
  const mixedWithReal =
    synthetic && notes.some((note) => note.sourceKind !== "SYNTHETIC");
  const partialDimensions = DIMENSION_ORDER.filter((dimension) => {
    const count = notes.filter((note) =>
      note.dimensions.includes(dimension),
    ).length;
    return count > 0 && count < notes.length;
  });
  const divergenceNotes: string[] = [];
  if (statuses.length > 1) {
    divergenceNotes.push(
      `依据程度不同（${statuses.map((status) => MATCH_SHORT[status]).join("、")}）`,
    );
  }
  if (mixedWithReal) divergenceNotes.push("合成样例与其他来源并存，请分开看待");
  if (partialDimensions.length > 0) {
    divergenceNotes.push(
      `只有部分证据提到${partialDimensions.map((dimension) => DIMENSION_LABEL[dimension]).join("、")}，不能当作一致结论`,
    );
  }
  return {
    synthetic,
    hasMatched: notes.some(
      (note) => note.matchStatus === "COURSE_TEACHER_MATCHED",
    ),
    divergenceNotes,
  };
}

function yearText(publishedAt: string | null): string {
  if (!publishedAt) return "年份未知";
  const date = new Date(publishedAt);
  return Number.isNaN(date.getTime())
    ? "年份未知"
    : `发布于 ${date.getUTCFullYear()} 年`;
}

function dimensionText(dimensions: ReviewNote["dimensions"]): string {
  return dimensions.length > 0
    ? dimensions.map((dimension) => DIMENSION_LABEL[dimension]).join("、")
    : "未标注维度";
}
</script>

<template>
  <section class="question-card" aria-labelledby="teacher-title">
    <p class="eyebrow">教师偏好</p>
    <h1 id="teacher-title" ref="heading" tabindex="-1">比较课程与教师</h1>
    <p class="lead">
      从当前培养方案选择课程，查看对应的教师资料。评价只作参考，依据不足的会标明。
    </p>
    <RouterLink class="button button--secondary" to="/plan/questions/ready">
      返回资料确认
    </RouterLink>

    <template v-if="!ready">
      <p class="notice" role="note">
        请先在规划页开始会话并选择培养方案，再来比较教师。
      </p>
      <RouterLink class="button button--secondary" to="/plan/questions/teacher">
        返回教师偏好问题
      </RouterLink>
    </template>

    <template v-else>
      <form class="teacher-search" @submit.prevent="searchTeachers">
        <label class="field-label" for="course-code">选择课程</label>
        <select
          id="course-code"
          v-model="courseInput"
          class="select-control"
          :disabled="
            courseCatalogStatus !== 'ready' || courseChoices.length === 0
          "
        >
          <option value="" disabled>请选择当前培养方案中的课程</option>
          <option
            v-for="course in courseChoices"
            :key="course.courseCode"
            :value="course.courseCode"
          >
            {{ course.name }}（{{ course.courseCode }}）
          </option>
        </select>
        <button
          type="submit"
          class="button button--primary"
          :disabled="searchStatus === 'loading'"
        >
          {{ searchStatus === "loading" ? "正在查找…" : "查找教师" }}
        </button>
      </form>
      <p
        v-if="courseCatalogStatus === 'loading'"
        class="microcopy"
        role="status"
      >
        正在读取当前培养方案的课程…
      </p>
      <div
        v-else-if="courseCatalogStatus === 'error'"
        class="notice notice--error"
        role="alert"
      >
        <p>{{ courseCatalogError }}</p>
        <button
          type="button"
          class="button button--secondary"
          @click="loadCourseCatalog"
        >
          重试读取课程
        </button>
      </div>
      <p v-else-if="courseChoices.length === 0" class="notice" role="status">
        当前培养方案没有课程资料。
      </p>
      <p v-if="inputMessage" class="notice notice--error" role="alert">
        {{ inputMessage }}
      </p>
      <button
        v-if="searchStatus === 'ready'"
        type="button"
        class="button button--secondary"
        @click="loadCourseReviews"
      >
        查看课程历史评价
      </button>
      <p v-if="courseReviewsLoaded && !courseReviews.length">
        当前未找到课程级历史评价。
      </p>
      <section
        v-if="courseReviews.length"
        class="notice"
        aria-label="课程历史评价"
      >
        <h2>课程历史评价</h2>
        <p>以下评价的教师身份尚未核实，仅供了解课程历史反馈。</p>
        <ul>
          <li v-for="note in courseReviews" :key="note.reviewNoteId">
            <span v-if="note.teacherDisplayName"
              >教师姓名（未核验）：{{ note.teacherDisplayName }}；</span
            >
            {{
              note.sourceKind === "SYNTHETIC" ? "虚构演示评价：" : "历史资料："
            }}{{ note.excerpt }}
          </li>
        </ul>
      </section>
      <p v-if="courseReviewError" class="notice notice--error" role="alert">
        课程评价读取失败：{{ courseReviewError }}
      </p>

      <p v-if="searchStatus === 'loading'" class="microcopy" role="status">
        正在读取教师资料…
      </p>
      <div
        v-else-if="searchStatus === 'error'"
        class="notice notice--error"
        role="alert"
      >
        <p>{{ searchError }}</p>
        <button
          type="button"
          class="button button--secondary"
          @click="searchTeachers"
        >
          重试
        </button>
      </div>
      <p
        v-else-if="
          searchStatus === 'ready' && options.length === 0 && optionsUnconfirmed
        "
        class="notice notice--warning"
        role="status"
      >
        {{ searchedCourse }}
        的教师资料无法确认：当前培养方案快照缺失或不是当前版本，不能据此说没有可比较的教师。
      </p>
      <p
        v-else-if="searchStatus === 'ready' && options.length === 0"
        class="notice"
        role="status"
      >
        {{ searchedCourse }}
        在当前培养方案快照下没有可比较的教师资料。这是正常说明，不是错误。
      </p>

      <template v-else-if="searchStatus === 'ready'">
        <p v-if="optionsUnconfirmed" class="notice notice--warning" role="note">
          下面的教师资料无法确认（快照缺失或不是当前版本），列表可能不完整。
        </p>
        <ul class="teacher-list" aria-label="教师选项">
          <li
            v-for="option in options"
            :key="optionKey(option)"
            class="choice-card teacher-option"
          >
            <span class="choice-copy">
              <strong>{{ option.teacherDisplayName }}</strong>
              <small>
                {{ AVAILABILITY_LABEL[option.availability] }} ·
                {{ classCountText(option) }}
              </small>
            </span>

            <span
              class="seg"
              role="group"
              :aria-label="`${option.teacherDisplayName} 的保留强度`"
            >
              <button
                type="button"
                :aria-pressed="pickOf(option)?.mode === 'MUST'"
                :aria-label="`${option.teacherDisplayName} ${MODE_LABEL.MUST}`"
                @click="setStrength(option, 'MUST')"
              >
                {{ MODE_LABEL.MUST }}
              </button>
              <button
                type="button"
                :aria-pressed="pickOf(option)?.mode === 'PREFER'"
                :aria-label="`${option.teacherDisplayName} ${MODE_LABEL.PREFER}`"
                @click="setStrength(option, 'PREFER')"
              >
                {{ MODE_LABEL.PREFER }}
              </button>
            </span>

            <button
              :ref="(el) => bindTrigger(option, el)"
              type="button"
              class="button button--secondary"
              :aria-expanded="expandedKey === optionKey(option)"
              :aria-controls="
                expandedKey === optionKey(option) ? panelId(option) : undefined
              "
              @click="toggleReviews(option)"
            >
              {{ expandedKey === optionKey(option) ? "收起评价" : "查看评价" }}
            </button>

            <div
              v-if="expandedKey === optionKey(option)"
              :id="panelId(option)"
              class="teacher-reviews"
              role="region"
              :aria-label="`${option.teacherDisplayName} 的课程评价`"
              @keydown.esc="collapseReviews(option)"
            >
              <p
                v-if="reviewStateOf(option)?.status === 'loading'"
                class="microcopy"
                role="status"
              >
                正在读取评价…
              </p>
              <div
                v-else-if="reviewStateOf(option)?.status === 'error'"
                class="notice notice--error"
                role="alert"
              >
                <p>{{ reviewStateOf(option)?.error }}</p>
                <button
                  type="button"
                  class="button button--secondary"
                  @click="loadReviews(option)"
                >
                  重试
                </button>
              </div>
              <template v-else-if="reviewStateOf(option)?.status === 'ready'">
                <template v-if="reviewStateOf(option)!.notes.length === 0">
                  <p
                    v-if="reviewStateOf(option)!.unconfirmed"
                    class="notice notice--warning"
                    role="status"
                  >
                    评价资料无法确认，不能据此说没有相关评价。
                  </p>
                  <p v-else class="notice" role="status">
                    没有找到评价。这只表示当前资料里没有相关记录，不代表这位老师或这门课的评价好或不好。
                  </p>
                </template>
                <template v-else>
                  <p
                    v-if="reviewStateOf(option)!.unconfirmed"
                    class="notice notice--warning"
                    role="note"
                  >
                    下面的评价资料无法确认，列表可能不完整。
                  </p>
                  <p
                    v-if="
                      summarizeReviews(reviewStateOf(option)!.notes).synthetic
                    "
                    class="notice notice--demo"
                    role="note"
                  >
                    本列表含合成样例，仅用于演示流程，不是真实学生的评价。
                  </p>
                  <p
                    v-if="
                      !summarizeReviews(reviewStateOf(option)!.notes).hasMatched
                    "
                    class="notice notice--warning"
                    role="note"
                  >
                    这位老师目前没有课程与教师均已对应的评价，下面的依据有限。
                  </p>
                  <div
                    v-if="
                      summarizeReviews(reviewStateOf(option)!.notes)
                        .divergenceNotes.length > 0
                    "
                    class="notice notice--warning"
                    role="note"
                  >
                    <strong>证据之间有分歧</strong>
                    <p>
                      {{
                        summarizeReviews(
                          reviewStateOf(option)!.notes,
                        ).divergenceNotes.join("；")
                      }}
                    </p>
                  </div>
                  <ol class="summary-priorities">
                    <li
                      v-for="note in reviewStateOf(option)!.notes"
                      :key="note.reviewNoteId"
                      :class="{
                        'review-limited':
                          note.matchStatus !== 'COURSE_TEACHER_MATCHED',
                      }"
                    >
                      <p>
                        <strong>{{ SOURCE_LABEL[note.sourceKind] }}</strong>
                        · {{ yearText(note.publishedAt) }}
                      </p>
                      <p v-if="note.teacherDisplayName">
                        教师姓名（显示文本）：{{ note.teacherDisplayName }}
                      </p>
                      <p>维度：{{ dimensionText(note.dimensions) }}</p>
                      <p>{{ note.excerpt }}</p>
                      <p
                        :class="
                          note.matchStatus === 'COURSE_TEACHER_MATCHED'
                            ? 'microcopy'
                            : 'notice notice--warning'
                        "
                      >
                        {{ MATCH_LABEL[note.matchStatus] }}
                      </p>
                    </li>
                  </ol>
                </template>
              </template>
              <button
                type="button"
                class="button button--quiet"
                @click="collapseReviews(option)"
              >
                关闭评价
              </button>
            </div>
          </li>
        </ul>
      </template>
    </template>

    <section class="teacher-picks" aria-labelledby="picks-title">
      <h2 id="picks-title">已选择的课程与教师</h2>
      <p class="microcopy">选择会加入本次规划。刷新页面后需要重新选择。</p>
      <dl class="summary-list">
        <div>
          <dt>必须保留</dt>
          <dd>
            {{
              mustPicks.length > 0
                ? mustPicks.map(pickLabel).join("、")
                : "这一项留空了"
            }}
          </dd>
        </div>
        <div>
          <dt>优先考虑</dt>
          <dd>
            {{
              preferPicks.length > 0
                ? preferPicks.map(pickLabel).join("、")
                : "这一项留空了"
            }}
          </dd>
        </div>
      </dl>
    </section>
  </section>
</template>
