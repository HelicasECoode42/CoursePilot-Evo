<script setup lang="ts">
/**
 * 规划结果页（E-F4 前半）。
 *
 * 这一页只做两件事：把 store 里的 PlanningAnswer 显示出来，以及把
 * 「结论该用什么颜色」交给 domain/answer-display.ts。
 * 页面本身不判断 verdict/scope，也不从 violations 为空推断通过。
 */
import { computed } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import type { PlanningAnswer, PlanValidation } from "../contracts";
import {
  collectUnknowns,
  describeVerification,
} from "../domain/answer-display";
import { usePlanningStore } from "../stores/planning";

const store = usePlanningStore();
const router = useRouter();

const result = computed<PlanningAnswer | null>(() => store.planningResult);

const headline = computed(() => {
  if (store.submitStatus === "submitting") return "正在生成建议";
  const answer = result.value;
  if (!answer) return "还没有结果";
  switch (answer.decision) {
    case "CLARIFY":
      return "需要你先回答一个问题";
    case "RECOMMENDATIONS":
      return "给你这些课程建议";
    default:
      return "这一步没能确认";
  }
});

const unknowns = computed(() =>
  result.value === null
    ? []
    : collectUnknowns(
        result.value.unknowns,
        result.value.recommendations.map((item) => item.verification),
      ),
);

/** 展示门禁：把本次答复的未知项一并交给 describeVerification，带受控缺口标记时降级。 */
function verificationView(validation: PlanValidation) {
  return describeVerification(validation, unknowns.value);
}

async function goBackToQuestions() {
  await router.push("/plan/questions/ready");
}
</script>

<template>
  <section class="question-card" aria-labelledby="result-title">
    <p class="eyebrow">规划结果</p>
    <h1 id="result-title" tabindex="-1">{{ headline }}</h1>

    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      演示模式 · 虚构内容，不代表任何真实课程或核验结果。
    </p>

    <p
      v-if="store.submitStatus === 'submitting'"
      class="notice"
      role="status"
      aria-live="polite"
    >
      正在规划，请稍候。这一步不会重复提交。
    </p>

    <p
      v-else-if="store.submitStatus === 'error'"
      class="notice notice--error"
      role="alert"
    >
      {{ store.submitError }}
    </p>

    <p v-else-if="!result" class="notice notice--warning" role="note">
      还没有提交规划请求。回到上一页检查资料后再提交。
    </p>

    <template v-else>
      <div
        v-if="result.decision === 'CLARIFY' && result.clarification"
        class="option-section"
      >
        <h2 class="sub-label">{{ result.clarification.text }}</h2>
        <ul v-if="result.clarification.choices.length" class="summary-list">
          <li
            v-for="choice in result.clarification.choices"
            :key="choice.value"
          >
            {{ choice.label }}
          </li>
        </ul>
        <p v-else class="microcopy">可以补充文字说明。</p>
        <p class="microcopy">
          回答方式与回填字段还在与模块 C 确认（契约里没有 questionId 与 intent
          字段的对应关系），本轮先只展示问题。
        </p>
      </div>

      <div v-else-if="result.recommendations.length" class="option-section">
        <article
          v-for="recommendation in result.recommendations"
          :key="recommendation.planId"
        >
          <h2 class="sub-label">方案 {{ recommendation.planId }}</h2>
          <p
            class="notice"
            :class="{
              'notice--success': verificationView(recommendation.verification)
                .allowGreenPass,
              'notice--warning': !verificationView(recommendation.verification)
                .allowGreenPass,
            }"
            role="status"
          >
            <strong>
              {{ verificationView(recommendation.verification).label }}
            </strong>
            —— {{ verificationView(recommendation.verification).detail }}
          </p>
          <ul class="summary-list">
            <li v-for="item in recommendation.items" :key="item.courseCode">
              {{ item.courseCode }}
              <template v-if="item.teacherKey">
                · 教师 {{ item.teacherKey }}
              </template>
              <template v-if="item.classId">· 班次 {{ item.classId }}</template>
            </li>
          </ul>
          <p class="microcopy">{{ recommendation.explanation }}</p>
        </article>
      </div>

      <div v-if="unknowns.length" class="notice notice--warning" role="note">
        <p>以下内容目前无法确认，不能算通过：</p>
        <ul class="summary-list">
          <li v-for="issue in unknowns" :key="issue.code + issue.message">
            {{ issue.message }}
          </li>
        </ul>
      </div>
    </template>

    <nav class="question-nav" aria-label="结果导航">
      <button
        class="button button--secondary"
        type="button"
        @click="goBackToQuestions"
      >
        回去修改条件
      </button>
      <button
        v-if="result || store.submitStatus === 'error'"
        class="button button--primary"
        type="button"
        :disabled="store.submitStatus === 'submitting'"
        @click="store.submitPlan()"
      >
        重新提交
      </button>
    </nav>
  </section>
</template>
