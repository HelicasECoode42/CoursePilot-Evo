<script setup lang="ts">
/**
 * 课程搜索选择器。输入课程号或课程名都能搜（后端 query 同时匹配两者），从结果里选。
 *
 * 只允许选中当前培养方案里的课程：结果来自 listCourses，页面拿到的是课程号，不是自由文本。
 * 展示「课程号 · 课程名 · 学分 · 类别」；学分为 null 时写「学分未知」，不写 0。
 */
import { onBeforeUnmount, ref, watch } from "vue";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type { Course } from "../contracts";

const props = defineProps<{
  curriculumSnapshotId: string | null;
  inputId: string;
  label: string;
  /** 当前已选课程号，空字符串表示未选。 */
  modelValue: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  select: [course: Course];
}>();

const SEARCH_DEBOUNCE_MS = 250;

const query = ref("");
const results = ref<Course[]>([]);
const nextCursor = ref<string | null>(null);
const status = ref<"idle" | "loading" | "ready" | "error">("idle");
const errorMessage = ref("");
const picked = ref<Course | null>(null);
let seq = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let controller: AbortController | null = null;

function clearTimer() {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

function failureMessage(error: unknown): string {
  return error instanceof ApiFailure
    ? error.message
    : "搜索失败，请检查网络后重试。";
}

async function runSearch(cursor: string | null) {
  const term = query.value.trim();
  if (cursor === null) {
    // 新搜索作废所有在途请求，包括已被清空的旧搜索。
    seq += 1;
    controller?.abort();
    controller = new AbortController();
    results.value = [];
    nextCursor.value = null;
  }
  const current = seq;
  if (!props.curriculumSnapshotId || term === "") {
    status.value = "idle";
    return;
  }
  status.value = "loading";
  errorMessage.value = "";
  try {
    const page = await api.listCourses(
      props.curriculumSnapshotId,
      cursor,
      controller?.signal,
      term,
    );
    if (current !== seq) return;
    results.value =
      cursor === null ? page.items : [...results.value, ...page.items];
    nextCursor.value = page.nextCursor;
    status.value = "ready";
  } catch (error) {
    if (current !== seq) return;
    if (isAbortError(error)) return;
    errorMessage.value = failureMessage(error);
    status.value = "error";
  }
}

watch(query, () => {
  clearTimer();
  timer = setTimeout(() => {
    timer = null;
    void runSearch(null);
  }, SEARCH_DEBOUNCE_MS);
});

watch(
  () => props.curriculumSnapshotId,
  () => {
    query.value = "";
    results.value = [];
    nextCursor.value = null;
    status.value = "idle";
    picked.value = null;
  },
);

function choose(course: Course) {
  picked.value = course;
  clearTimer();
  seq += 1;
  controller?.abort();
  query.value = "";
  results.value = [];
  nextCursor.value = null;
  status.value = "idle";
  emit("select", course);
}

function creditsText(course: Course): string {
  return course.credits === null ? "学分未知" : `${course.credits} 学分`;
}

const selectedText = () => {
  if (props.modelValue === "") return "";
  if (picked.value && picked.value.courseCode === props.modelValue) {
    return `${picked.value.courseCode} · ${picked.value.name}`;
  }
  return props.modelValue;
};

onBeforeUnmount(() => {
  clearTimer();
  controller?.abort();
});
</script>

<template>
  <div class="course-picker">
    <label class="field-label" :for="inputId">{{ label }}</label>
    <p v-if="selectedText()" class="microcopy course-picker__selected">
      已选：{{ selectedText() }}
    </p>
    <input
      :id="inputId"
      v-model="query"
      class="text-control"
      type="search"
      maxlength="200"
      autocomplete="off"
      :disabled="disabled || !curriculumSnapshotId"
      placeholder="输入课程号或课程名，例如 dsa 或 数据结构"
      :aria-describedby="`${inputId}-status`"
    />
    <p
      :id="`${inputId}-status`"
      class="microcopy"
      role="status"
      aria-live="polite"
    >
      <template v-if="!curriculumSnapshotId">请先选择培养方案。</template>
      <template v-else-if="status === 'loading'">正在搜索…</template>
      <template v-else-if="status === 'idle' && query.trim() === ''">
        输入后会列出匹配的课程。
      </template>
      <template v-else-if="status === 'ready' && results.length === 0">
        没有找到匹配的课程。
      </template>
    </p>
    <p v-if="status === 'error'" class="notice notice--error" role="alert">
      {{ errorMessage }}
    </p>
    <ul v-if="results.length > 0" class="course-picker__results">
      <li
        v-for="course in results"
        :key="`${course.courseCode}:${course.name}`"
      >
        <button
          class="course-picker__choice"
          type="button"
          :aria-label="`选择 ${course.courseCode} ${course.name}`"
          @click="choose(course)"
        >
          <span class="course-picker__code">{{ course.courseCode }}</span>
          <span>{{ course.name }}</span>
          <span class="microcopy">
            · {{ creditsText(course) }} · {{ course.category }}
            <template v-if="course.suggestedTerm">
              · 建议修读：{{ course.suggestedTerm }}
            </template>
          </span>
        </button>
      </li>
    </ul>
    <button
      v-if="nextCursor && status === 'ready'"
      class="button button--secondary"
      type="button"
      @click="runSearch(nextCursor)"
    >
      加载更多结果
    </button>
  </div>
</template>

<style scoped>
.course-picker {
  min-width: 0;
}

.course-picker__selected {
  margin: 0 0 6px;
  color: #164f55;
  font-weight: 600;
}

.course-picker__results {
  list-style: none;
  padding: 0;
  margin: 8px 0;
  display: grid;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}

.course-picker__choice {
  width: 100%;
  text-align: left;
  border: 1px solid #dbe3e8;
  border-radius: 10px;
  padding: 8px 12px;
  background: #fff;
  font: inherit;
  cursor: pointer;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.course-picker__choice:hover,
.course-picker__choice:focus-visible {
  border-color: #164f55;
  background: #f1f7f8;
}

.course-picker__code {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: #164f55;
}
</style>
