<script setup lang="ts">
/**
 * 方案课表（只读）：星期 × 节次网格 + 未纳入课表的说明。
 *
 * 数据全部来自 domain/timetable.ts；这里只负责展示。
 * scope 不是 REAL_TIMETABLE 时，课表上方必须写明它不是真实课表。
 */
import { computed } from "vue";
import type { PlanScope } from "../contracts";
import { buildTimetable, type TimetableSource } from "../domain/timetable";
import {
  SCHEDULE_DAYS,
  SCHEDULE_SECTIONS,
  WEEKDAY_NAMES,
} from "../domain/schedule-grid";

const props = defineProps<{
  scope: PlanScope;
  sources: TimetableSource[];
}>();

const view = computed(() => buildTimetable(props.sources));
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

    <ul v-if="view.placed.length" class="summary-list timetable-detail">
      <li
        v-for="course in view.placed"
        :key="course.courseCode + course.classId"
      >
        {{ course.courseCode }} · 班次 {{ course.classId }} ·
        {{ course.teacherText || "教师未填写" }} ·
        {{ course.meetingTextRaw.trim() || "时间未填写" }} ·
        {{ course.weeksText }}
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

.timetable-detail {
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
