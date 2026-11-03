<script setup lang="ts">
/**
 * 「我保存的方案」：本机浏览器里的方案副本，只读回看，可删除。
 *
 * 副本不会因为会话过期消失，但它不是最新核验结果：每份都标明保存时间与「非最新核验结果」。
 * 数据读写全部经 domain/saved-plans.ts，这里只负责展示。
 */
import { computed, onMounted, ref, watch } from "vue";
import {
  SAVED_PLAN_NOTICE,
  defaultSavedPlanStorage,
  deleteSavedPlan,
  loadSavedPlans,
  type SavedPlan,
} from "../domain/saved-plans";
import { planningContextLine } from "../domain/planning-context";

const props = withDefaults(defineProps<{ revision?: number }>(), {
  revision: 0,
});

const plans = ref<SavedPlan[]>([]);
const openedId = ref<string | null>(null);
const error = ref("");

function reload() {
  plans.value = loadSavedPlans(defaultSavedPlanStorage());
  if (
    openedId.value !== null &&
    !plans.value.some((p) => p.id === openedId.value)
  ) {
    openedId.value = null;
  }
}

onMounted(reload);
watch(
  () => props.revision,
  () => reload(),
);

const opened = computed<SavedPlan | null>(
  () => plans.value.find((plan) => plan.id === openedId.value) ?? null,
);

function toggle(id: string) {
  openedId.value = openedId.value === id ? null : id;
}

function remove(id: string) {
  error.value = "";
  const before = plans.value.length;
  plans.value = deleteSavedPlan(id, defaultSavedPlanStorage());
  if (plans.value.length === before) {
    error.value = "没能删除这份副本，它仍保存在本机。可以再试一次。";
    return;
  }
  if (openedId.value === id) openedId.value = null;
}

/** 保存时间按本地时间显示；解析失败时原样显示，不猜。 */
function savedAtText(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <section class="saved-plans" aria-labelledby="saved-plans-title">
    <h2 id="saved-plans-title" class="sub-label">我保存的方案</h2>
    <p class="microcopy">
      只保存在这台电脑的浏览器里；清除站点数据、换设备后就看不到了。
    </p>

    <p v-if="plans.length === 0" class="microcopy" role="status">
      还没有保存的方案。在结果页点「保存方案」→「保存到本机浏览器」即可保存。
    </p>

    <ul v-else class="saved-list" aria-label="本机保存的方案">
      <li v-for="plan in plans" :key="plan.id" class="saved-list__item">
        <button
          class="button button--secondary saved-list__open"
          type="button"
          :aria-expanded="openedId === plan.id ? 'true' : 'false'"
          @click="toggle(plan.id)"
        >
          方案 {{ plan.planNumber }}{{ plan.edited ? "（调整后）" : "" }} ·
          保存于 {{ savedAtText(plan.savedAt) }}
        </button>
      </li>
    </ul>

    <article
      v-if="opened"
      class="saved-view"
      aria-label="保存的方案副本（只读）"
    >
      <p class="notice notice--warning" role="note">
        <strong>{{ SAVED_PLAN_NOTICE }}</strong>
        <span class="microcopy">
          这是保存当时的内容。判决与课表可能已经过时，要以最新核验为准。
        </span>
      </p>
      <p class="microcopy">保存时的判决：{{ opened.verdict.label }}</p>
      <p v-if="opened.planningContext" class="microcopy">
        {{ planningContextLine(opened.planningContext) }}
      </p>
      <ul class="saved-courses" aria-label="副本中的课程">
        <li
          v-for="(course, index) in opened.courses"
          :key="`${course.courseCode}-${index}`"
        >
          <strong>{{ course.name ?? course.courseCode }}</strong>
          <span class="saved-courses__meta">
            {{ course.courseCode
            }}<template v-if="course.credits !== null">
              · {{ course.credits }} 学分</template
            ><template v-if="course.tag"> · {{ course.tag }}</template>
          </span>
          <span class="saved-courses__meta">
            {{ course.teacherText || "教师未填写" }} · {{ course.timeText }}
            <template v-if="course.classId">
              · 班次 {{ course.classId }}</template
            >
          </span>
        </li>
      </ul>
      <button
        class="button button--quiet saved-view__delete"
        type="button"
        @click="remove(opened.id)"
      >
        删除这份副本
      </button>
    </article>

    <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.saved-plans {
  margin-top: 24px;
}

.saved-list {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.saved-list__open {
  width: 100%;
  text-align: left;
}

.saved-view {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
}

.saved-view .notice {
  margin: 0 0 8px;
}

.saved-courses {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.saved-courses li {
  display: grid;
  gap: 2px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
  color: var(--ink);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.saved-courses__meta {
  color: var(--soft);
  font-size: 12px;
}

.saved-view__delete {
  margin-top: 10px;
  color: #8b3c31;
}
</style>
