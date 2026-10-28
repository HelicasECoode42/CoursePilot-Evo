<script setup lang="ts">
import { computed } from "vue";
import { api } from "./api";

const modeLabel = computed(() =>
  api.mode === "fixture"
    ? "页面演示 · 虚构内容"
    : api.mode === "simulation"
      ? "服务联调 · 虚构内容"
      : "真实服务模式",
);
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink
        class="brand"
        to="/plan/questions/goals"
        aria-label="CoursePilot 首页"
      >
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
