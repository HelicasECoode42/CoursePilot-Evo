<script setup lang="ts">
import { computed } from "vue";
import type { CourseNameLookup } from "../domain/course-names";
import {
  courseDisplayName,
  creditsLabel,
  nodeName,
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
  }>(),
  { parentId: null, courses: () => [], nameLookup: undefined },
);
const visibleNodes = computed(() =>
  props.nodes.filter((node) => node.parentId === props.parentId),
);
const hasChildren = (id: string) =>
  props.nodes.some((node) => node.parentId === id);
const coursesOf = (id: string) =>
  (props.courses ?? []).filter((course) => course.nodeId === id);
const creditLabel = (value: number | null) =>
  value === null ? "待确认" : String(value);
const titleOf = (node: SchoolProgressNode) => nodeName(node);
const isUnnamed = (node: SchoolProgressNode) =>
  nodeName(node) === UNREAD_CATEGORY_NAME;
const courseName = (course: SchoolProgressCourse) =>
  courseDisplayName(course.courseCode, course.name, props.nameLookup);
</script>

<template>
  <ul
    class="school-progress-tree"
    :class="{ 'school-progress-tree--nested': parentId !== null }"
  >
    <li v-for="node in visibleNodes" :key="node.nodeId" class="school-category">
      <h3 :class="{ 'school-category__unnamed': isUnnamed(node) }">
        {{ titleOf(node) }}
      </h3>
      <dl>
        <div>
          <dt>要求</dt>
          <dd>{{ creditLabel(node.requiredCredits) }}</dd>
        </div>
        <div>
          <dt>已获</dt>
          <dd>{{ creditLabel(node.earnedCredits) }}</dd>
        </div>
        <div class="school-category__remaining">
          <dt>还差</dt>
          <dd>{{ creditLabel(node.remainingCredits) }}</dd>
        </div>
      </dl>
      <details v-if="hasChildren(node.nodeId) || coursesOf(node.nodeId).length">
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
  min-width: 0;
  background: var(--canvas);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 1rem;
}
.school-category h3 {
  margin: 0 0 0.8rem;
  font-size: 0.9rem;
  font-weight: 550;
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
