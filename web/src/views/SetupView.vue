<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { describePortMismatch } from "../domain/extension-probe";
import { usePlanningStore } from "../stores/planning";

const props = defineProps<{ pagePort?: string }>();
const router = useRouter();
const store = usePlanningStore();
const preparing = ref(false);
const error = ref("");
const detectedPort = ref("");
const portMismatch = computed(() =>
  describePortMismatch(props.pagePort ?? detectedPort.value),
);
onMounted(() => {
  detectedPort.value = globalThis.location.port;
});

async function goToRecords() {
  if (preparing.value) return;
  preparing.value = true;
  error.value = "";
  try {
    if (store.sessionStatus !== "ready") await store.startSession();
    if (store.sessionStatus !== "ready") {
      error.value = store.errorMessage || "暂时连接不到服务，请稍后重试。";
      return;
    }
    await router.push("/records?import=school");
  } finally {
    preparing.value = false;
  }
}
</script>

<template>
  <section class="setup-page" aria-labelledby="setup-title">
    <RouterLink class="back-link" to="/">← 返回首页</RouterLink>
    <p class="eyebrow">学业资料 · 首次连接</p>
    <h1 id="setup-title" tabindex="-1">把已有的学业进度带进来</h1>
    <p class="lead">
      培养方案已经准备好。你只需要导入自己修过哪些课，以及学校报告的学分进度。
    </p>
    <p v-if="api.mode === 'fixture'" class="notice notice--demo">
      当前为虚构资料演示。学校导入需要连接本地服务。
    </p>
    <div v-if="store.schoolProgress" class="notice notice--success">
      <strong>本次会话已有学校学业记录</strong>
      <RouterLink to="/me">查看我的学业 →</RouterLink>
    </div>
    <ol class="setup-steps" aria-label="导入步骤">
      <li class="setup-step">
        <span class="step-index" aria-hidden="true">1</span>
        <div>
          <h2>准备浏览器扩展</h2>
          <p>第一次使用时安装，已经安装可以直接继续。</p>
          <details class="record-help">
            <summary>第一次使用：如何安装？</summary>
            <p>
              在 Chrome
              或兼容浏览器中打开扩展程序管理，开启开发者模式，选择“加载已解压的扩展程序”。
            </p>
            <p>
              选择项目中的
              <code>browser-adapter/academic-progress/</code> 文件夹，安装后刷新
              CoursePilot。
            </p>
          </details>
        </div>
      </li>
      <li class="setup-step">
        <span class="step-index" aria-hidden="true">2</span>
        <div>
          <h2>连接教务，导入并返回</h2>
          <p>
            下一页先连接扩展，再打开学校学业情况。登录后点击页面浮窗中的“导入
            CoursePilot 并返回”。
          </p>
          <p class="microcopy">
            保存成功后会回到学业资料页，显示已读取的类别和课程。
          </p>
        </div>
      </li>
    </ol>
    <div v-if="portMismatch" class="notice" role="status">
      <p>{{ portMismatch }}</p>
      <a class="button button--secondary" href="http://127.0.0.1:5173/setup"
        >在扩展支持的地址继续</a
      >
      <p class="microcopy">也可以在下一页选择已有的学业汇总文件。</p>
    </div>
    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>
    <div class="setup-actions">
      <RouterLink
        v-if="api.mode === 'fixture'"
        class="button button--primary"
        to="/me"
        >查看演示资料</RouterLink
      >
      <button
        v-else
        class="button button--primary"
        type="button"
        :disabled="preparing"
        @click="goToRecords"
      >
        {{ preparing ? "正在准备…" : "连接我的学业资料" }}
        <span aria-hidden="true">→</span>
      </button>
      <RouterLink class="button button--quiet" to="/me"
        >查看已有资料</RouterLink
      >
    </div>
    <details class="record-help setup-privacy">
      <summary>会读取哪些内容？</summary>
      <p>
        扩展读取你已登录学校页面中显示的类别学分与课程状态。不读密码、不读
        Cookie。数据交给本机 CoursePilot 保存。
      </p>
      <p>
        CoursePilot
        不替你登录。下学期班次与学业进度分开读取；缺少班次时先保存课程建议。
      </p>
    </details>
  </section>
</template>

<style scoped>
.back-link {
  display: inline-block;
  margin-bottom: 1.7rem;
  color: var(--soft);
  text-decoration: none;
  font-size: 0.85rem;
}
.setup-steps {
  list-style: none;
  margin: 1.8rem 0;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface);
}
.setup-step {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.35rem;
}
.setup-step + .setup-step {
  border-top: 1px solid var(--line);
}
.step-index {
  display: grid;
  place-items: center;
  width: 1.8rem;
  height: 1.8rem;
  flex: none;
  background: var(--wash);
  color: var(--green);
  border-radius: 50%;
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
}
.setup-step h2 {
  font-size: 1rem;
  margin: 0.15rem 0 0.4rem;
}
.setup-step p {
  margin: 0.35rem 0;
  font-size: 0.9rem;
  color: var(--soft);
}
.setup-step code {
  overflow-wrap: anywhere;
  font-size: 0.8rem;
}
.setup-step .record-help {
  border: 0;
  margin-bottom: 0;
}
.setup-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}
.setup-actions .button--primary {
  gap: 1.5rem;
}
.setup-privacy {
  margin-top: 2rem;
  border: 0;
}
@media (max-width: 540px) {
  .setup-step {
    padding: 1rem;
    gap: 0.75rem;
  }
}
</style>
