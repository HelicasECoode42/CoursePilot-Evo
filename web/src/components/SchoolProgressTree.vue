<script setup lang="ts">
import { computed } from "vue";
import type {
  SchoolProgressCourse,
  SchoolProgressNode,
} from "../domain/school-progress";

const props = withDefaults(
  defineProps<{
    nodes: SchoolProgressNode[];
    courses?: SchoolProgressCourse[];
    parentId?: string | null;
  }>(),
  { parentId: null, courses: () => [] },
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
const outcomeLabel = (outcome: SchoolProgressCourse["outcome"]) =>
  ({
    PASSED: "已通过",
    FAILED: "未通过",
    IN_PROGRESS: "在读",
    NOT_TAKEN: "未修",
    UNKNOWN: "状态待确认",
  })[outcome];
</script>

<template>
  <ul
    class="school-progress-tree"
    :class="{ 'school-progress-tree--nested': parentId !== null }"
  >
    <li v-for="node in visibleNodes" :key="node.nodeId" class="school-category">
      <h3>{{ node.name }}</h3>
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
            <span>{{ course.name }} · {{ course.courseCode }}</span>
            <span class="school-course-meta">
              {{
                course.credits === null
                  ? "学分待确认"
                  : `${course.credits} 学分`
              }}
              · {{ outcomeLabel(course.outcome) }}
            </span>
          </li>
        </ul>
        <SchoolProgressTree
          v-if="hasChildren(node.nodeId)"
          :nodes="nodes"
          :courses="courses"
          :parent-id="node.nodeId"
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
