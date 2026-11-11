<script setup lang="ts">
import { computed } from "vue";
import type { CourseNameLookup } from "../domain/course-names";
import {
  firstLevelNodes,
  nodeName,
  remainingSummaryLine,
} from "../domain/school-categories";
import type {
  SchoolProgressCourse,
  SchoolProgressNode,
} from "../domain/school-progress";
import SchoolProgressTree from "./SchoolProgressTree.vue";

/**
 * 「我的」页的学校进度紧凑摘要：一句还差 + 第一级类别表格。
 * 完整的类别树收在「查看全部类别」里，口径与 /records 的 SchoolProgressTree 相同。
 */
const props = withDefaults(
  defineProps<{
    nodes: SchoolProgressNode[];
    courses?: SchoolProgressCourse[];
    nameLookup?: CourseNameLookup;
  }>(),
  { courses: () => [], nameLookup: undefined },
);

const summaryLine = computed(() => remainingSummaryLine(props.nodes));
const rows = computed(() =>
  firstLevelNodes(props.nodes, props.courses).map((node) => ({
    key: node.nodeId,
    name: nodeName(node),
    earned: node.earnedCredits,
    required: node.requiredCredits,
    remaining: node.remainingCredits,
  })),
);
const numberOrPending = (value: number | null) =>
  value === null ? "待确认" : String(value);
const remainingText = (remaining: number | null) => {
  if (remaining === null) return "待确认";
  if (remaining > 0) return `还差 ${remaining}`;
  return "已凑满";
};
</script>

<template>
  <div class="school-progress-summary">
    <p v-if="summaryLine" class="school-summary-line">{{ summaryLine }}</p>
    <table v-if="rows.length" class="school-summary-table">
      <thead>
        <tr>
          <th scope="col">类别</th>
          <th scope="col">已获 / 要求</th>
          <th scope="col">还差</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key">
          <th scope="row">{{ row.name }}</th>
          <td>
            {{ numberOrPending(row.earned) }} /
            {{ numberOrPending(row.required) }}
          </td>
          <td>
            <span
              class="school-summary-badge"
              :class="{ 'school-summary-badge--done': row.remaining === 0 }"
            >
              {{ remainingText(row.remaining) }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <details class="school-summary-all">
      <summary>查看全部类别</summary>
      <SchoolProgressTree
        :nodes="nodes"
        :courses="courses"
        :name-lookup="nameLookup"
        :show-summary="false"
      />
    </details>
  </div>
</template>

<style scoped>
.school-summary-line {
  margin: 0 0 0.7rem;
  font-size: 0.88rem;
  font-weight: 550;
}
.school-summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.school-summary-table th,
.school-summary-table td {
  padding: 0.45rem 0.4rem;
  border-top: 1px solid var(--line);
  text-align: left;
  vertical-align: middle;
}
.school-summary-table thead th {
  border-top: 0;
  color: var(--soft);
  font-size: 0.75rem;
  font-weight: 500;
}
.school-summary-table tbody th {
  font-weight: 500;
}
.school-summary-badge {
  display: inline-block;
  padding: 0.12rem 0.5rem;
  border-radius: 999px;
  background: var(--green-soft, #e7f4ec);
  color: var(--green);
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}
.school-summary-badge--done {
  background: transparent;
  color: var(--soft);
  font-weight: 400;
}
.school-summary-all {
  margin-top: 0.7rem;
}
.school-summary-all > summary {
  color: var(--green);
  font-size: 0.8rem;
  cursor: pointer;
}
.school-summary-all :deep(.school-progress-tree) {
  margin-top: 0.8rem;
}
</style>
