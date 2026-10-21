<script setup lang="ts">
/**
 * 学业资料页（E-F1）。
 *
 * 流程按 docs/15 第 2 节：已有本会话记录就读取，缺记录才补录；
 * 再按培养方案核对，把「已满足 / 还差 / 无法确认」分开显示。
 * 这一页不计算学分，也不判断要求是否满足——那是模块 B 的职责。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import type { CompletedCourse, CourseOutcome } from "../contracts";
import {
  describeCompleteness,
  duplicateCourseCodes,
  groupAuditItems,
} from "../domain/academic-record";
import { usePlanningStore } from "../stores/planning";

const store = usePlanningStore();
const router = useRouter();

const draftCourses = ref<CompletedCourse[]>([]);
const transcriptComplete = ref(false);
const formMessage = ref("");

const canLoad = computed(
  () => store.sessionStatus === "ready" && Boolean(store.sessionId),
);
const duplicateCodes = computed(() => duplicateCourseCodes(draftCourses.value));
const auditGroups = computed(() =>
  store.audit ? groupAuditItems(store.audit.requirements) : [],
);

onMounted(() => {
  if (canLoad.value) void store.loadRecords();
});

const OUTCOMES: ReadonlyArray<{ value: CourseOutcome; label: string }> = [
  { value: "PASSED", label: "已通过" },
  { value: "FAILED", label: "未通过" },
  { value: "IN_PROGRESS", label: "在读" },
  { value: "UNKNOWN", label: "不清楚" },
];

function addCourse() {
  draftCourses.value = [
    ...draftCourses.value,
    {
      courseCode: "",
      earnedCredits: null,
      outcome: "PASSED",
      completedTerm: null,
    },
  ];
}

function removeCourse(index: number) {
  draftCourses.value = draftCourses.value.filter((_, at) => at !== index);
}

function updateCourse(index: number, patch: Partial<CompletedCourse>) {
  draftCourses.value = draftCourses.value.map((course, at) =>
    at === index ? { ...course, ...patch } : course,
  );
}

/** 学分留空就是未知，不写成 0。 */
function parseCredits(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

async function submitRecord() {
  formMessage.value = "";
  if (draftCourses.value.length === 0) {
    formMessage.value = "至少填写一门已修课程。";
    return;
  }
  if (draftCourses.value.some((course) => course.courseCode.trim() === "")) {
    formMessage.value = "每行都要填课程编号。";
    return;
  }
  if (duplicateCodes.value.length > 0) {
    formMessage.value = `课程编号重复：${duplicateCodes.value.join("、")}`;
    return;
  }
  const saved = await store.saveRecord(
    draftCourses.value,
    transcriptComplete.value,
  );
  if (saved) await store.runAudit();
}

async function useRecord(recordId: string) {
  store.selectRecord(recordId);
  await store.runAudit();
}

async function goToQuestions() {
  await router.push("/plan/questions/goals");
}
</script>

<template>
  <section class="question-card" aria-labelledby="records-title">
    <p class="eyebrow">学业资料</p>
    <h1 id="records-title" tabindex="-1">先核对你的学业资料</h1>

    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      演示模式 · 虚构内容。这里显示的记录与核对结果都不是你的真实情况。
    </p>

    <p v-if="!canLoad" class="notice notice--warning" role="note">
      还没有可用会话。请先回到引导页开始，再回来核对资料。
    </p>

    <template v-else>
      <p
        v-if="store.recordsStatus === 'loading'"
        class="notice"
        role="status"
        aria-live="polite"
      >
        正在读取本会话的学业记录…
      </p>
      <p
        v-else-if="store.recordsStatus === 'error'"
        class="notice notice--error"
        role="alert"
      >
        {{ store.recordsError }}
      </p>

      <!-- 已有记录：直接读取，不重复手填 -->
      <div v-if="store.records.length > 0" class="option-section">
        <h2 class="sub-label">本会话已有的学业记录</h2>
        <ul class="summary-list">
          <li v-for="record in store.records" :key="record.academicRecordId">
            <button
              class="linkbtn"
              type="button"
              :aria-pressed="record.academicRecordId === store.selectedRecordId"
              @click="useRecord(record.academicRecordId)"
            >
              {{ record.academicRecordId }}（第 {{ record.revision }} 版）
            </button>
            <span class="microcopy">
              · {{ record.completedCourses.length }} 门已修 ·
              {{ describeCompleteness(record) }}
            </span>
          </li>
        </ul>
        <button
          class="button button--secondary"
          type="button"
          :disabled="!store.selectedRecord"
          @click="store.runAudit()"
        >
          用选中的记录核对培养要求
        </button>
      </div>

      <!-- 缺记录：只补缺，不让学生猜内部编号 -->
      <div v-else-if="store.recordsStatus === 'ready'" class="option-section">
        <h2 class="sub-label">还没有学业记录，补一份</h2>
        <p class="microcopy">
          只填已修课程。记录编号由服务端生成，不需要你填写。
        </p>
        <div
          v-for="(course, index) in draftCourses"
          :key="index"
          class="confirm-row"
        >
          <label class="field-label" :for="`code-${index}`">课程编号</label>
          <input
            :id="`code-${index}`"
            class="text-control"
            type="text"
            maxlength="120"
            :value="course.courseCode"
            @input="
              updateCourse(index, {
                courseCode: ($event.target as HTMLInputElement).value,
              })
            "
          />
          <label class="field-label" :for="`outcome-${index}`">结果</label>
          <select
            :id="`outcome-${index}`"
            class="select-control"
            :value="course.outcome"
            @change="
              updateCourse(index, {
                outcome: ($event.target as HTMLSelectElement)
                  .value as CourseOutcome,
              })
            "
          >
            <option
              v-for="option in OUTCOMES"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
          <label class="field-label" :for="`credits-${index}`">学分</label>
          <input
            :id="`credits-${index}`"
            class="text-control"
            type="text"
            inputmode="decimal"
            maxlength="6"
            placeholder="留空表示未知"
            :value="course.earnedCredits ?? ''"
            @input="
              updateCourse(index, {
                earnedCredits: parseCredits(
                  ($event.target as HTMLInputElement).value,
                ),
              })
            "
          />
          <button
            class="button button--quiet"
            type="button"
            @click="removeCourse(index)"
          >
            删除这一行
          </button>
        </div>
        <button
          class="button button--secondary"
          type="button"
          @click="addCourse"
        >
          添加一门已修课程
        </button>
        <label class="field-label" for="transcript-complete">
          <input
            id="transcript-complete"
            type="checkbox"
            :checked="transcriptComplete"
            @change="
              transcriptComplete = ($event.target as HTMLInputElement).checked
            "
          />
          这份记录已经完整（不勾选时，无法判断的要求会显示为「无法确认」）
        </label>
        <p v-if="formMessage" class="inline-error" role="alert">
          {{ formMessage }}
        </p>
        <button
          class="button button--primary"
          type="button"
          @click="submitRecord"
        >
          保存并核对
        </button>
      </div>
    </template>

    <!-- 核对结果：三态分开，UNKNOWN 不并进已满足 -->
    <template v-if="store.audit">
      <p
        v-if="store.auditStatus === 'loading'"
        class="notice"
        role="status"
        aria-live="polite"
      >
        正在核对…
      </p>
      <p class="microcopy">
        {{ describeCompleteness(store.audit) }}
      </p>
      <div
        v-for="group in auditGroups"
        :key="group.key"
        class="option-section"
        :class="{ 'notice--warning': group.key === 'unknown' }"
      >
        <h2 class="sub-label">{{ group.label }}</h2>
        <ul class="summary-list">
          <li v-for="item in group.items" :key="item.requirementId">
            {{ item.requirementId }}
            <template v-if="item.courseCodes.length">
              · {{ item.courseCodes.join("、") }}
            </template>
            <template v-if="item.gapCredits !== null">
              · 还差 {{ item.gapCredits }} 学分
            </template>
            <template v-else>· 学分缺口未知</template>
          </li>
        </ul>
      </div>
      <div
        v-if="store.audit.unknowns.length"
        class="notice notice--warning"
        role="note"
      >
        <p>以下内容无法确认：</p>
        <ul class="summary-list">
          <li v-for="issue in store.audit.unknowns" :key="issue.code">
            {{ issue.message }}
          </li>
        </ul>
      </div>
    </template>

    <p
      v-if="store.auditStatus === 'error'"
      class="notice notice--error"
      role="alert"
    >
      {{ store.auditError }}
    </p>

    <nav class="question-nav" aria-label="资料页导航">
      <button
        class="button button--secondary"
        type="button"
        @click="goToQuestions"
      >
        回到选课目标
      </button>
    </nav>
  </section>
</template>
