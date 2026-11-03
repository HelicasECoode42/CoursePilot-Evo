<script setup lang="ts">
/**
 * 方案课表（只读）：星期 × 节次网格 + 未纳入课表的说明。
 *
 * 数据全部来自 domain/timetable.ts；这里只负责展示。
 * scope 不是 REAL_TIMETABLE 时，课表上方必须写明它不是真实课表。
 */
import { computed, ref } from "vue";
import type { PlanScope } from "../contracts";
import {
  buildTimetable,
  compactWeeksText,
  meetingsText,
  type TimetableSource,
  type WeekView,
} from "../domain/timetable";
import {
  SCHEDULE_DAYS,
  SCHEDULE_SECTIONS,
  WEEKDAY_NAMES,
} from "../domain/schedule-grid";

const props = withDefaults(
  defineProps<{
    scope: PlanScope;
    sources: TimetableSource[];
    /** 课程号 → 课程名。读不到时明细里只显示课程号。 */
    courseNames?: Record<string, string>;
    /** 课程号 → 未排进课表的真实原因（来自方案的未知项）。没有时用通用说明。 */
    unplacedReasons?: Record<string, string>;
  }>(),
  { courseNames: () => ({}), unplacedReasons: () => ({}) },
);

/** 周次切换：全学期 / 前八周 / 后八周。只影响格子，不影响明细与未排说明。 */
const weekView = ref<WeekView>("ALL");
const WEEK_OPTIONS: { value: WeekView; label: string }[] = [
  { value: "ALL", label: "全学期" },
  { value: "FIRST_8", label: "前八周（1-8）" },
  { value: "LAST_8", label: "后八周（9-16）" },
];

const view = computed(() =>
  buildTimetable(props.sources, props.unplacedReasons, {
    weekView: weekView.value,
  }),
);
const nameOf = (courseCode: string) => props.courseNames[courseCode] ?? null;
const cellsEmptyInView = computed(
  () => view.value.placed.length > 0 && view.value.cells.size === 0,
);

/** 明细卡片：课程名、真实教师、人话时间。班次号只作小字辅助信息。 */
const detailCards = computed(() =>
  view.value.placed.map((course) => {
    const source = props.sources.find(
      (candidate) =>
        candidate.courseCode === course.courseCode &&
        candidate.classId === course.classId,
    );
    return {
      courseCode: course.courseCode,
      classId: course.classId,
      name: props.courseNames[course.courseCode] ?? null,
      teacherText: course.teacherText.trim(),
      timeText: meetingsText(source?.offering?.meetings ?? []),
    };
  }),
);
const isReal = computed(() => props.scope === "REAL_TIMETABLE");
const hasAnything = computed(
  () => view.value.placed.length > 0 || view.value.gaps.length > 0,
);

function cellEntries(day: number, section: number) {
  return view.value.cells.get(`${day}-${section}`) ?? [];
}

/** 格子里截断后，完整信息放在悬停提示里。 */
function chipTitle(entry: {
  courseCode: string;
  classId: string;
  teacherText: string;
  weeks: number[];
}): string {
  const name = nameOf(entry.courseCode) ?? entry.courseCode;
  const teacher = entry.teacherText.trim() || "教师未填写";
  return `${name} · ${teacher} · ${compactWeeksText(entry.weeks)} · ${entry.classId}`;
}

function dayLabel(day: number): string {
  return WEEKDAY_NAMES[day - 1];
}
</script>

<template>
  <div class="plan-timetable">
    <p v-if="!isReal" class="microcopy" role="note">
      此课表来自未经核验的班次资料，不代表真实课表，不构成无冲突证明。
    </p>

    <p v-if="!hasAnything" class="microcopy">
      这份方案里还没有选定班次的课程，课表为空。
    </p>

    <div
      v-if="view.placed.length"
      class="timetable-weeks"
      role="group"
      aria-label="周次范围"
    >
      <button
        v-for="option in WEEK_OPTIONS"
        :key="option.value"
        type="button"
        class="timetable-weeks__btn"
        :aria-pressed="weekView === option.value"
        :class="{ 'timetable-weeks__btn--on': weekView === option.value }"
        @click="weekView = option.value"
      >
        {{ option.label }}
      </button>
    </div>
    <p v-if="cellsEmptyInView" class="microcopy" role="status">
      所选周次范围内没有这些课的上课时段，可切换到全学期查看。
    </p>

    <div class="timetable-layout">
      <div v-if="view.placed.length" class="timetable-scroll">
        <table class="timetable">
          <caption class="sr-only">
            一周课表，列为星期，行为节次
          </caption>
          <thead>
            <tr>
              <th scope="col" class="timetable-corner">节次</th>
              <th v-for="day in SCHEDULE_DAYS" :key="day" scope="col">
                {{ dayLabel(day) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="section in SCHEDULE_SECTIONS" :key="section">
              <th scope="row" class="timetable-section">第{{ section }}节</th>
              <td
                v-for="day in SCHEDULE_DAYS"
                :key="day"
                :class="{
                  'timetable-cell--multi': cellEntries(day, section).length > 1,
                }"
              >
                <ul
                  v-if="cellEntries(day, section).length"
                  class="timetable-stack"
                >
                  <li
                    v-for="entry in cellEntries(day, section)"
                    :key="entry.courseCode + entry.classId"
                    class="timetable-chip"
                    :title="chipTitle(entry)"
                  >
                    <strong class="timetable-chip__name">{{
                      nameOf(entry.courseCode) ?? entry.courseCode
                    }}</strong>
                    <span class="timetable-chip__line">{{
                      entry.teacherText.trim() || "教师未填写"
                    }}</span>
                    <span class="timetable-chip__line timetable-chip__meta"
                      >{{ compactWeeksText(entry.weeks) }} ·
                      {{ entry.classId }}</span
                    >
                  </li>
                </ul>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <aside
        v-if="view.gaps.length"
        class="timetable-gaps"
        aria-labelledby="timetable-unplaced-title"
      >
        <h4 id="timetable-unplaced-title" class="timetable-gaps__title">
          未排进课表
        </h4>
        <p class="microcopy">以下课程不在上面的格子里，原因如下：</p>
        <ul class="summary-list">
          <li v-for="gap in view.gaps" :key="gap.courseCode + gap.message">
            {{ gap.message }}
          </li>
        </ul>
      </aside>
    </div>

    <ul
      v-if="detailCards.length"
      class="timetable-cards"
      aria-label="已排入课表的班次明细"
    >
      <li
        v-for="course in detailCards"
        :key="course.courseCode + course.classId"
        class="timetable-card"
      >
        <div class="timetable-card__title">
          <strong>{{ course.name ?? course.courseCode }}</strong>
          <span v-if="course.name" class="timetable-card__code">{{
            course.courseCode
          }}</span>
        </div>
        <dl class="timetable-card__facts">
          <div>
            <dt>教师</dt>
            <dd>{{ course.teacherText || "教师未填写" }}</dd>
          </div>
          <div>
            <dt>上课时间</dt>
            <dd>{{ course.timeText }}</dd>
          </div>
          <div>
            <dt>班次</dt>
            <dd class="timetable-card__small">{{ course.classId }}</dd>
          </div>
        </dl>
      </li>
    </ul>
  </div>
</template>

<style scoped>
/* 「未排进课表」列在课表格子下面（不并排），课程卡片上也有同一原因，这里只做清单。 */
.timetable-layout {
  display: grid;
  gap: 12px;
}

.timetable-gaps {
  padding: 12px 14px;
  border-radius: 9px;
  color: #875817;
  background: #fff8ed;
  font-size: 13px;
}

.timetable-gaps__title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
}

.timetable-scroll {
  max-width: 100%;
  overflow-x: auto;
  margin: 12px 0 0;
}

.timetable {
  width: 100%;
  min-width: 0;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 12px;
}

/* 窄屏（手机）保留横向滚动，桌面让课表撑满左栏。 */
@media (max-width: 760px) {
  .timetable {
    min-width: 560px;
  }
}

.timetable th,
.timetable td {
  border: 1px solid var(--line);
  padding: 4px;
  vertical-align: top;
  text-align: center;
}

.timetable thead th {
  color: var(--ink);
  font-weight: 550;
  background: #f4f7f5;
}

.timetable tbody td {
  height: 52px;
  padding: 3px;
}

.timetable-section {
  width: 44px;
  color: var(--soft);
  font-weight: 500;
  white-space: nowrap;
}

/* 同一格有两门以上课，即时间重叠：整格标红，并给出文字标记（不只靠颜色）。 */
.timetable-cell--multi {
  background: #fff4f2;
  box-shadow: inset 0 0 0 1px #efc4bd;
}

.timetable-cell--multi .timetable-chip {
  color: #8b3c31;
  background: #fbe3df;
}

.timetable-stack {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 3px;
}

.timetable-chip {
  display: grid;
  gap: 0;
  min-width: 0;
  padding: 3px 4px;
  border-radius: 6px;
  color: #164f55;
  background: #e8f1ef;
  text-align: left;
  font-size: 11px;
  line-height: 1.3;
}

/* 课程名最多两行，超出省略；教师与周次各占一行，超出省略。 */
.timetable-chip__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  font-size: 12px;
  font-weight: 600;
}

.timetable-chip__line {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.timetable-chip__meta {
  color: var(--soft);
  font-size: 10.5px;
}

.timetable-weeks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 12px 0 0;
}

.timetable-weeks__btn {
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--canvas);
  color: var(--ink);
  font-size: 12px;
  cursor: pointer;
}

.timetable-weeks__btn--on {
  border-color: var(--green);
  background: var(--green-soft, #e7f4ec);
  color: var(--green);
  font-weight: 600;
}

/* 明细卡片：浅绿色圆角，沿用全局 --wash / --line 变量。 */
.timetable-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr));
  gap: 10px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.timetable-card {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--wash);
}

.timetable-card__title strong {
  display: block;
  color: var(--ink);
  font-size: 16px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.timetable-card__code {
  display: block;
  color: var(--soft);
  font-size: 12px;
}

.timetable-card__facts {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
}

.timetable-card__facts div {
  display: grid;
  grid-template-columns: 4.5em minmax(0, 1fr);
  gap: 8px;
}

.timetable-card__facts dt {
  color: var(--soft);
  font-size: 12px;
}

.timetable-card__facts dd {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.timetable-card__facts .timetable-card__small {
  color: var(--soft);
  font-size: 12px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
