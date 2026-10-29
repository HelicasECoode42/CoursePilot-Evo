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
import { groupAuditItems } from "../domain/academic-record";
import { isCurriculumUsableForMode } from "../domain/planning-request";
import { usePlanningStore } from "../stores/planning";

const store = usePlanningStore();

type Load = "idle" | "loading" | "ready" | "error";

const bootStatus = ref<Load>("idle");
const bootError = ref("");

const courses = ref<Course[]>([]);
const coursesStatus = ref<Load>("idle");
const coursesError = ref("");

const expanded = ref<string | null>(null);
const reviewsByCourse = ref<Record<string, ReviewNote[]>>({});
const reviewStatus = ref<Record<string, Load>>({});

const directions = ref<CareerDirection[]>([]);
const directionsStatus = ref<Load>("idle");
const directionsError = ref("");

const askOpen = ref<"" | "learned" | "directions">("");

let controller: AbortController | null = null;

const DIMENSION_LABELS: Record<ReviewNote["dimensions"][number], string> = {
  GRADING: "给分",
  ATTENDANCE: "签到",
  WORKLOAD: "工作量",
  EXAM: "考试",
  GROUP_WORK: "小组作业",
  PRESENTATION: "课堂汇报",
  TEACHING: "讲课",
  OVERALL: "综合",
};

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
    const key = course.category || "未注明类别";
    const bucket = byCategory.get(key);
    if (bucket) bucket.push(course);
    else byCategory.set(key, [course]);
  }
  return [...byCategory.entries()]
    .map(([category, items]) => ({ category, items }))
    .sort((a, b) => b.items.length - a.items.length);
});

const courseCount = computed(() => courses.value.length);

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
  if (expanded.value === course.courseCode) {
    expanded.value = null;
    return;
  }
  expanded.value = course.courseCode;
  if (reviewStatus.value[course.courseCode]) return;
  reviewStatus.value = {
    ...reviewStatus.value,
    [course.courseCode]: "loading",
  };
  try {
    const found = await api.searchReviews(course.courseCode, null);
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

function dimensionsOf(courseCode: string): string[] {
  const notes = reviewsByCourse.value[courseCode] ?? [];
  const tags = new Set<string>();
  for (const note of notes) {
    for (const dimension of note.dimensions) {
      tags.add(DIMENSION_LABELS[dimension] ?? dimension);
    }
  }
  return [...tags];
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
    await Promise.all([store.loadRecords(), store.loadSchoolProgress()]);
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
  <section class="question-card" aria-labelledby="dash-title">
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      当前是演示模式：下面的课程和评价是虚构示例，不是真实教务数据。
    </p>
    <p class="eyebrow">个人控制台</p>
    <h1 id="dash-title">我的学业与可选课程</h1>

    <p v-if="bootStatus === 'loading'" class="microcopy" role="status">
      正在读取你的学业数据…
    </p>
    <div v-else-if="bootStatus === 'error'">
      <p class="notice notice--error" role="alert">{{ bootError }}</p>
      <button class="button button--secondary" type="button" @click="boot">
        重试
      </button>
    </div>

    <template v-else>
      <!-- ① 我的状态 -->
      <section class="dash-block" aria-labelledby="dash-status">
        <h2 id="dash-status">我的状态</h2>
        <div v-if="!store.selectedCurriculum">
          <p v-if="usableCurricula.length === 0" class="notice" role="note">
            还没有可用的培养方案。
            <RouterLink to="/setup">回到配置</RouterLink>
            把学校数据接上，这一页才有内容。
          </p>
          <template v-else>
            <p class="microcopy">
              有 {{ usableCurricula.length }} 份培养方案可用，先选一份。
              来源核验状态照原样列出，不替你挑「看起来更可信」的那份。
            </p>
            <label class="dash-picker">
              <span>培养方案</span>
              <select
                :value="store.selectedCurriculumId ?? ''"
                @change="
                  pickCurriculum(
                    ($event.target as HTMLSelectElement | null)?.value ?? '',
                  )
                "
              >
                <option value="" disabled>请选择</option>
                <option
                  v-for="item in usableCurricula"
                  :key="item.snapshotId"
                  :value="item.snapshotId"
                >
                  {{ item.displayName ?? item.snapshotId }} ·
                  {{ item.sourceKind }} · {{ item.sourceValidation }}
                </option>
              </select>
            </label>
          </template>
        </div>
        <template v-else>
          <p class="dash-plan">
            {{ store.selectedCurriculum.displayName ?? "未命名培养方案" }}
            <span class="dash-badge">
              来源核验：{{ store.selectedCurriculum.sourceValidation }}
            </span>
          </p>
          <p v-if="!store.audit" class="microcopy">
            还没有学业核对结果。
            <RouterLink to="/records">去学业资料页核对</RouterLink>。
          </p>
          <ul v-else class="dash-audit">
            <li v-for="group in auditGroups" :key="group.key">
              <strong>{{ group.label }}</strong>
              <ul>
                <li v-for="item in group.items" :key="item.requirementId">
                  {{ item.category ?? item.requirementId }} ·
                  {{ formatGap(item.gapCredits) }}
                </li>
              </ul>
            </li>
          </ul>
        </template>
      </section>

      <!-- ② 问一问 -->
      <section class="dash-block" aria-labelledby="dash-ask">
        <h2 id="dash-ask">问一问</h2>
        <p class="microcopy">
          前两个问题的答案是确定的，直接来自学校数据与 Java
          的核对，<strong>不经过模型</strong>；想让 AI 给成套的选课建议，
          走下面的「开始选课」。
        </p>
        <div class="dash-ask-row">
          <button
            class="button button--secondary"
            type="button"
            @click="toggleLearned"
          >
            我学了什么
          </button>
          <button
            class="button button--secondary"
            type="button"
            @click="openDirections"
          >
            有哪些方向，分别要学什么
          </button>
          <RouterLink
            class="button button--secondary"
            to="/plan/questions/goals"
          >
            我还能学什么
          </RouterLink>
        </div>

        <div v-if="askOpen === 'learned'" class="dash-answer">
          <p v-if="!store.selectedRecord" class="microcopy">
            本次会话还没有学业记录。
            <RouterLink to="/records">去补录或导入</RouterLink>。
          </p>
          <template v-else>
            <p class="microcopy">
              共 {{ store.selectedRecord.completedCourses.length }} 条课程记录。
              {{
                store.selectedRecord.transcriptComplete
                  ? "已声明记录完整。"
                  : "未声明完整，所以会有「无法确认」的要求。"
              }}
            </p>
            <ul class="dash-learned">
              <li
                v-for="(done, index) in store.selectedRecord.completedCourses"
                :key="`${done.courseCode}-${index}`"
              >
                {{ done.courseCode }} · {{ done.outcome }} ·
                {{ formatCredits(done.earnedCredits) }}
              </li>
            </ul>
          </template>
        </div>

        <div v-if="askOpen === 'directions'" class="dash-answer">
          <p
            v-if="directionsStatus === 'loading'"
            class="microcopy"
            role="status"
          >
            正在读取职业方向…
          </p>
          <p
            v-else-if="directionsStatus === 'error'"
            class="notice notice--error"
            role="alert"
          >
            {{ directionsError }}
          </p>
          <p v-else-if="directions.length === 0" class="microcopy">
            服务端没有返回职业方向。这是正常业务状态，不是错误。
          </p>
          <ul v-else class="dash-directions">
            <li v-for="item in directions" :key="item.directionId">
              <strong>{{ item.title }}</strong>
              <p class="microcopy">{{ item.description }}</p>
              <p class="microcopy">
                建议课程：{{
                  item.courseCodes.length > 0
                    ? item.courseCodes.join("、")
                    : "未给出课程号"
                }}
              </p>
            </li>
          </ul>
        </div>
      </section>

      <!-- ③ 看开什么课 -->
      <section class="dash-block" aria-labelledby="dash-courses">
        <h2 id="dash-courses">看开什么课</h2>
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
        <template v-else>
          <p class="microcopy">
            培养方案里共 {{ courseCount }} 条课程记录，按要求类别分组。
            点开一门课才会去查它的评价。
            <strong>本学期谁上课、周几第几节，要等选课开放才公开。</strong>
          </p>
          <div v-for="group in courseGroups" :key="group.category">
            <h3 class="dash-category">
              {{ group.category }}
              <span class="dash-count">{{ group.items.length }} 条</span>
            </h3>
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
                  <span class="dash-course__name">{{ course.name }}</span>
                  <span class="dash-course__meta">
                    {{ course.courseCode }} ·
                    {{ formatCredits(course.credits) }}
                    <template v-if="course.suggestedTerm">
                      · 建议 {{ course.suggestedTerm }}
                    </template>
                  </span>
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
                  <p
                    v-else-if="reviewStatus[course.courseCode] === 'error'"
                    class="microcopy"
                  >
                    评价暂时读不出来，再点一次可重试。
                  </p>
                  <template v-else>
                    <p
                      v-if="
                        (reviewsByCourse[course.courseCode] ?? []).length === 0
                      "
                      class="microcopy"
                    >
                      暂无评价记录。
                    </p>
                    <template v-else>
                      <p class="microcopy">
                        评价 {{ reviewsByCourse[course.courseCode].length }} 条
                        · 维度：{{
                          dimensionsOf(course.courseCode).join(" / ")
                        }}
                      </p>
                      <p
                        v-if="boundTeachers(course.courseCode).length > 0"
                        class="microcopy"
                      >
                        已确认教过这门课的教师：{{
                          boundTeachers(course.courseCode).join("、")
                        }}（历史记录，不代表本学期谁上）
                      </p>
                      <p
                        v-if="unboundNoteCount(course.courseCode) > 0"
                        class="microcopy"
                      >
                        另有 {{ unboundNoteCount(course.courseCode) }}
                        条评价提到了教师名，但服务端没有确认这位教师教过这门课，
                        所以不列进上面的名单。
                      </p>
                      <ul class="dash-excerpts">
                        <li
                          v-for="note in reviewsByCourse[course.courseCode]"
                          :key="note.reviewNoteId"
                        >
                          <blockquote>{{ note.excerpt }}</blockquote>
                          <span class="microcopy">
                            {{ note.termId ?? "学期未注明" }} ·
                            {{ note.matchStatus }}
                          </span>
                        </li>
                      </ul>
                    </template>
                  </template>
                </div>
              </li>
            </ul>
          </div>
        </template>
      </section>

      <!-- ④ 开始选课 -->
      <section class="dash-block" aria-labelledby="dash-start">
        <h2 id="dash-start">开始选课</h2>
        <p class="microcopy">
          进现有的规划流程：先问几个问题，再按学分缺口挑课，最后给出方案。
        </p>
        <RouterLink class="button button--primary" to="/plan/questions/goals">
          开始选课
        </RouterLink>
      </section>
    </template>
  </section>
</template>

<style scoped>
.dash-block {
  margin: 1.25rem 0;
  padding: 1rem 1.1rem;
  border: 1px solid var(--line);
  border-radius: 14px;
}

.dash-block h2 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}

.dash-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin: 0.5rem 0;
  font-size: 0.88rem;
}

.dash-picker select {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: white;
  font-size: 0.88rem;
  max-width: 100%;
}

.dash-plan {
  margin: 0 0 0.5rem;
  font-weight: 550;
}

.dash-badge {
  margin-left: 0.5rem;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--wash);
  border: 1px solid var(--line);
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--soft);
  white-space: nowrap;
}

.dash-audit,
.dash-audit ul,
.dash-courses,
.dash-directions,
.dash-learned,
.dash-excerpts {
  list-style: none;
  margin: 0.35rem 0 0;
  padding: 0;
}

.dash-audit > li {
  margin-bottom: 0.6rem;
}

.dash-audit ul li,
.dash-learned li {
  font-size: 0.88rem;
  color: var(--soft);
  padding: 2px 0;
}

.dash-ask-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 0.5rem 0;
}

.dash-answer {
  margin-top: 0.75rem;
  padding: 0.85rem 1rem;
  border-radius: 12px;
  background: var(--wash);
}

.dash-directions > li {
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--line);
}

.dash-directions > li:last-child {
  border-bottom: 0;
}

.dash-category {
  margin: 1rem 0 0.35rem;
  font-size: 0.9rem;
  color: var(--soft);
}

.dash-count {
  font-weight: 400;
}

.dash-courses > li {
  border: 1px solid var(--line);
  border-radius: 12px;
  margin-bottom: 0.5rem;
  overflow: hidden;
}

.dash-course {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: 100%;
  padding: 0.7rem 0.85rem;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.dash-course:hover {
  background: var(--wash);
}

.dash-course__name {
  font-weight: 550;
  color: var(--ink);
}

.dash-course__meta {
  font-size: 0.8rem;
  color: var(--soft);
}

.dash-course__body {
  padding: 0 0.85rem 0.8rem;
  border-top: 1px solid var(--line);
}

.dash-excerpts > li {
  padding: 0.4rem 0;
}

.dash-excerpts blockquote {
  margin: 0 0 2px;
  padding-left: 0.65rem;
  border-left: 3px solid var(--line);
  font-size: 0.88rem;
  line-height: 1.6;
}

@media (max-width: 540px) {
  .dash-ask-row {
    flex-direction: column;
  }

  .dash-ask-row > * {
    width: 100%;
  }
}
</style>
