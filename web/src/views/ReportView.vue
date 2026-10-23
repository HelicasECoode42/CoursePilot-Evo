<script setup lang="ts">
// 老师运行报告：受限页面。权限由服务端强制（会话 bearer + 管理密钥）。
// 本页面不持有、不输入、不保存任何管理密钥；无权限时如实显示，不回退到假数据。
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type { RunReport } from "../contracts";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; report: RunReport }
  | { status: "forbidden" }
  | { status: "not-found" }
  | { status: "retry" };

const route = useRoute();
const heading = ref<HTMLElement | null>(null);
const state = ref<LoadState>({ status: "loading" });
const runId = computed(() => String(route.params.runId ?? ""));
let controller: AbortController | null = null;

const decisionLabels: Record<RunReport["decision"], string> = {
  BASELINE: "基线版本（未与候选比较）",
  PROMOTED: "候选已晋升",
  REJECTED: "候选被拒绝",
};

function formatAverage(value: number | null, unit: string): string {
  if (value === null) return "未记录";
  const shown = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return `${shown} ${unit}`;
}

function formatScore(value: number | null): string {
  if (value === null) return "未记录";
  return `${value}（held-out 原始评分，单位以评测定义为准）`;
}

function classify(error: unknown): LoadState {
  if (error instanceof ApiFailure) {
    if (error.status === 401 || error.status === 403) {
      return { status: "forbidden" };
    }
    if (error.status === 404) return { status: "not-found" };
  }
  return { status: "retry" };
}

async function load() {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  state.value = { status: "loading" };
  try {
    const report = await api.getRunReport(runId.value, current.signal);
    if (current.signal.aborted) return;
    state.value = { status: "ready", report };
  } catch (error) {
    if (current.signal.aborted) return;
    state.value = classify(error);
  }
  await nextTick();
  heading.value?.focus();
}

watch(runId, () => void load(), { immediate: true });

onBeforeUnmount(() => {
  controller?.abort();
});
</script>

<template>
  <section class="question-card" aria-labelledby="report-title">
    <p class="notice notice--warning" role="note">
      教师专用 · 受限报告 ·
      这不是学生页面。访问权限由服务端校验；本页面不保存、不输入、不发送管理密钥。
    </p>
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      当前是演示模式：下方内容是虚构的示例报告，不是真实运行结果。
    </p>
    <p class="eyebrow">老师运行报告</p>
    <h1 id="report-title" ref="heading" tabindex="-1">运行报告</h1>
    <p class="microcopy">运行编号：{{ runId }}</p>

    <p v-if="state.status === 'loading'" class="microcopy" role="status">
      正在读取运行报告…
    </p>

    <div v-else-if="state.status === 'forbidden'">
      <p class="notice notice--error" role="alert">
        需要管理权限。这是老师专用的受限报告，当前会话无法查看。学生页面不会显示这些内容。
      </p>
    </div>

    <div v-else-if="state.status === 'not-found'">
      <p class="notice notice--error" role="alert">
        找不到这次运行记录。这不是一份空报告，服务端没有返回这次运行的记录。
      </p>
    </div>

    <div v-else-if="state.status === 'retry'">
      <p class="notice notice--error" role="alert">
        运行报告暂时无法读取，请稍后重试。
      </p>
      <button class="button button--secondary" @click="load">重试</button>
    </div>

    <template v-else>
      <section aria-labelledby="baseline-title">
        <h2 id="baseline-title">真实基线</h2>
        <dl class="summary-list">
          <div>
            <dt>本次版本（harnessVersion）</dt>
            <dd>{{ state.report.harnessVersion }}</dd>
          </div>
          <div>
            <dt>父版本（parentVersion）</dt>
            <dd>{{ state.report.parentVersion ?? "无父版本记录" }}</dd>
          </div>
          <div>
            <dt>held-out 评分（heldOutScore）</dt>
            <dd>{{ formatScore(state.report.heldOutScore) }}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="decision-title">
        <h2 id="decision-title">候选决策</h2>
        <dl class="summary-list">
          <div>
            <dt>决策（decision）</dt>
            <dd>
              {{ decisionLabels[state.report.decision] }}
              （{{ state.report.decision }}）
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="cost-title">
        <h2 id="cost-title">质量成本</h2>
        <dl class="summary-list">
          <div>
            <dt>平均输入 token 数</dt>
            <dd>
              {{ formatAverage(state.report.averageInputTokens, "tokens") }}
            </dd>
          </div>
          <div>
            <dt>平均输出 token 数</dt>
            <dd>
              {{ formatAverage(state.report.averageOutputTokens, "tokens") }}
            </dd>
          </div>
          <div>
            <dt>平均工具调用次数</dt>
            <dd>{{ formatAverage(state.report.averageToolCalls, "次") }}</dd>
          </div>
          <div>
            <dt>平均延迟</dt>
            <dd>{{ formatAverage(state.report.averageLatencyMs, "毫秒") }}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="failure-title">
        <h2 id="failure-title">失败记录</h2>
        <p v-if="state.report.failureCategories.length === 0" class="microcopy">
          本次运行没有记录失败分类。
        </p>
        <ul v-else>
          <li
            v-for="category in state.report.failureCategories"
            :key="category"
          >
            {{ category }}
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>
