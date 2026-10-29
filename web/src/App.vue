<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "./api";
import { startSchoolProgressBridge } from "./school-progress-wiring";

// 学业进度的接收挂在应用级：原先只在 /records 里监听，学生停在别的页面时
// 扩展送过来没人接，bridge.js 要干等 60 秒超时才回失败。
const router = useRouter();
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
      : "真实服务模式",
);
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/" aria-label="CoursePilot 首页">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>CoursePilot</span>
      </RouterLink>
      <span
        class="mode-badge"
        :class="api.mode !== 'http' ? 'mode-badge--demo' : ''"
      >
        {{ modeLabel }}
      </span>
    </header>

    <main id="main-content" class="page-shell">
      <RouterView />
    </main>

    <footer class="page-footer">
      <span>你可以返回修改条件。课程规划不会替你登录教务系统或提交选课。</span>
    </footer>
  </div>
</template>
