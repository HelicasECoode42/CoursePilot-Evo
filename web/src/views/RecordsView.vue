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
const editingRecord = ref(false);

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
  if (saved) {
    editingRecord.value = false;
    await store.runAudit();
  }
}

function editRecord() {
  if (!store.selectedRecord) return;
  draftCourses.value = store.selectedRecord.completedCourses.map((course) => ({
    ...course,
  }));
  transcriptComplete.value = store.selectedRecord.transcriptComplete;
  editingRecord.value = true;
}

async function useRecord(recordId: string) {
  store.selectRecord(recordId);
  await store.runAudit();
}

async function goToQuestions() {
  await router.push("/plan/questions/ready");
}

function explainUnknown(code: string, fallback: string): string {
  if (code === "TRANSCRIPT_COMPLETENESS_UNKNOWN")
    return "已修课程可能还未填全，暂时无法确定剩余要求。";
  if (code === "REQUIREMENT_SOURCE_REFS_MISSING")
    return "部分培养要求缺少可核对的来源，暂时无法确定。";
  return fallback;
}
</script>

<template>
  <section class="question-card" aria-labelledby="records-title">
    <p class="eyebrow">学业资料</p>
    <h1 id="records-title" tabindex="-1">先核对你的学业资料</h1>

    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      演示模式 · 虚构内容。这里显示的记录与核对结果都不是你的真实情况。
    </p>
    <p
      v-else-if="api.mode === 'simulation'"
      class="notice notice--demo"
      role="note"
    >
      服务联调模式 · 请只输入虚构课程和学分；记录将标记为虚构数据。
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
        <h2 class="sub-label">已填写的课程</h2>
        <ul class="record-list">
          <li
            v-for="(record, index) in store.records"
            :key="record.academicRecordId"
          >
            <button
              class="record-choice"
              type="button"
              :aria-pressed="record.academicRecordId === store.selectedRecordId"
              @click="useRecord(record.academicRecordId)"
            >
              学业记录 {{ index + 1 }} ·
              {{ record.completedCourses.length }} 门课程
            </button>
            <span class="microcopy">
              · {{ record.transcriptComplete ? "已填完整" : "尚未确认填全" }}
            </span>
            <p class="microcopy">
              {{
                record.completedCourses
                  .map((course) => course.courseCode)
                  .join("、")
              }}
            </p>
          </li>
        </ul>
        <button
          class="button button--secondary"
          type="button"
          :disabled="!store.selectedRecord || store.auditStatus === 'loading'"
          @click="store.runAudit()"
        >
          {{ store.auditStatus === "loading" ? "正在核对…" : "核对培养要求" }}
        </button>
        <button
          class="button button--quiet"
          type="button"
          :disabled="!store.selectedRecord"
          @click="editRecord"
        >
          修改已填写课程
        </button>
      </div>

      <!-- 缺记录：只补缺，不让学生猜内部编号 -->
      <div
        v-if="
          store.recordsStatus === 'ready' &&
          (store.records.length === 0 || editingRecord)
        "
        class="option-section"
      >
        <h2 class="sub-label">
          {{ editingRecord ? "修改课程" : "还没有学业记录，补一份" }}
        </h2>
        <p class="microcopy">
          填写你已修或正在修读的课程，系统会据此核对培养要求。
        </p>
        <div
          v-for="(course, index) in draftCourses"
          :key="index"
          class="course-row"
        >
          <div class="course-field">
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
          </div>
          <div class="course-field">
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
          </div>
          <div class="course-field">
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
          </div>
          <button
            class="button button--secondary course-remove"
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
    <p
      v-if="store.auditStatus === 'loading'"
      class="notice"
      role="status"
      aria-live="polite"
    >
      正在核对培养要求…
    </p>
    <template v-if="store.audit && store.auditStatus !== 'loading'">
      <h2 class="sub-label">核对结果</h2>
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
        <ul class="audit-list">
          <li v-for="(item, index) in group.items" :key="item.requirementId">
            {{ item.category ?? `培养要求 ${index + 1}` }}
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
            {{ explainUnknown(issue.code, issue.message) }}
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
        返回资料确认
      </button>
    </nav>
  </section>
</template>

<style scoped>
/* 三个字段共用同一套标签间距和控件高度，删除按钮与控件底边对齐，标签才在同一水平线上。 */
.course-row {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.75rem;
  margin: 1rem 0;
}

.course-field {
  min-width: 0;
}

.course-field > .field-label {
  margin: 0 0 6px;
}

.course-field .text-control,
.course-field .select-control {
  width: 100%;
  height: 46px;
  min-height: 46px;
  padding: 0 12px;
  box-sizing: border-box;
}

.course-remove {
  min-height: 46px;
  white-space: nowrap;
}

@media (max-width: 560px) {
  .course-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
}

.record-list,
.audit-list {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.75rem;
}

.record-list > li,
.audit-list > li {
  border: 1px solid #dbe3e8;
  border-radius: 12px;
  padding: 1rem;
  background: #f8fafb;
}

.record-choice {
  border: 0;
  background: transparent;
  padding: 0;
  color: #164f55;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.record-choice[aria-pressed="true"]::after {
  content: " · 已选择";
  font-weight: 400;
}
</style>
