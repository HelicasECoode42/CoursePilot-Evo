<script setup lang="ts">
import { ref } from "vue";
import { api } from "../api";
import type { CareerDirection } from "../contracts";

const emit = defineEmits<{ choose: [title: string] }>();
const props = defineProps<{ selectedText: string }>();
const MAX_TEXT_LENGTH = 1000;
function addition(title: string): string {
  return `${props.selectedText.length ? "；" : ""}想了解${title}`;
}
function alreadySelected(title: string): boolean {
  return props.selectedText.includes(`想了解${title}`);
}
function fits(title: string): boolean {
  return props.selectedText.length + addition(title).length <= MAX_TEXT_LENGTH;
}
const open = ref(false);
const status = ref<"idle" | "loading" | "ready" | "error">("idle");
const directions = ref<CareerDirection[]>([]);
const error = ref("");
async function toggle() {
  open.value = !open.value;
  if (!open.value || ["ready", "loading"].includes(status.value)) return;
  status.value = "loading";
  try {
    directions.value = await api.listCareerDirections();
    status.value = "ready";
  } catch {
    error.value = "方向资料暂时读不到，可以先自由填写，或稍后重试。";
    status.value = "error";
  }
}
</script>

<template>
  <div class="direction-suggestions">
    <button
      type="button"
      class="linkbtn"
      :aria-expanded="open"
      aria-controls="interest-directions"
      @click="toggle"
    >
      还没有明确方向？先看看方向介绍
    </button>
    <div v-if="open" id="interest-directions" class="direction-options">
      <p class="microcopy">
        先了解可能做什么，再判断有没有兴趣；资料中的来源标记会保留。
      </p>
      <p v-if="status === 'loading'" role="status">正在读取方向资料…</p>
      <p v-else-if="status === 'error'" role="status">{{ error }}</p>
      <p v-else-if="directions.length === 0" class="microcopy">
        暂时没有方向资料。你可以写下感兴趣的主题，也可以继续探索。
      </p>
      <article
        v-for="direction in directions"
        v-else
        :key="direction.directionId"
      >
        <h2>{{ direction.title }}</h2>
        <p>{{ direction.description }}</p>
        <button
          type="button"
          class="button button--secondary"
          :disabled="alreadySelected(direction.title) || !fits(direction.title)"
          @click="emit('choose', direction.title)"
        >
          {{
            alreadySelected(direction.title)
              ? "已加入想法"
              : fits(direction.title)
                ? "我想了解这个方向"
                : "内容已达长度上限"
          }}
        </button>
        <details v-if="direction.sourceRefIds.length" class="record-help">
          <summary>查看资料引用</summary>
          <ul>
            <li v-for="source in direction.sourceRefIds" :key="source">
              <code>{{ source }}</code>
            </li>
          </ul>
        </details>
      </article>
    </div>
  </div>
</template>

<style scoped>
.direction-suggestions {
  margin-top: 1.25rem;
}
.direction-options {
  margin-top: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--wash);
}
.direction-options article {
  padding-block: 1rem;
  border-bottom: 1px solid var(--line);
}
.direction-options article:last-child {
  border-bottom: 0;
}
.direction-options h2 {
  font-size: 1rem;
  margin: 0 0 0.5rem;
}
.direction-options p {
  font-size: 0.85rem;
  color: var(--soft);
}
.direction-options .button {
  min-height: 40px;
  padding: 0.6rem 0.8rem;
  background: var(--surface);
  font-size: 0.85rem;
}
.direction-options code {
  overflow-wrap: anywhere;
}
</style>
