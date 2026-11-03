<script setup lang="ts">
import { computed } from "vue";
import type { CourseNameLookup } from "../domain/course-names";
import {
  courseDisplayName,
  creditsLabel,
  hasAnyCredit,
  hasChildNodes,
  majorRootOf,
  nodeHasContent,
  nodeName,
  remainingSummaryLine,
  SCHOOL_OUTCOME_LABELS,
  UNREAD_CATEGORY_NAME,
} from "../domain/school-categories";
import type {
  SchoolProgressCourse,
  SchoolProgressNode,
} from "../domain/school-progress";

const props = withDefaults(
  defineProps<{
    nodes: SchoolProgressNode[];
    courses?: SchoolProgressCourse[];
    parentId?: string | null;
    /** 课程名的备用来源（课程目录）。学校报告里的课程名读不出来时用它补。 */
    nameLookup?: CourseNameLookup;
    /** 是否在顶部显示「按学校报告还差」一句（嵌在紧凑摘要里时关掉，避免重复）。 */
    showSummary?: boolean;
  }>(),
  {
    parentId: null,
    courses: () => [],
    nameLookup: undefined,
    showSummary: true,
  },
);
const hasChildren = (id: string) => hasChildNodes(id, props.nodes);
const coursesOf = (id: string) =>
  (props.courses ?? []).filter((course) => course.nodeId === id);
const visibleNodes = computed(() =>
  props.nodes.filter(
    (node) =>
      node.parentId === props.parentId &&
      nodeHasContent(node, props.nodes, props.courses ?? []),
  ),
);
const creditLabel = (value: number | null) =>
  value === null ? "待确认" : String(value);
const remainingOf = (node: SchoolProgressNode) => node.remainingCredits ?? 0;
const unknownLayerNote = (node: SchoolProgressNode) =>
  hasChildren(node.nodeId)
    ? "学校页面没有给出这一层的总学分，请看下面各类别"
    : "学校页面没有给出这一层的总学分，请看下面课程";
/** 默认展开的只有「主修」这一层本身（它的第一级子类别直接可见），更深的层级保持收起。 */
const majorRoot = computed(() => majorRootOf(props.nodes));
const isMajorRoot = (node: SchoolProgressNode) =>
  majorRoot.value !== null && majorRoot.value.nodeId === node.nodeId;
/** 顶层摘要，口径见 remainingSummaryLine。 */
const remainingSummary = computed(() =>
  props.parentId !== null || !props.showSummary
    ? ""
    : remainingSummaryLine(props.nodes),
);
const titleOf = (node: SchoolProgressNode) => nodeName(node);
const isUnnamed = (node: SchoolProgressNode) =>
  nodeName(node) === UNREAD_CATEGORY_NAME;
const courseName = (course: SchoolProgressCourse) =>
  courseDisplayName(course.courseCode, course.name, props.nameLookup);
</script>

<template>
  <p v-if="remainingSummary" class="school-remaining-summary">
    {{ remainingSummary }}
  </p>
  <ul
    class="school-progress-tree"
    :class="{ 'school-progress-tree--nested': parentId !== null }"
  >
    <li v-for="node in visibleNodes" :key="node.nodeId" class="school-category">
      <h3 :class="{ 'school-category__unnamed': isUnnamed(node) }">
        {{ titleOf(node) }}
      </h3>
      <span v-if="remainingOf(node) > 0" class="school-category__badge">
        还差 {{ node.remainingCredits }} 学分
      </span>
      <p v-if="!hasAnyCredit(node)" class="school-category__muted">
        {{ unknownLayerNote(node) }}
      </p>
      <template v-else>
        <p class="school-category__source">学校报告</p>
        <dl>
          <div>
            <dt>要求</dt>
            <dd
              :class="{
                'school-category__unknown': node.requiredCredits === null,
              }"
            >
              {{ creditLabel(node.requiredCredits) }}
            </dd>
          </div>
          <div>
            <dt>已获</dt>
            <dd
              :class="{
                'school-category__unknown': node.earnedCredits === null,
              }"
            >
              {{ creditLabel(node.earnedCredits) }}
            </dd>
          </div>
          <div class="school-category__remaining">
            <dt>还差</dt>
            <dd
              :class="{
                'school-category__unknown': node.remainingCredits === null,
              }"
            >
              {{ creditLabel(node.remainingCredits) }}
            </dd>
          </div>
        </dl>
      </template>
      <details
        v-if="hasChildren(node.nodeId) || coursesOf(node.nodeId).length"
        :open="isMajorRoot(node)"
      >
        <summary>
          {{ hasChildren(node.nodeId) ? "查看子类别" : "查看关联课程" }}
          <template v-if="coursesOf(node.nodeId).length">
            · {{ coursesOf(node.nodeId).length }} 门课程
          </template>
        </summary>
        <ul v-if="coursesOf(node.nodeId).length" class="school-courses">
          <li
            v-for="(course, index) in coursesOf(node.nodeId)"
            :key="`${course.courseCode}:${index}`"
          >
            <span class="school-course-name"
              >{{ courseName(course) }} · {{ course.courseCode }}</span
            >
            <span class="school-course-meta">
              {{ creditsLabel(course.credits) }} ·
              {{ SCHOOL_OUTCOME_LABELS[course.outcome] }}
            </span>
          </li>
        </ul>
        <SchoolProgressTree
          v-if="hasChildren(node.nodeId)"
          :nodes="nodes"
          :courses="courses"
          :parent-id="node.nodeId"
          :name-lookup="nameLookup"
        />
      </details>
    </li>
  </ul>
</template>

<style scoped>
.school-progress-tree {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.8rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.school-category {
  position: relative;
  min-width: 0;
  background: var(--canvas);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 1rem;
}
.school-category h3 {
  margin: 0 0 0.8rem;
  padding-right: 6rem;
  font-size: 0.9rem;
  font-weight: 550;
}
.school-category__badge {
  position: absolute;
  top: 0.85rem;
  right: 0.9rem;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--green-soft, #e7f4ec);
  color: var(--green);
  font-size: 0.72rem;
  font-weight: 600;
  white-space: nowrap;
}
.school-category__source {
  margin: -0.4rem 0 0.5rem;
  color: var(--soft);
  font-size: 0.72rem;
}
.school-category__muted {
  margin: 0;
  color: var(--soft);
  font-size: 0.82rem;
}
.school-category dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0;
}
.school-category dt {
  color: var(--soft);
  font-size: 0.75rem;
}
.school-category dd {
  margin: 0.2rem 0 0;
  font-size: 1.3rem;
  font-variant-numeric: tabular-nums;
}
.school-category__remaining dd {
  color: var(--green);
  font-weight: 600;
}
.school-category__unknown {
  color: var(--soft) !important;
  font-size: 0.95rem !important;
  font-weight: 400 !important;
}
.school-remaining-summary {
  margin: 0 0 0.8rem;
  font-size: 0.88rem;
  font-weight: 550;
}
.school-category details {
  margin-top: 0.75rem;
}
.school-category summary {
  color: var(--green);
  font-size: 0.8rem;
  cursor: pointer;
}
.school-courses {
  display: grid;
  gap: 0.4rem;
  margin: 0.65rem 0 0;
  padding: 0;
  list-style: none;
}
.school-courses li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.2rem 0.7rem;
  padding: 0.45rem 0;
  border-top: 1px solid var(--line);
  font-size: 0.82rem;
}
.school-course-meta {
  color: var(--soft);
}
.school-category__unnamed {
  color: var(--soft);
  font-weight: 400;
}
.school-progress-tree--nested {
  grid-template-columns: 1fr;
  margin-top: 0.75rem;
}
.school-progress-tree--nested .school-category {
  background: var(--surface);
}
@media (max-width: 540px) {
  .school-progress-tree {
    grid-template-columns: 1fr;
  }
}
</style>
