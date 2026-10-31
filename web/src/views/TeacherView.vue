<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import ReviewSummary from "../components/ReviewSummary.vue";
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
    CURRENT_VERIFIED: "课程与教师关联已确认",
    HISTORICAL_ONLY: "仅有历史资料",
    UNKNOWN: "目标学期开课状态未知",
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
type SearchOption = TeacherCourseOption & { courseDisplayName?: string };

const store = usePlanningStore();
const heading = ref<HTMLElement | null>(null);
const searchInput = ref("");
const inputMessage = ref("");
const searchedQuery = ref("");
const searchStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
const searchError = ref("");
const options = ref<SearchOption[]>([]);
const courses = ref<Course[]>([]);
const expandedCourseCode = ref<string | null>(null);
const coursesWithoutTeacher = computed(() =>
  courses.value.filter(
    (course) =>
      !options.value.some((option) => option.courseCode === course.courseCode),
  ),
);
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
 * 草稿只保存契约字段；姓名保存在 store 的显示映射中，不进入规划请求。
 */
const pickKey = (courseCode: string, teacherKey: string) =>
  `${courseCode}::${teacherKey}`;

const picks = computed<TeacherPick[]>(() =>
  store.draft.teacherPicks.map((pick) => ({
    ...pick,
    teacherDisplayName:
      store.teacherPickDisplayNames[
        pickKey(pick.courseCode, pick.teacherKey)
      ] ?? pick.teacherKey,
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

const route = useRoute();

onMounted(() => {
  heading.value?.focus();
  // 从凑学分页「加入规划」进来：带 ?course=课程号 时预先选好课程，学生只需挑教师。
  const preset = route.query.course;
  if (typeof preset === "string" && preset.trim() !== "") {
    searchInput.value = preset.trim();
    void searchOptions();
  }
});

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
  store.setTeacherPickDisplayName(
    option.courseCode,
    option.teacherKey,
    option.teacherDisplayName,
  );
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

async function searchOptions() {
  inputMessage.value = "";
  searchError.value = "";
  const term = searchInput.value.trim();
  if (!term) {
    inputMessage.value = "请输入课程号、课程名或教师姓名。";
    return;
  }
  if (!ready.value || !store.selectedCurriculumId) {
    inputMessage.value = "请先在规划页开始会话并选择培养方案，再来比较教师。";
    return;
  }
  const seq = ++searchSeq;
  searchedQuery.value = term;
  searchStatus.value = "loading";
  expandedKey.value = null;
  expandedCourseCode.value = null;
  try {
    const matchedCourses: Course[] = [];
    let cursor: string | null = null;
    do {
      const page = await api.listCourses(
        store.selectedCurriculumId,
        cursor,
        undefined,
        term,
      );
      matchedCourses.push(...page.items);
      cursor = page.nextCursor;
    } while (cursor);
    const [byTeacher, byCourse] = await Promise.all([
      api.listTeacherCourseOptions(
        store.selectedCurriculumId,
        null,
        undefined,
        term,
      ),
      Promise.all(
        matchedCourses.map((course) =>
          api.listTeacherCourseOptions(
            store.selectedCurriculumId!,
            course.courseCode,
          ),
        ),
      ),
    ]);
    if (seq !== searchSeq) return;
    const names = new Map(
      matchedCourses.map((course) => [course.courseCode, course.name]),
    );
    const missingCodes = [
      ...new Set(byTeacher.items.map((item) => item.courseCode)),
    ].filter((code) => !names.has(code));
    const namePages = await Promise.all(
      missingCodes.map((code) =>
        api.listCourses(store.selectedCurriculumId!, null, undefined, code),
      ),
    );
    for (const item of namePages.flatMap((page) => page.items)) {
      names.set(item.courseCode, item.name);
    }
    if (seq !== searchSeq) return;
    const merged = new Map<string, SearchOption>();
    for (const option of [
      ...byTeacher.items,
      ...byCourse.flatMap((result) => result.items),
    ]) {
      merged.set(optionKey(option), {
        ...option,
        courseDisplayName: names.get(option.courseCode),
      });
    }
    options.value = [...merged.values()];
    courses.value = matchedCourses;
    optionsUnconfirmed.value =
      byTeacher.status === "UNKNOWN" ||
      byCourse.some((result) => result.status === "UNKNOWN");
    searchStatus.value = "ready";
  } catch (error) {
    if (seq !== searchSeq) return;
    options.value = [];
    courses.value = [];
    optionsUnconfirmed.value = false;
    searchError.value = failureMessage(error);
    searchStatus.value = "error";
  }
}

function courseReviewKey(course: Course): string {
  return `course:${course.courseCode}`;
}

async function loadCourseReviews(course: Course) {
  const key = courseReviewKey(course);
  const seq = (reviewSeq.get(key) ?? 0) + 1;
  reviewSeq.set(key, seq);
  reviewStates.value = {
    ...reviewStates.value,
    [key]: { status: "loading", notes: [], error: "", unconfirmed: false },
  };
  try {
    const result = await api.searchReviews(course.courseCode, null);
    if (reviewSeq.get(key) !== seq) return;
    reviewStates.value = {
      ...reviewStates.value,
      [key]: {
        status: "ready",
        notes: result.items.filter(
          (note) => note.courseCode === course.courseCode,
        ),
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

async function toggleCourseReviews(course: Course) {
  if (expandedCourseCode.value === course.courseCode) {
    expandedCourseCode.value = null;
    return;
  }
  expandedCourseCode.value = course.courseCode;
  const state = reviewStates.value[courseReviewKey(course)];
  if (!state || state.status === "error") await loadCourseReviews(course);
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

interface TeacherReviewOverview {
  synthetic: boolean;
  hasMatched: boolean;
  divergenceNotes: string[];
}

function summarizeReviews(notes: ReviewNote[]): TeacherReviewOverview {
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
      <form class="teacher-search" @submit.prevent="searchOptions">
        <label class="field-label" for="teacher-search-input">
          搜索课程或教师
        </label>
        <div class="teacher-search-actions">
          <input
            id="teacher-search-input"
            v-model="searchInput"
            class="text-control"
            placeholder="课程号、课程名或教师姓名"
            maxlength="200"
          />
          <button
            type="submit"
            class="button button--primary"
            :disabled="searchStatus === 'loading' || !searchInput.trim()"
          >
            {{ searchStatus === "loading" ? "正在搜索…" : "搜索" }}
          </button>
        </div>
        <p class="microcopy">
          结果仅显示培养方案中已有的课程与教师关联。<a
            href="https://cs.shu.edu.cn/szdw/jsml.htm"
            target="_blank"
            rel="noopener noreferrer"
            >查看学校教师名录</a
          >
        </p>
      </form>
      <p v-if="inputMessage" class="notice notice--error" role="alert">
        {{ inputMessage }}
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
          @click="searchOptions"
        >
          重试
        </button>
      </div>
      <p
        v-else-if="
          searchStatus === 'ready' &&
          options.length === 0 &&
          courses.length === 0 &&
          optionsUnconfirmed
        "
        class="notice notice--warning"
        role="status"
      >
        {{ searchedQuery }}
        的教师资料无法确认：当前培养方案快照缺失或不是当前版本，不能据此说没有可比较的教师。
      </p>
      <p
        v-else-if="
          searchStatus === 'ready' &&
          options.length === 0 &&
          courses.length === 0
        "
        class="notice"
        role="status"
      >
        {{
          `没有找到与 ${searchedQuery} 匹配的课程和教师关联`
        }}。学校教师名录可查询姓名。
      </p>

      <template v-else-if="searchStatus === 'ready'">
        <p v-if="optionsUnconfirmed" class="notice notice--warning" role="note">
          下面的教师资料无法确认（快照缺失或不是当前版本），列表可能不完整。
        </p>
        <ul
          v-if="coursesWithoutTeacher.length"
          class="teacher-list"
          aria-label="课程结果"
        >
          <li
            v-for="course in coursesWithoutTeacher"
            :key="course.courseCode"
            class="choice-card teacher-option teacher-option--green"
          >
            <span class="choice-copy">
              <strong>{{ course.courseCode }} · {{ course.name }}</strong>
              <small>
                {{
                  course.credits === null
                    ? "学分未知"
                    : `${course.credits} 学分`
                }}
                ·
                {{ course.category }}
              </small>
              <small>
                {{
                  optionsUnconfirmed
                    ? "教师资料暂不可确认"
                    : "暂无已确认的教师关联"
                }}
              </small>
            </span>
            <button
              type="button"
              class="button button--secondary"
              :aria-expanded="expandedCourseCode === course.courseCode"
              @click="toggleCourseReviews(course)"
            >
              {{
                expandedCourseCode === course.courseCode
                  ? "收起课程评价"
                  : "查看课程历史评价"
              }}
            </button>
            <div
              v-if="expandedCourseCode === course.courseCode"
              class="teacher-reviews"
              role="region"
              :aria-label="`${course.courseCode} 的课程评价`"
            >
              <p
                v-if="
                  reviewStates[courseReviewKey(course)]?.status === 'loading'
                "
                class="microcopy"
                role="status"
              >
                正在读取课程评价…
              </p>
              <div
                v-else-if="
                  reviewStates[courseReviewKey(course)]?.status === 'error'
                "
                class="notice notice--error"
                role="alert"
              >
                <p>{{ reviewStates[courseReviewKey(course)]?.error }}</p>
                <button
                  type="button"
                  class="button button--secondary"
                  @click="loadCourseReviews(course)"
                >
                  重试
                </button>
              </div>
              <template
                v-else-if="
                  reviewStates[courseReviewKey(course)]?.status === 'ready'
                "
              >
                <ReviewSummary
                  :course-code="course.courseCode"
                  :notes="reviewStates[courseReviewKey(course)]!.notes"
                  :unconfirmed="
                    reviewStates[courseReviewKey(course)]!.unconfirmed
                  "
                />
                <p
                  v-if="
                    !reviewStates[courseReviewKey(course)]!.notes.length &&
                    !reviewStates[courseReviewKey(course)]!.unconfirmed
                  "
                  class="microcopy"
                >
                  当前资料中没有课程评价记录。
                </p>
              </template>
            </div>
          </li>
        </ul>
        <ul v-if="options.length" class="teacher-list" aria-label="教师选项">
          <li
            v-for="option in options"
            :key="optionKey(option)"
            class="choice-card teacher-option teacher-option--green"
          >
            <span class="choice-copy">
              <strong>
                {{ option.courseCode
                }}<template v-if="option.courseDisplayName">
                  · {{ option.courseDisplayName }}
                </template>
                · {{ option.teacherDisplayName }}
              </strong>
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
              v-if="pickOf(option)"
              type="button"
              class="button button--secondary teacher-option__cancel"
              :aria-label="`取消 ${option.courseCode} ${option.teacherDisplayName} 的教师偏好`"
              @click="setStrength(option, pickOf(option)!.mode)"
            >
              取消
            </button>

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
                  <ReviewSummary
                    :course-code="option.courseCode"
                    :notes="reviewStateOf(option)!.notes"
                    :unconfirmed="reviewStateOf(option)!.unconfirmed"
                  />
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

    <p v-if="picks.length" class="teacher-picks" aria-live="polite">
      已选：
      <span
        v-for="(pick, index) in picks"
        :key="pickKey(pick.courseCode, pick.teacherKey)"
      >
        <template v-if="index">、</template>
        {{ pick.courseCode }} · {{ pick.teacherDisplayName }}（{{
          MODE_LABEL[pick.mode]
        }}）
      </span>
    </p>
  </section>
</template>

<style scoped>
.teacher-option--green {
  border: 1px solid #b8d9c7;
  border-radius: 16px;
  background: #f1f8f3;
  padding: 16px;
}

.teacher-option__cancel {
  color: #315f48;
}

.teacher-picks {
  margin-top: 18px;
  padding: 12px 16px;
  border-radius: 12px;
  background: #e8f4ec;
  color: #315f48;
}

@media (max-width: 640px) {
  .teacher-option--green {
    padding: 12px;
  }
}
</style>
