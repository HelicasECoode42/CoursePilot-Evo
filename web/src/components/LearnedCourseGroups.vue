<script setup lang="ts">
import { creditsLabel, type LearnedGroup } from "../domain/school-categories";

defineProps<{ groups: LearnedGroup[] }>();
</script>

<template>
  <div class="learned-groups">
    <details v-for="group in groups" :key="group.key" class="learned-group">
      <summary>{{ group.label }} · {{ group.items.length }} 门课程</summary>
      <ul class="learned-group__items">
        <li
          v-for="(item, index) in group.items"
          :key="`${item.courseCode}:${index}`"
        >
          <span class="learned-group__name">{{ item.name }}</span>
          <span class="learned-group__meta">
            {{ item.courseCode }} · {{ creditsLabel(item.credits) }} ·
            {{ item.statusLabel }}
          </span>
        </li>
      </ul>
    </details>
  </div>
</template>

<style scoped>
.learned-group {
  margin-top: 0.5rem;
  border-top: 1px solid var(--line);
  padding-top: 0.5rem;
}
.learned-group > summary {
  color: var(--green);
  font-size: 0.9rem;
  cursor: pointer;
}
.learned-group__items {
  display: grid;
  gap: 0.35rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}
.learned-group__items li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.2rem 0.7rem;
  font-size: 0.85rem;
}
.learned-group__meta {
  color: var(--soft);
}
</style>
