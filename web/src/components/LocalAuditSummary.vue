<script setup lang="ts">
import { computed } from "vue";
import type { AuditResult } from "../contracts";
import type { CourseNameLookup } from "../domain/course-names";
import {
  courseTitle,
  summarizeAuditUnknowns,
} from "../domain/school-categories";

const props = defineProps<{
  audit: Pick<AuditResult, "unknowns" | "transcriptComplete">;
  lookupName: CourseNameLookup;
}>();

const summary = computed(() =>
  summarizeAuditUnknowns(props.audit, props.lookupName),
);
</script>

<template>
  <div class="local-audit-summary">
    <p class="local-audit-summary__headline" role="status">
      {{ summary.headline }}
    </p>
    <details
      v-for="group in summary.groups"
      :key="group.key"
      class="local-audit-summary__group"
    >
      <summary>{{ group.headline }}</summary>
      <ul v-if="group.courses.length" class="local-audit-summary__list">
        <li v-for="course in group.courses" :key="course.courseCode">
          {{ courseTitle(course.courseCode, course.name) }}
        </li>
      </ul>
      <ul v-if="group.notes.length" class="local-audit-summary__list">
        <li v-for="(note, index) in group.notes" :key="index">{{ note }}</li>
      </ul>
    </details>
  </div>
</template>

<style scoped>
.local-audit-summary__headline {
  margin: 0 0 0.6rem;
  line-height: 1.7;
  font-size: 0.9rem;
}
.local-audit-summary__group {
  margin-top: 0.4rem;
}
.local-audit-summary__group > summary {
  color: var(--green);
  font-size: 0.85rem;
  cursor: pointer;
}
.local-audit-summary__list {
  margin: 0.4rem 0 0;
  padding-left: 1.2rem;
  font-size: 0.85rem;
  line-height: 1.7;
}
</style>
