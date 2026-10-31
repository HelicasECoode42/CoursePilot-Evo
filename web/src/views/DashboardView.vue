<script setup lang="ts">
/**
 * 个人控制台。配置完之后的落地页，四块：
 *   ① 我的状态   —— 来自 Java 的学业核对，原样显示，不改写 UNKNOWN
 *   ② 问一问     —— 确定性的回答 + 职业方向；不编造，也不假装在和模型对话
 *   ③ 看开什么课 —— 真实培养方案的课程，按要求类别分组，展开才查评价
 *   ④ 开始选课   —— 进现有的规划流程，这一页不重做它
 *
 * 两条自己给自己定的红线：
 *  - 评价只给条数和维度标签，不折算成分数或星级（AGENTS.md：
 *    高绩点 / 签到 / 工作量 / 授课评价不是一回事）。
 *  - 没有评价记录就写「暂无评价记录」，不能留空让人读成「没人吐槽」。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../api";
import type { CareerDirection, Course, ReviewNote } from "../contracts";
import SchoolProgressTree from "../components/SchoolProgressTree.vue";
import ReviewSummary from "../components/ReviewSummary.vue";
import AdviceChat from "../components/AdviceChat.vue";
import { groupAuditItems } from "../domain/academic-record";
import { isCurriculumUsableForMode } from "../domain/planning-request";
import { usePlanningStore } from "../stores/planning";

const store = usePlanningStore();

const activeView = ref<"progress" | "courses" | "directions">("progress");
const courseQuery = ref("");
function selectView(view: "progress" | "courses" | "directions") {
  activeView.value = view;
  if (view === "directions" && askOpen.value !== "directions")
    void openDirections();
}
const sourceLabel = computed(
  () =>
    ({
      VERIFIED: "来源已核验",
      UNVERIFIED: "来源待核验",
      SYNTHETIC: "虚构示例",
    })[store.selectedCurriculum?.sourceValidation ?? "UNVERIFIED"],
);
const outcomeLabels = {
  PASSED: "已通过",
  FAILED: "未通过",
  IN_PROGRESS: "在读",
  UNKNOWN: "状态待确认",
};

type Load = "idle" | "loading" | "ready" | "error";

const bootStatus = ref<Load>("idle");
const bootError = ref("");

const courses = ref<Course[]>([]);
const coursesStatus = ref<Load>("idle");
const coursesError = ref("");

const expanded = ref<string | null>(null);
const reviewsByCourse = ref<Record<string, ReviewNote[]>>({});
const reviewStatus = ref<Record<string, Load>>({});
const reviewUnconfirmed = ref<Record<string, boolean>>({});

const directions = ref<CareerDirection[]>([]);
const directionsStatus = ref<Load>("idle");
const directionsError = ref("");

const askOpen = ref<"" | "learned" | "directions">("");

let controller: AbortController | null = null;

/**
 * 能用的培养方案。沿用 domain/planning-request 的同一个判断，
 * 不在这一页另写一套「哪份方案能用」的规则。
 */
const usableCurricula = computed(() =>
  store.curricula.filter((item) =>
    isCurriculumUsableForMode(item, store.planningMode),
  ),
);

async function pickCurriculum(snapshotId: string) {
  if (!snapshotId) return;
  store.chooseCurriculum(snapshotId);
  await Promise.all([store.loadRecords(), store.loadSchoolProgress()]);
  const current = new AbortController();
  controller?.abort();
  controller = current;
  await loadCourses(snapshotId, current.signal);
}

const auditGroups = computed(() =>
  store.audit ? groupAuditItems(store.audit.requirements) : [],
);

/** 按要求类别分组。类别名来自培养方案，不在前端另起名字。 */
const courseGroups = computed(() => {
  const byCategory = new Map<string, Course[]>();
  for (const course of courses.value) {
    const term = courseQuery.value.trim().toLocaleLowerCase();
    if (
      term &&
      !`${course.name} ${course.courseCode}`.toLocaleLowerCase().includes(term)
    )
      continue;
    const key = course.category || "未注明类别";
    const bucket = byCategory.get(key);
    if (bucket) bucket.push(course);
    else byCategory.set(key, [course]);
  }
  return [...byCategory.entries()]
    .map(([category, items]) => ({ category, items }))
    .sort((a, b) => b.items.length - a.items.length);
});

const courseCount = computed(
  () => new Set(courses.value.map((course) => course.courseCode)).size,
);
const importedCourseNames = computed(() => {
  const names = new Map(
    courses.value.map((course) => [course.courseCode, course.name]),
  );
  for (const course of store.schoolProgress?.snapshot.courses ?? [])
    names.set(course.courseCode, course.name);
  return names;
});

function formatCredits(value: number | null): string {
  if (value === null) return "学分未注明";
  return `${Number.isInteger(value) ? value : value.toFixed(1)} 学分`;
}

function formatGap(value: number | null): string {
  if (value === null) return "无法确认";
  if (value <= 0) return "已凑满";
  return `还差 ${Number.isInteger(value) ? value : value.toFixed(1)} 学分`;
}

/**
 * 把课程分页全部取回来。真实培养方案是 95 门课、105 行记录，
 * 一页取不完，所以要跟着 nextCursor 翻到底。上限 20 页是为了
 * 不被异常的游标拖进死循环。
 */
async function loadCourses(snapshotId: string, signal: AbortSignal) {
  coursesStatus.value = "loading";
  coursesError.value = "";
  const collected: Course[] = [];
  let cursor: string | null = null;
  try {
    for (let page = 0; page < 20; page += 1) {
      const result = await api.listCourses(snapshotId, cursor, signal);
      collected.push(...result.items);
      cursor = result.nextCursor;
      if (!cursor) break;
    }
    if (signal.aborted) return;
    if (cursor) throw new Error("课程目录尚未读取完整，请重试。");
    courses.value = collected;
    coursesStatus.value = "ready";
  } catch (error) {
    if (signal.aborted) return;
    coursesStatus.value = "error";
    coursesError.value =
      error instanceof Error ? error.message : "课程列表暂时读不出来。";
  }
}

async function toggleCourse(course: Course) {
  if (
    expanded.value === course.courseCode &&
    reviewStatus.value[course.courseCode] !== "error"
  ) {
    expanded.value = null;
    return;
  }
  expanded.value = course.courseCode;
  if (
    ["ready", "loading"].includes(reviewStatus.value[course.courseCode] ?? "")
  )
    return;
  reviewStatus.value = {
    ...reviewStatus.value,
    [course.courseCode]: "loading",
  };
  try {
    const found = await api.searchReviews(course.courseCode, null);
    reviewUnconfirmed.value[course.courseCode] = found.status === "UNKNOWN";
    reviewsByCourse.value = {
      ...reviewsByCourse.value,
      [course.courseCode]: found.items,
    };
    reviewStatus.value = {
      ...reviewStatus.value,
      [course.courseCode]: "ready",
    };
  } catch {
    reviewStatus.value = {
      ...reviewStatus.value,
      [course.courseCode]: "error",
    };
  }
}

/**
 * 这门课确认绑定过的教师名。
 *
 * 只取 matchStatus 为 COURSE_TEACHER_MATCHED 的评价。实测这门课的 10 条
 * 评价全是 COURSE_ONLY，却都带着 teacherDisplayName——那是「评价提到了
 * 某个名字」，不是「服务端确认这位教师教过这门课」。把它们列成教师名单，
 * 就是把评价硬塞给某位教师，正是 TeacherReviewAssembler 明确拒绝做的事。
 *
 * 另外这也不是「这学期谁上」：那个要等选课开放。
 */
function boundTeachers(courseCode: string): string[] {
  const notes = reviewsByCourse.value[courseCode] ?? [];
  const names = notes
    .filter((note) => note.matchStatus === "COURSE_TEACHER_MATCHED")
    .map((note) => note.teacherDisplayName)
    .filter((name): name is string => typeof name === "string" && name !== "");
  return [...new Set(names)];
}

/** 带着教师名、但服务端没确认绑定的评价条数。有就要说出来，不能装看不见。 */
function unboundNoteCount(courseCode: string): number {
  const notes = reviewsByCourse.value[courseCode] ?? [];
  return notes.filter(
    (note) =>
      note.matchStatus !== "COURSE_TEACHER_MATCHED" &&
      typeof note.teacherDisplayName === "string" &&
      note.teacherDisplayName !== "",
  ).length;
}

async function openDirections() {
  askOpen.value = askOpen.value === "directions" ? "" : "directions";
  if (askOpen.value !== "directions" || directionsStatus.value === "ready")
    return;
  directionsStatus.value = "loading";
  directionsError.value = "";
  try {
    directions.value = await api.listCareerDirections();
    directionsStatus.value = "ready";
  } catch (error) {
    directionsStatus.value = "error";
    directionsError.value =
      error instanceof Error ? error.message : "职业方向暂时读不出来。";
  }
}

function toggleLearned() {
  askOpen.value = askOpen.value === "learned" ? "" : "learned";
}

async function boot() {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  bootStatus.value = "loading";
  bootError.value = "";
  try {
    if (store.sessionStatus !== "ready") await store.startSession();
    if (store.sessionStatus !== "ready") {
      bootStatus.value = "error";
      bootError.value = store.errorMessage || "没能建立本次会话。";
      return;
    }
    const initialLoads: Promise<unknown>[] = [];
    if (store.recordsStatus !== "ready") initialLoads.push(store.loadRecords());
    if (!store.schoolProgress) initialLoads.push(store.loadSchoolProgress());
    await Promise.all(initialLoads);
    if (store.selectedCurriculumId && store.selectedRecordId && !store.audit) {
      await store.runAudit();
    }
    if (store.selectedCurriculumId) {
      await loadCourses(store.selectedCurriculumId, current.signal);
    }
    if (current.signal.aborted) return;
    bootStatus.value = "ready";
  } catch (error) {
    if (current.signal.aborted) return;
    bootStatus.value = "error";
    bootError.value =
      error instanceof Error ? error.message : "控制台暂时打不开。";
  }
}

onMounted(() => void boot());
onUnmounted(() => controller?.abort());
</script>

<template>
  <section class="dashboard" aria-labelledby="dash-title">
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      页面演示 · 以下课程与进度为虚构示例
    </p>
    <header class="dashboard-heading">
      <div>
        <p class="eyebrow">从这里继续</p>
        <h1 id="dash-title" tabindex="-1">我的学业</h1>
        <p class="dashboard-subtitle">
          {{
            store.selectedCurriculum?.displayName ||
            "先连接学业资料，再开始规划"
          }}
          <span v-if="store.selectedCurriculum" class="source-pill">{{
            sourceLabel
          }}</span>
        </p>
      </div>
      <RouterLink
        class="button button--secondary"
        to="/records?import=school"
        >{{
          store.schoolProgress ? "更新学业资料" : "导入学业进度"
        }}</RouterLink
      >
    </header>
    <p v-if="bootStatus === 'loading'" class="notice" role="status">
      正在读取你的学业数据…
    </p>
    <div
      v-else-if="bootStatus === 'error'"
      class="notice notice--error"
      role="alert"
    >
      <p>{{ bootError }}</p>
      <button class="button button--secondary" type="button" @click="boot">
        重新连接
      </button>
    </div>
    <template v-else>
      <ol class="student-journey" aria-label="规划进度">
        <li>
          <span
            class="journey-dot"
            :class="{ 'is-complete': store.selectedRecordId }"
            >1</span
          >
          <div>
            <strong>了解学业</strong
            ><small>{{
              store.selectedRecordId ? "已有课程记录" : "等待导入"
            }}</small>
          </div>
        </li>
        <li>
          <span
            class="journey-dot"
            :class="{ 'is-complete': store.draft.prioritiesConfirmed }"
            >2</span
          >
          <div>
            <strong>整理需求</strong
            ><small>{{
              store.draft.prioritiesConfirmed
                ? "目标顺序已确认"
                : "兴趣、偏好与时间"
            }}</small>
          </div>
        </li>
        <li>
          <span
            class="journey-dot"
            :class="{ 'is-complete': store.planningResult }"
            >3</span
          >
          <div>
            <strong>调整方案</strong
            ><small>{{
              store.planningResult ? "已有规划结果" : "选课与课表"
            }}</small>
          </div>
        </li>
      </ol>
      <nav class="view-switch" aria-label="学业内容">
        <button
          type="button"
          data-view="progress"
          :aria-pressed="activeView === 'progress'"
          @click="selectView('progress')"
        >
          学分进度
        </button>
        <button
          type="button"
          data-view="courses"
          :aria-pressed="activeView === 'courses'"
          @click="selectView('courses')"
        >
          课程与评价
        </button>
        <button
          type="button"
          data-view="directions"
          :aria-pressed="activeView === 'directions'"
          @click="selectView('directions')"
        >
          有哪些方向
        </button>
      </nav>
      <section
        v-if="activeView === 'progress'"
        class="dashboard-panel"
        aria-labelledby="progress-title"
      >
        <div class="section-heading">
          <div>
            <h2 id="progress-title">我还缺哪些学分？</h2>
            <p v-if="store.schoolProgress" class="microcopy">
              来自本次导入的学校学业报告 · 各类别独立显示
            </p>
          </div>
          <button
            v-if="store.selectedRecord"
            class="linkbtn"
            type="button"
            @click="toggleLearned"
          >
            我学了什么
          </button>
        </div>
        <div v-if="!store.selectedCurriculum" class="empty-state">
          <template v-if="usableCurricula.length"
            ><h3>先选定你的培养方案</h3>
            <label class="dash-picker"
              ><span>培养方案</span
              ><select
                :value="store.selectedCurriculumId ?? ''"
                @change="
                  pickCurriculum(($event.target as HTMLSelectElement).value)
                "
              >
                <option disabled value="">请选择</option>
                <option
                  v-for="item in usableCurricula"
                  :key="item.snapshotId"
                  :value="item.snapshotId"
                >
                  {{ item.displayName ?? "未命名培养方案" }}
                </option>
              </select></label
            ></template
          >
          <template v-else
            ><h3>还没有可用的培养方案</h3>
            <RouterLink to="/setup">连接学业资料</RouterLink></template
          >
        </div>
        <template v-else-if="store.schoolProgress">
          <SchoolProgressTree :nodes="store.schoolProgress.snapshot.nodes" />
          <details class="record-help">
            <summary>本地培养方案核对与资料来源</summary>
            <p>
              {{
                sourceLabel
              }}；学校报告保留原类别，本地核对按所选培养方案计算。
            </p>
            <p v-if="!store.audit">
              还没有学业核对结果。<RouterLink to="/records"
                >查看资料并核对</RouterLink
              >
            </p>
            <ul v-else class="dash-audit">
              <li v-for="group in auditGroups" :key="group.key">
                <strong>{{ group.label }}</strong>
                <ul>
                  <li v-for="item in group.items" :key="item.requirementId">
                    {{ item.category ?? "类别未注明" }} ·
                    {{ formatGap(item.gapCredits) }}
                  </li>
                </ul>
              </li>
            </ul>
          </details>
        </template>
        <template v-else-if="store.audit">
          <p class="microcopy">
            以下按已填写课程核对；你也可以导入学校学业报告。
          </p>
          <ul class="dash-audit">
            <li v-for="group in auditGroups" :key="group.key">
              <strong>{{ group.label }}</strong>
              <ul>
                <li v-for="item in group.items" :key="item.requirementId">
                  {{ item.category ?? "类别未注明" }} ·
                  {{ formatGap(item.gapCredits) }}
                </li>
              </ul>
            </li>
          </ul>
        </template>
        <div v-else class="empty-state">
          <h3>导入后，就能查看学校报告的学分进度</h3>
          <p>培养方案已准备好，已有课程无需逐门重填。</p>
          <RouterLink
            class="button button--secondary"
            to="/records?import=school"
            >导入我的学业情况</RouterLink
          >
          <p class="microcopy">还没有学业核对结果。</p>
        </div>
        <p v-if="store.schoolProgressError" class="notice" role="status">
          {{ store.schoolProgressError }}
        </p>
        <div v-if="askOpen === 'learned'" class="dash-answer">
          <h3>已读取的课程</h3>
          <p v-if="!store.selectedRecord">本次会话还没有学业记录。</p>
          <template v-else
            ><p class="microcopy">
              已读取
              {{ store.selectedRecord.completedCourses.length }}
              条记录；在读课程尚未计入已获学分。
            </p>
            <ul class="dash-learned">
              <li
                v-for="(done, index) in store.selectedRecord.completedCourses"
                :key="`${done.courseCode}-${index}`"
              >
                <span>{{
                  importedCourseNames.get(done.courseCode) || done.courseCode
                }}</span
                ><span
                  >{{ outcomeLabels[done.outcome] }} ·
                  {{ formatCredits(done.earnedCredits) }}</span
                >
              </li>
            </ul></template
          >
        </div>
      </section>
      <section
        v-else-if="activeView === 'courses'"
        class="dashboard-panel"
        aria-labelledby="dash-courses"
      >
        <div class="section-heading">
          <div>
            <h2 id="dash-courses">培养方案中的课程</h2>
            <p class="microcopy">
              {{ courseCount }} 门课程 ·
              按类别浏览，点开查看历史评价。目录不代表下学期开课清单。
            </p>
          </div>
        </div>
        <label class="catalog-search"
          ><span class="visually-hidden">搜索课程号或课程名</span
          ><input
            v-model="courseQuery"
            type="search"
            placeholder="搜索课程号或课程名"
        /></label>
        <p v-if="coursesStatus === 'loading'" class="microcopy" role="status">
          正在读取课程…
        </p>
        <p
          v-else-if="coursesStatus === 'error'"
          class="notice notice--error"
          role="alert"
        >
          {{ coursesError }}
        </p>
        <p v-else-if="courseGroups.length === 0" class="empty-state">
          {{
            courseQuery
              ? "没有找到匹配课程，请换个关键词。"
              : "当前方案还没有课程资料。"
          }}
        </p>
        <details
          v-for="group in courseGroups"
          v-else
          :key="group.category"
          class="catalog-group"
          :open="Boolean(courseQuery)"
        >
          <summary>
            {{ group.category }} <span>{{ group.items.length }} 条</span>
          </summary>
          <ul class="dash-courses">
            <li
              v-for="course in group.items"
              :key="`${course.courseCode}-${course.name}`"
            >
              <button
                class="dash-course"
                type="button"
                :aria-expanded="expanded === course.courseCode"
                @click="toggleCourse(course)"
              >
                <span class="dash-course__name">{{ course.name }}</span
                ><span class="dash-course__meta"
                  >{{ course.courseCode }} · {{ formatCredits(course.credits)
                  }}<template v-if="course.suggestedTerm">
                    · 建议 {{ course.suggestedTerm }}</template
                  ></span
                ><span class="course-open" aria-hidden="true">{{
                  expanded === course.courseCode ? "−" : "+"
                }}</span>
              </button>
              <div
                v-if="expanded === course.courseCode"
                class="dash-course__body"
              >
                <p
                  v-if="reviewStatus[course.courseCode] === 'loading'"
                  class="microcopy"
                  role="status"
                >
                  正在读取评价…
                </p>
                <button
                  v-else-if="reviewStatus[course.courseCode] === 'error'"
                  type="button"
                  class="linkbtn"
                  @click="toggleCourse(course)"
                >
                  评价读取失败，点击重试
                </button>
                <template v-else
                  ><p
                    v-if="
                      (reviewsByCourse[course.courseCode] ?? []).length === 0 &&
                      !reviewUnconfirmed[course.courseCode]
                    "
                    class="microcopy"
                  >
                    暂无评价记录。
                  </p>
                  <template v-else
                    ><p
                      v-if="
                        reviewUnconfirmed[course.courseCode] &&
                        !reviewsByCourse[course.courseCode].length
                      "
                      class="microcopy"
                    >
                      评价资料状态未确认，当前没有可展示的评价记录。
                    </p>
                    <p v-else class="microcopy">
                      评价 {{ reviewsByCourse[course.courseCode].length }} 条
                    </p>
                    <p
                      v-if="boundTeachers(course.courseCode).length"
                      class="microcopy"
                    >
                      已确认教过这门课的教师：{{
                        boundTeachers(course.courseCode).join("、")
                      }}（历史记录，不代表下学期任课）
                    </p>
                    <p
                      v-if="unboundNoteCount(course.courseCode)"
                      class="microcopy"
                    >
                      部分评价没有确认这位教师教过这门课，仅按课程参考。
                    </p>
                    <ReviewSummary
                      :course-code="course.courseCode"
                      :unconfirmed="reviewUnconfirmed[course.courseCode]"
                      :notes="reviewsByCourse[course.courseCode]" /></template
                ></template>
              </div>
            </li>
          </ul>
        </details>
      </section>
      <section
        v-else
        class="dashboard-panel"
        aria-labelledby="directions-title"
      >
        <h2 id="directions-title">还没有明确方向，也可以先了解</h2>
        <p class="microcopy">
          方向资料帮助你表达兴趣，选课仍要结合培养方案和课程来源。
        </p>
        <p v-if="directionsStatus === 'loading'" role="status">
          正在读取方向资料…
        </p>
        <p
          v-else-if="directionsStatus === 'error'"
          class="notice notice--error"
          role="alert"
        >
          {{ directionsError }}
        </p>
        <p v-else-if="directions.length === 0" class="empty-state">
          暂时没有方向资料。你可以直接写下感兴趣的主题，继续需求引导。
        </p>
        <ul v-else class="dash-directions">
          <li v-for="item in directions" :key="item.directionId">
            <h3>{{ item.title }}</h3>
            <p>{{ item.description }}</p>
            <p v-if="item.courseCodes.length" class="microcopy">
              相关课程：{{
                item.courseCodes
                  .map((code) => importedCourseNames.get(code) || code)
                  .join("、")
              }}
            </p>
          </li>
        </ul>
      </section>
      <section class="plan-start" aria-labelledby="plan-start-title">
        <div>
          <p class="eyebrow">下一步 · 整理需求</p>
          <h2 id="plan-start-title">你想怎样安排下学期？</h2>
          <p class="microcopy">
            可以先讨论课程与方向；确认采用的兴趣或课程会进入本次规划草稿。完整引导仍会逐步确认目标、偏好和时间。
          </p>
        </div>
        <AdviceChat />
        <div class="plan-start__actions">
          <RouterLink class="button button--primary" to="/plan/questions/goals"
            >继续完整需求引导 →</RouterLink
          ><RouterLink
            v-if="store.planningResult"
            class="button button--secondary"
            to="/plan/result"
            >查看已有方案</RouterLink
          >
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.dashboard-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.7rem;
}
.dashboard-heading h1 {
  margin-bottom: 0.4rem;
}
.source-pill {
  display: inline-block;
  margin-left: 0.5rem;
  padding: 0.1rem 0.5rem;
  font-size: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 6px;
}
.dashboard-subtitle {
  margin: 0;
  color: var(--soft);
  font-size: 0.9rem;
}
.student-journey {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  list-style: none;
  margin: 0 0 2rem;
  padding: 1.2rem 0;
  border-block: 1px solid var(--line);
}
.student-journey li {
  display: flex;
  align-items: center;
  gap: 0.7rem;
}
.student-journey strong {
  font-size: 0.85rem;
  font-weight: 550;
}
.student-journey small {
  display: block;
  font-size: 0.75rem;
  color: var(--soft);
}
.journey-dot {
  width: 1.65rem;
  height: 1.65rem;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 50%;
  font-size: 0.75rem;
  color: var(--soft);
}
.journey-dot.is-complete {
  background: var(--green);
  border-color: var(--green);
  color: white;
}
.view-switch {
  display: flex;
  gap: 0.4rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid var(--line);
}
.view-switch button {
  background: transparent;
  color: var(--soft);
  padding: 0.8rem 1rem;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 0.9rem;
}
.view-switch button[aria-pressed="true"] {
  color: var(--green);
  font-weight: 600;
  border-bottom-color: var(--green);
}
.dashboard-panel {
  padding: 1.5rem;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface);
  min-height: 180px;
}
.dashboard-panel h2,
.plan-start h2 {
  margin: 0;
  font-size: 1.2rem;
  line-height: 1.5;
}
.dashboard-panel h3 {
  font-size: 1rem;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 1.25rem;
}
.empty-state {
  color: var(--soft);
  padding-block: 1.5rem;
}
.empty-state h3 {
  color: var(--ink);
  margin: 0 0 0.5rem;
}
.dash-picker {
  display: grid;
  gap: 0.5rem;
  max-width: 28rem;
}
.dash-picker select {
  width: 100%;
  padding: 0.65rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}
.dash-audit,
.dash-audit ul,
.dash-learned,
.dash-courses,
.dash-directions {
  list-style: none;
  padding: 0;
  margin: 0.75rem 0 0;
}
.dash-audit > li {
  padding-block: 0.5rem;
}
.dash-audit ul {
  color: var(--soft);
  font-size: 0.85rem;
  margin-top: 0.3rem;
}
.dash-learned li {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  border-bottom: 1px solid var(--line);
  padding: 0.6rem 0;
  font-size: 0.85rem;
}
.dash-learned li > span:last-child {
  color: var(--soft);
}
.dash-answer {
  background: var(--wash);
  border-radius: 12px;
  padding: 1rem;
  margin-top: 1rem;
}
.catalog-search input {
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--canvas);
  margin-bottom: 1rem;
}
.catalog-group {
  border-bottom: 1px solid var(--line);
  padding-block: 0.75rem;
}
.catalog-group > summary {
  cursor: pointer;
  font-weight: 550;
  font-size: 0.9rem;
}
.catalog-group > summary > span {
  float: right;
  color: var(--soft);
  font-weight: 400;
  font-size: 0.8rem;
}
.dash-courses > li {
  border-top: 1px solid var(--line);
}
.dash-course {
  width: 100%;
  position: relative;
  display: grid;
  gap: 0.25rem;
  text-align: left;
  border: 0;
  padding: 0.9rem 2rem 0.9rem 0.25rem;
  background: transparent;
}
.dash-course__name {
  font-weight: 550;
  font-size: 0.95rem;
}
.dash-course__meta {
  color: var(--soft);
  font-size: 0.8rem;
}
.course-open {
  position: absolute;
  right: 0.4rem;
  top: 1rem;
  color: var(--green);
}
.dash-course__body {
  padding: 0.25rem 0.5rem 1rem;
}
.dash-directions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.dash-directions li {
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
}
.dash-directions h3 {
  margin: 0 0 0.5rem;
}
.dash-directions p {
  color: var(--soft);
  font-size: 0.9rem;
}
.plan-start {
  padding: 1.6rem;
  margin-top: 1.5rem;
  border-radius: 16px;
  background: var(--wash);
  border: 1px solid var(--line);
}
.dash-ask-label {
  display: block;
  margin-top: 1.25rem;
  font-size: 0.85rem;
}
.dash-ask-input {
  display: block;
  width: 100%;
  min-height: 88px;
  padding: 0.85rem;
  margin-top: 0.5rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  resize: vertical;
}
.dash-samples {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  margin-block: 0.8rem 1.2rem;
}
.dash-sample {
  padding: 0.4rem 0.65rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  font-size: 0.75rem;
  color: var(--soft);
  text-align: left;
}
.plan-start__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
}
@media (max-width: 640px) {
  .dashboard-heading {
    align-items: flex-start;
  }
  .dashboard-heading .button {
    font-size: 0.8rem;
    padding: 0.7rem;
    min-width: auto;
  }
  .student-journey li {
    align-items: flex-start;
    gap: 0.4rem;
  }
  .student-journey small {
    font-size: 0.7rem;
  }
  .journey-dot {
    width: 1.4rem;
    height: 1.4rem;
    flex: none;
  }
  .dashboard-panel,
  .plan-start {
    padding: 1.1rem;
  }
  .view-switch {
    gap: 0;
  }
  .view-switch button {
    flex: 1;
    padding-inline: 0.3rem;
    font-size: 0.85rem;
  }
  .dash-directions {
    grid-template-columns: 1fr;
  }
  .dash-learned li {
    flex-direction: column;
    gap: 0.2rem;
  }
}
</style>
