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
  type TimetableSource,
  type WeekView,
} from "../domain/timetable";
import {
  SCHEDULE_DAYS,
  SCHEDULE_SECTIONS,
  WEEKDAY_NAMES,
  slotKey,
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
  () => view.value.placedCount > 0 && view.value.cells.size === 0,
);

const isReal = computed(() => props.scope === "REAL_TIMETABLE");
const hasAnything = computed(
  () => view.value.placedCount > 0 || view.value.gaps.length > 0,
);

function cellEntries(day: number, section: number) {
  return view.value.cells.get(slotKey(day, section)) ?? [];
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
      v-if="view.placedCount"
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
      <div v-if="view.placedCount" class="timetable-scroll">
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
                  'timetable-cell--multi': view.overlapCells.has(
                    slotKey(day, section),
                  ),
                }"
              >
                <ul
                  v-if="cellEntries(day, section).length"
                  class="timetable-stack"
                >
                  <li
                    v-for="entry in cellEntries(day, section)"
                    :key="entry.key"
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
  </div>
</template>

<style scoped>
/* 左栏只放课表；「未排进课表」列在格子下面（不并排），课程详情在右栏卡片里，这里不重复。 */
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
  height: 44px;
  padding: 3px;
}

.timetable-section {
  width: 44px;
  color: var(--soft);
  font-weight: 500;
  white-space: nowrap;
}

/* 同一格内不同班次的上课周次重叠时标红。 */
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
