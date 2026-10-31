<script setup lang="ts">
/**
 * 方案课表（只读）：星期 × 节次网格 + 未纳入课表的说明。
 *
 * 数据全部来自 domain/timetable.ts；这里只负责展示。
 * scope 不是 REAL_TIMETABLE 时，课表上方必须写明它不是真实课表。
 */
import { computed } from "vue";
import type { PlanScope } from "../contracts";
import {
  buildTimetable,
  meetingsText,
  type TimetableSource,
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
  }>(),
  { courseNames: () => ({}) },
);

const view = computed(() => buildTimetable(props.sources));

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

function dayLabel(day: number): string {
  return WEEKDAY_NAMES[day - 1];
}
</script>

<template>
  <div class="plan-timetable">
    <p v-if="!isReal" class="notice notice--warning" role="note">
      此课表来自未经核验的班次资料，不代表真实课表，不构成无冲突证明。
    </p>

    <p v-if="!hasAnything" class="microcopy">
      这份方案里还没有选定班次的课程，课表为空。
    </p>

    <div
      v-if="view.gaps.length"
      class="notice notice--warning timetable-gaps"
      role="note"
    >
      <p>以下课程的时间不能画进课表，它们不在下面的格子里：</p>
      <ul class="summary-list">
        <li v-for="gap in view.gaps" :key="gap.courseCode + gap.message">
          {{ gap.message }}
        </li>
      </ul>
    </div>

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
                >
                  <strong>{{ entry.courseCode }}</strong>
                  <span>{{ entry.classId }}</span>
                </li>
              </ul>
            </td>
          </tr>
        </tbody>
      </table>
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
.timetable-scroll {
  max-width: 100%;
  overflow-x: auto;
  margin: 12px 0 0;
}

.timetable {
  width: 100%;
  min-width: 520px;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 12px;
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

.timetable-section {
  width: 56px;
  color: var(--soft);
  font-weight: 500;
  white-space: nowrap;
}

.timetable-cell--multi {
  background: #fff8ed;
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
  gap: 1px;
  padding: 3px 4px;
  border-radius: 6px;
  color: #164f55;
  background: #e8f1ef;
  overflow-wrap: anywhere;
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
