<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { usePlanningStore } from "../stores/planning";
import ReviewSummary from "./ReviewSummary.vue";
import type { AdviceChatAnswer, AdviceChatSuggestion } from "../contracts";
import {
  describeSelectedCourse,
  type CourseFact,
  type CourseFactLookup,
} from "../domain/course-names";
import { usableName } from "../domain/school-categories";

/**
 * lookupCourse 由页面提供（课程目录、学校报告）。对话卡片里的课程优先，
 * 没有时才查它；都查不到就只显示课程号，不编名字。
 */
const props = defineProps<{ lookupCourse?: CourseFactLookup }>();

const store = usePlanningStore();
const message = ref(store.adviceFailure?.text ?? "");
/** 对话记录的固定高度滚动框：只在框内上下翻，新消息出现时自动滚到底部。 */
const scrollBox = ref<HTMLElement | null>(null);

function scrollToNewest() {
  const box = scrollBox.value;
  if (!box) return;
  box.scrollTop = box.scrollHeight;
}
watch(
  () => [
    store.adviceMessages.length,
    store.advicePendingMessage,
    store.adviceFailure?.text ?? null,
  ],
  async () => {
    await nextTick();
    scrollToNewest();
  },
);
onMounted(() => {
  scrollToNewest();
});
const reviewLabels = {
  AVAILABLE: "有评价记录",
  NONE: "暂无评价记录",
  NOT_QUERIED: "尚未查询评价",
  UNKNOWN: "评价资料无法确认",
} as const;

async function send() {
  const sent = await store.sendAdviceMessage(message.value);
  if (sent) message.value = "";
}
/**
 * Enter 发送，Shift+Enter 换行。输入法组字过程中的 Enter 是选字，不能发送。
 * keyCode 229 是部分浏览器在组字时给出的值，同样忽略。
 */
function onMessageKeydown(event: {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
  keyCode: number;
  preventDefault: () => void;
}) {
  if (event.key !== "Enter" || event.shiftKey) return;
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (store.adviceBusy || !message.value.trim()) return;
  void send();
}
async function recoverAdvice() {
  const failure = store.adviceFailure;
  if (!failure) return;
  let sent: boolean;
  if (message.value.trim() && message.value.trim() !== failure.text) {
    sent = await store.sendAdviceMessage(message.value);
  } else if (failure.retryMode === "same-key") {
    sent = await store.retryAdviceMessage();
  } else {
    sent = await store.regenerateAdviceMessage();
  }
  if (sent) {
    message.value = "";
  }
}
/**
 * 按钮文字由动作类型决定，不直接用模型写的 label。模型曾把 PREFER_COURSE 写成
 * 「优先考虑…」、却返回 SELECT_COURSE，学生点的是「优先」，实际进了「必须保留」的
 * 选课。课程动作的文字因此由 kind 和课程名生成；兴趣建议仍用模型文字。
 */
function suggestionText(
  answer: AdviceChatAnswer,
  suggestion: AdviceChatSuggestion,
): string {
  if (suggestion.kind === "INTEREST") return suggestion.label;
  const name =
    answer.courses.find((course) => course.courseCode === suggestion.value)
      ?.name ?? suggestion.value;
  return suggestion.kind === "PREFER_COURSE"
    ? `优先考虑：${name}`
    : `加入待选：${name}`;
}
function adopt(answer: AdviceChatAnswer, suggestionId: string) {
  store.adoptAdviceSuggestion(answer, suggestionId);
}
function isSelected(code: string) {
  return store.draft.selectedCourseCodes.includes(code);
}
function isPreferred(code: string) {
  return store.draft.preferredCourseCodes.includes(code);
}
function courseFact(code: string): CourseFact | null {
  const answered = store.adviceMessages
    .flatMap((item) => item.answer?.courses ?? [])
    .find((item) => item.courseCode === code);
  const answeredName = usableName(answered?.name);
  if (answered && answeredName) {
    return { name: answeredName, credits: answered.credits };
  }
  return props.lookupCourse?.(code) ?? null;
}
function courseChip(code: string): string {
  return describeSelectedCourse(code, courseFact(code));
}
function capturedAtLabel(value: string) {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(timestamp);
}
</script>

<template>
  <section class="advice-chat" aria-label="课程规划对话">
    <div
      v-if="
        store.adviceMessages.length ||
        store.advicePendingMessage ||
        store.adviceFailure
      "
      ref="scrollBox"
      class="advice-chat__scroll"
      tabindex="0"
      aria-label="对话记录，可上下滚动"
    >
      <ol
        v-if="store.adviceMessages.length"
        class="advice-chat__messages"
        aria-live="polite"
      >
        <li
          v-for="(item, index) in store.adviceMessages"
          :key="`${index}-${item.role}`"
          :class="[
            `advice-chat__message--${item.role}`,
            'advice-chat__message',
          ]"
        >
          <strong>{{ item.role === "user" ? "你" : "课程助手" }}</strong>
          <p>{{ item.text }}</p>
          <div v-if="item.answer" class="advice-chat__answer">
            <p v-if="item.answer.question" class="advice-chat__question">
              <strong>需要补充：</strong>{{ item.answer.question }}
            </p>
            <details v-if="item.answer.schoolProgress" class="advice-course">
              <summary>
                学校进度（{{ item.answer.schoolProgress.source }} ·
                {{ capturedAtLabel(item.answer.schoolProgress.capturedAt) }}）
              </summary>
              <ul>
                <li
                  v-for="node in item.answer.schoolProgress.nodes"
                  :key="node.nodeId"
                >
                  {{ node.name }} · 已获 {{ node.earnedCredits ?? "未知" }} /
                  要求 {{ node.requiredCredits ?? "未知" }} 学分 · 尚缺
                  {{ node.remainingCredits ?? "未知" }} 学分
                </li>
              </ul>
            </details>
            <ul
              v-if="item.answer.unknowns.length"
              class="advice-chat__unknowns"
            >
              <li
                v-for="(unknown, issueIndex) in item.answer.unknowns"
                :key="`${unknown.code}-${issueIndex}`"
              >
                {{ unknown.message }}
              </li>
            </ul>
            <article
              v-for="course in item.answer.courses"
              :key="course.courseCode"
              class="advice-course"
            >
              <h3>{{ course.name }}</h3>
              <p class="microcopy">
                {{ course.courseCode }} ·
                {{
                  course.credits === null
                    ? "学分未知"
                    : `${course.credits} 学分`
                }}
                · {{ course.category }}
              </p>
              <p>{{ course.reason }}</p>
              <p class="microcopy">{{ reviewLabels[course.reviewStatus] }}</p>
              <ReviewSummary
                v-if="course.reviews.length"
                :course-code="course.courseCode"
                :notes="course.reviews"
                :unconfirmed="course.reviewStatus === 'UNKNOWN'"
              />
            </article>
            <div
              v-if="item.answer.suggestions.length"
              class="advice-chat__suggestions"
            >
              <button
                v-for="suggestion in item.answer.suggestions"
                :key="suggestion.suggestionId"
                class="button button--secondary"
                type="button"
                :disabled="
                  store.adoptedAdviceSuggestions.includes(
                    suggestion.suggestionId,
                  ) ||
                  (suggestion.kind === 'SELECT_COURSE' &&
                    isSelected(suggestion.value)) ||
                  (suggestion.kind === 'PREFER_COURSE' &&
                    isPreferred(suggestion.value))
                "
                @click="adopt(item.answer!, suggestion.suggestionId)"
              >
                {{
                  store.adoptedAdviceSuggestions.includes(
                    suggestion.suggestionId,
                  )
                    ? "已采用"
                    : suggestion.kind === "SELECT_COURSE" &&
                        isSelected(suggestion.value)
                      ? "已选入"
                      : suggestion.kind === "PREFER_COURSE" &&
                          isPreferred(suggestion.value)
                        ? "已优先考虑"
                        : suggestionText(item.answer!, suggestion)
                }}
              </button>
            </div>
          </div>
        </li>
      </ol>
      <div
        v-if="store.advicePendingMessage"
        class="advice-chat__pending"
        role="status"
      >
        <strong>你</strong>
        <p>{{ store.advicePendingMessage }}</p>
        <p class="microcopy">正在整理回答…</p>
      </div>
      <div
        v-if="store.adviceFailure && !store.adviceBusy"
        class="advice-chat__failure"
      >
        <p class="advice-chat__message advice-chat__message--user">
          <strong>你</strong><br />{{ store.adviceFailure.text }}
        </p>
        <p class="notice notice--error" role="alert">{{ store.adviceError }}</p>
        <button
          v-if="store.adviceFailure.retryMode !== 'none'"
          class="button button--secondary"
          type="button"
          @click="recoverAdvice"
        >
          {{
            message.trim() && message.trim() !== store.adviceFailure.text
              ? "发送修改后的问题"
              : store.adviceFailure.retryMode === "same-key"
                ? "重试本次请求"
                : "重新生成回答"
          }}
        </button>
      </div>
    </div>
    <p
      v-if="store.adviceError && !store.adviceFailure"
      class="notice notice--error"
      role="alert"
    >
      {{ store.adviceError }}
    </p>
    <p v-if="store.draft.careerText" class="advice-chat__adopted">
      已确认兴趣：{{ store.draft.careerText }}
    </p>
    <ul
      v-if="store.draft.selectedCourseCodes.length"
      class="advice-chat__selected"
      aria-label="已加入待选课程"
    >
      <li v-for="code in store.draft.selectedCourseCodes" :key="code">
        {{ courseChip(code) }} · 已选入
        <button
          type="button"
          class="linkbtn"
          :aria-label="`取消选择 ${code}`"
          @click="store.removeSelectedCourse(code)"
        >
          取消
        </button>
      </li>
    </ul>
    <ul
      v-if="store.draft.preferredCourseCodes.length"
      class="advice-chat__selected"
      aria-label="优先考虑课程"
    >
      <li v-for="code in store.draft.preferredCourseCodes" :key="code">
        {{ courseChip(code) }} · 优先考虑
        <button
          type="button"
          class="linkbtn"
          :aria-label="`取消优先考虑 ${code}`"
          @click="store.removePreferredCourse(code)"
        >
          取消
        </button>
      </li>
    </ul>
    <form class="advice-chat__form" @submit.prevent="send">
      <label for="dash-question">问一个关于方向或课程的问题</label>
      <textarea
        id="dash-question"
        v-model="message"
        class="text-control"
        rows="3"
        maxlength="1000"
        placeholder="例如：想了解人工智能方向，可以先选哪些专业选修？"
        :disabled="store.adviceBusy"
        @keydown="onMessageKeydown"
      />
      <div class="advice-chat__controls">
        <span class="microcopy">{{ message.length }}/1000</span
        ><button
          class="button button--primary"
          type="submit"
          :disabled="store.adviceBusy || !message.trim()"
        >
          {{ store.adviceBusy ? "正在发送…" : "发送问题" }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.advice-chat {
  display: grid;
  gap: 1rem;
}
/* 固定高度的滚动框：对话变长时在框内翻，不把整页拉长。 */
.advice-chat__scroll {
  height: min(60vh, 34rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  display: grid;
  align-content: start;
  gap: 0.8rem;
  padding: 0.25rem 0.25rem 0.25rem 0;
  border-radius: 12px;
}
.advice-chat__messages {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.8rem;
}
.advice-chat__message {
  max-width: 48rem;
  padding: 1rem;
  border-radius: 16px;
  background: #f0f6ee;
}
.advice-chat__message--user {
  justify-self: end;
  background: #e4f1e0;
}
.advice-chat__message p {
  white-space: pre-wrap;
}
.advice-chat__answer {
  display: grid;
  gap: 0.8rem;
}
.advice-course {
  padding: 0.8rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: white;
}
.advice-course h3 {
  margin: 0;
}
.advice-chat__suggestions,
.advice-chat__controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.advice-chat__controls {
  justify-content: space-between;
}
.advice-chat__selected {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
  list-style: none;
  padding: 0;
}
.advice-chat__selected li {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}
.advice-chat__form {
  display: grid;
  gap: 0.5rem;
}
.advice-chat__form textarea {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
}
.advice-chat__adopted {
  padding: 0.7rem;
  background: #f4f8f1;
  border-radius: 12px;
}
</style>
