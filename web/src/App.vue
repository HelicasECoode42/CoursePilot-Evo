<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "./api";
import { startSchoolProgressBridge } from "./school-progress-wiring";
import { usePlanningStore } from "./stores/planning";

// 学业进度的接收挂在应用级：原先只在 /records 里监听，学生停在别的页面时
// 扩展送过来没人接，bridge.js 要干等 60 秒超时才回失败。
const router = useRouter();
const route = useRoute();
const store = usePlanningStore();
const widePage = computed(() =>
  ["/", "/me", "/plan/credits"].includes(route.path),
);
const recordsTarget = computed(() =>
  store.sessionStatus === "ready" ? "/records" : "/setup",
);
let stopBridge: (() => void) | null = null;
onMounted(() => {
  stopBridge = startSchoolProgressBridge(router);
});
onUnmounted(() => {
  stopBridge?.();
  stopBridge = null;
});

const modeLabel = computed(() =>
  api.mode === "fixture"
    ? "页面演示 · 虚构内容"
    : api.mode === "simulation"
      ? "本地测试服务"
      : "本机运行",
);
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到正文</a>
    <header class="topbar">
      <RouterLink class="brand" to="/" aria-label="CoursePilot 首页">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>CoursePilot</span>
      </RouterLink>
      <nav class="main-nav" aria-label="主导航">
        <RouterLink
          to="/me"
          :aria-current="route.path === '/me' ? 'page' : undefined"
          >我的学业</RouterLink
        >
        <RouterLink
          to="/plan/questions/goals"
          :aria-current="route.path.startsWith('/plan/') ? 'page' : undefined"
          >规划下学期</RouterLink
        >
        <RouterLink
          :to="recordsTarget"
          :aria-current="
            ['/records', '/setup'].includes(route.path) ? 'page' : undefined
          "
          >学业资料</RouterLink
        >
      </nav>
      <span
        class="mode-badge"
        :class="api.mode !== 'http' ? 'mode-badge--demo' : ''"
      >
        {{ modeLabel }}
      </span>
    </header>

    <main
      id="main-content"
      class="page-shell"
      :class="{ 'page-shell--wide': widePage }"
      tabindex="-1"
    >
      <RouterView />
    </main>

    <footer class="page-footer">
      <span>CoursePilot · 下学期选课规划</span>
    </footer>
  </div>
</template>
