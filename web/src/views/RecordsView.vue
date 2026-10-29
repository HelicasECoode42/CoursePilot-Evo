<script setup lang="ts">
/**
 * 学业资料页（E-F1）。
 *
 * 流程按 docs/15 第 2 节：已有本会话记录就读取，缺记录才补录；
 * 再按培养方案核对，把「已满足 / 还差 / 无法确认」分开显示。
 * 这一页不计算学分，也不判断要求是否满足——那是模块 B 的职责。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import CourseSearchPicker from "../components/CourseSearchPicker.vue";
import {
  coursesSuggestedBeforeYear,
  describeYearSuggestionGap,
} from "../domain/academic-year";
import { isCurriculumUsableForMode } from "../domain/planning-request";
import type { CompletedCourse, Course, CourseOutcome } from "../contracts";
import {
  describeCompleteness,
  duplicateCourseCodes,
  explainAuditUnknown,
  groupAuditItems,
} from "../domain/academic-record";
import { usePlanningStore } from "../stores/planning";
import { schoolProgressFromBridge } from "../domain/school-progress";

const store = usePlanningStore();
const router = useRouter();
const route = useRoute();

const draftCourses = ref<CompletedCourse[]>([]);
const transcriptComplete = ref(false);
const formMessage = ref("");
const editingRecord = ref(false);
const catalogCredits = ref<Record<string, number | null>>({});
const studyYear = ref("");
const yearImportStatus = ref<"idle" | "loading" | "error">("idle");
const yearImportMessage = ref("");
const showSchoolImport = ref(route.query.import === "school");
const schoolImportMessage = ref("");
const schoolImporting = ref(false);

let schoolImportRequestId = "";

/** 学业进度 JSON 的大小上限。105 门课的导出按 2 空格缩进就有几十 KB，原来的 100KB 太紧。 */
const MAX_SCHOOL_PROGRESS_BYTES = 2_000_000;

function startSchoolImport() {
  schoolImportRequestId = crypto.randomUUID();
  schoolImportMessage.value =
    "正在连接扩展；若没有响应，请确认扩展已加载并刷新本页。";
  globalThis.window.postMessage(
    { type: "CP_START_IMPORT", requestId: schoolImportRequestId },
    globalThis.location.origin,
  );
}

async function saveSchoolProgress(data: unknown): Promise<void> {
  const snapshot = schoolProgressFromBridge(data);
  if (api.mode === "fixture")
    throw new Error("学校学业进度导入需要真实服务模式。");
  if (!store.selectedCurriculumId)
    throw new Error("请先选择培养方案，再导入学校学业进度。");
  schoolImporting.value = true;
  schoolImportMessage.value = "正在保存学校学业进度并更新学业核对。";
  try {
    const saved = await store.importSchoolProgress(snapshot);
    if (!saved)
      throw new Error(store.schoolProgressError || "保存失败，请重试。");
    schoolImportMessage.value =
      "学校学业进度已保存，课程明细已更新到学业记录。";
  } finally {
    schoolImporting.value = false;
  }
}

// eslint-disable-next-line no-undef
async function receiveSchoolProgress(event: MessageEvent) {
  if (
    event.source !== globalThis.window ||
    event.origin !== globalThis.location.origin
  )
    return;
  if (event.data?.type === "CP_IMPORT_READY" && event.data.ok) {
    schoolImportMessage.value =
      "扩展已连接。请打开学校学业情况，在浮窗点击导入并返回。";
    return;
  }
  if (
    event.data?.type !== "CP_DELIVER_PROGRESS" ||
    !schoolImportRequestId ||
    event.data.requestId !== schoolImportRequestId
  )
    return;
  try {
    await saveSchoolProgress(event.data.payload);
    showSchoolImport.value = false;
    globalThis.window.postMessage(
      {
        type: "CP_IMPORT_ACCEPTED",
        requestId: schoolImportRequestId,
        ok: true,
      },
      globalThis.location.origin,
    );
  } catch (error) {
    schoolImportMessage.value =
      error instanceof Error ? error.message : "未能保存学校学业进度，请重试。";
    globalThis.window.postMessage(
      {
        type: "CP_IMPORT_ACCEPTED",
        requestId: schoolImportRequestId,
        ok: false,
      },
      globalThis.location.origin,
    );
  }
}
onMounted(() =>
  globalThis.window.addEventListener("message", receiveSchoolProgress),
);
onUnmounted(() =>
  globalThis.window.removeEventListener("message", receiveSchoolProgress),
);

// eslint-disable-next-line no-undef
async function readSchoolProgress(event: Event) {
  // eslint-disable-next-line no-undef
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    // 原先这里是 throw new Error()，消息是空串，于是界面什么都不显示——
    // 看起来像点了没反应。另外 100KB 对 105 门课的导出来说太紧了。
    if (file.size > MAX_SCHOOL_PROGRESS_BYTES) {
      throw new Error(
        `文件 ${Math.round(file.size / 1024)} KB，超过 ${Math.round(
          MAX_SCHOOL_PROGRESS_BYTES / 1024,
        )} KB 上限，没有读取。请确认选的是扩展导出的学业进度 JSON。`,
      );
    }
    const text = await file.text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error(
        "这个文件不是合法的 JSON，没法解析。请选扩展导出的那个文件。",
      );
    }
    await saveSchoolProgress(parsed);
  } catch (error) {
    schoolImportMessage.value =
      error instanceof Error && error.message
        ? error.message
        : "文件格式不正确，请选择扩展导出的学业进度 JSON。";
  }
  input.value = "";
}

/**
 * 能用的培养方案。沿用 domain/planning-request 的同一个判断，不另写一套。
 *
 * 这一页原先根本没有选培养方案的地方：没选中时「按年级生成」点了没反应，
 * 选中的又可能是缺「建议修读学年」的那份旧合成快照，于是不管选哪个年级都是
 * 0 门。真实快照（CURRICULUM_FILE）排在前面，但不替学生自动挑。
 */
const usableCurricula = computed(() =>
  [...store.curricula]
    .filter((item) => isCurriculumUsableForMode(item, store.planningMode))
    .sort((a, b) => {
      const real = (item: typeof a) =>
        item.sourceKind === "CURRICULUM_FILE" ? 0 : 1;
      return real(a) - real(b);
    }),
);

/**
 * 换培养方案。
 *
 * store.chooseCurriculum 会 discardRecords()（核对结果绑定方案版本，换了就不适用），
 * 于是 recordsStatus 退回 idle，而补录表单的 v-if 看的就是这个状态——选完方案整块
 * 表单连同这个选择框一起消失。必须在换完之后把记录重新读回来。
 */
async function pickCurriculum(snapshotId: string) {
  if (!snapshotId) return;
  store.chooseCurriculum(snapshotId);
  yearImportMessage.value = "";
  await store.loadRecords();
}

const canLoad = computed(
  () => store.sessionStatus === "ready" && Boolean(store.sessionId),
);
const duplicateCodes = computed(() => duplicateCourseCodes(draftCourses.value));
const auditGroups = computed(() =>
  store.audit ? groupAuditItems(store.audit.requirements) : [],
);

onMounted(() => {
  if (canLoad.value) {
    void store.loadRecords();
    void store.loadSchoolProgress();
  }
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

async function addSuggestedCourses() {
  // 没选培养方案就直接 return 的话，按钮点下去毫无反应，看起来像坏了。
  if (!store.selectedCurriculumId) {
    yearImportStatus.value = "idle";
    yearImportMessage.value =
      "还没有选定培养方案，没法按年级整理。请先在规划流程里选一份培养方案，或者直接手动添加已修课程。";
    return;
  }
  if (!studyYear.value) {
    yearImportStatus.value = "idle";
    yearImportMessage.value = "请先选择目前年级。";
    return;
  }
  const year = Number(studyYear.value);
  yearImportStatus.value = "loading";
  yearImportMessage.value = "";
  try {
    const courses: Course[] = [];
    let cursor: string | null = null;
    for (let page = 0; page < 20; page += 1) {
      const response = await api.listCourses(
        store.selectedCurriculumId,
        cursor,
      );
      courses.push(...response.items);
      cursor = response.nextCursor;
      if (cursor === null) break;
    }
    if (cursor !== null) throw new Error("课程目录过长，请稍后重试。");
    const existing = new Set(draftCourses.value.map((item) => item.courseCode));
    const candidates = coursesSuggestedBeforeYear(courses, year).filter(
      (course) => !existing.has(course.courseCode),
    );
    for (const course of candidates)
      catalogCredits.value[course.courseCode] = course.credits;
    draftCourses.value = [
      ...draftCourses.value,
      ...candidates.map((course) => ({
        courseCode: course.courseCode,
        outcome: "PASSED" as const,
        earnedCredits: course.credits,
        completedTerm: null,
      })),
    ];
    yearImportStatus.value = "idle";
    // 空结果有三种完全不同的原因，笼统说一句「没有可整理的课程」看起来像功能坏了。
    yearImportMessage.value = candidates.length
      ? `已生成 ${candidates.length} 门待确认基础课程。请展开检查，把未修或未通过的课程更正后保存。`
      : explainEmptyYearImport(courses, year);
  } catch {
    yearImportStatus.value = "error";
    yearImportMessage.value = "课程目录读取失败，请重试或手动添加。";
  }
}

/**
 * 为什么一门都没生成。
 *
 * 实测：SYN_0263… 这份快照是早一轮导入发布的，105 门课的 suggestedTerm 全是
 * null，于是选哪个年级都是 0 门，页面却说「没有可按年级自动整理的基础课程」，
 * 看起来像坏了。这三种原因要分开讲，而且要告诉学生下一步能做什么。
 */
function explainEmptyYearImport(
  courses: readonly Course[],
  year: number,
): string {
  const gap = describeYearSuggestionGap(courses, year);
  switch (gap.kind) {
    case "no-suggested-term":
      return (
        "这份培养方案里没有「建议修读学年」这项数据，所以按年级整理不出课程——" +
        "换哪个年级都一样。换一份带建议学年的培养方案，或者直接手动添加已修课程。"
      );
    case "first-year":
      return "大一之前没有更早的学年，所以没有可自动整理的已修课程。直接手动添加你已经修过的课。";
    case "nothing-before-year":
      return "这份培养方案在该年级之前没有可自动识别的基础课（选修课、占位编号和多学期安排都不自动整理）。请手动添加。";
    default:
      return "没有可按年级自动整理的基础课程，请手动添加已修课程。";
  }
}

function removeCourse(index: number) {
  draftCourses.value = draftCourses.value.filter((_, at) => at !== index);
}

function updateCourse(index: number, patch: Partial<CompletedCourse>) {
  draftCourses.value = draftCourses.value.map((course, at) =>
    at === index ? { ...course, ...patch } : course,
  );
}

function selectCourse(index: number, course: Course) {
  catalogCredits.value = {
    ...catalogCredits.value,
    [course.courseCode]: course.credits,
  };
  updateCourse(index, {
    courseCode: course.courseCode,
    earnedCredits:
      draftCourses.value[index]?.outcome === "PASSED" ? course.credits : null,
  });
}

function changeOutcome(index: number, outcome: CourseOutcome) {
  const course = draftCourses.value[index];
  if (!course) return;
  updateCourse(index, {
    outcome,
    earnedCredits:
      outcome === "PASSED"
        ? (catalogCredits.value[course.courseCode] ?? null)
        : null,
  });
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

async function goToCredits() {
  await router.push("/plan/credits");
}
</script>

<template>
  <section class="question-card" aria-labelledby="records-title">
    <p class="eyebrow">学业资料</p>
    <h1 id="records-title" tabindex="-1">先核对你的学业资料</h1>

    <button
      class="button button--secondary"
      type="button"
      @click="showSchoolImport = true"
    >
      从学校教务导入
    </button>
    <dialog
      v-if="showSchoolImport"
      open
      aria-labelledby="school-import-title"
      class="school-import-dialog"
    >
      <h2 id="school-import-title">导入学校学业情况</h2>
      <p>
        打开教务学业情况页面，登录后使用 CoursePilot 扩展点击“导入 CoursePilot
        并返回”，数据会直接显示在这里。
      </p>
      <button
        type="button"
        class="button button--secondary"
        :disabled="schoolImporting"
        @click="startSchoolImport"
      >
        连接导入扩展
      </button>
      <a
        href="https://jwxt.shu.edu.cn/jwglxt/xsxy/xsxyqk_cxXsxyqkIndex.html?echarts=1&amp;gnmkdm=N105515&amp;layout=default"
        target="_blank"
        rel="noopener noreferrer"
        @click="startSchoolImport"
        >打开学校学业情况</a
      >
      <p><label for="school-progress-file">选择学分汇总文件</label></p>
      <input
        id="school-progress-file"
        type="file"
        accept="application/json,.json"
        :disabled="schoolImporting"
        @change="readSchoolProgress"
      />
      <p role="status">{{ schoolImportMessage }}</p>
      <p>导入后会保存学校类别树和课程状态，并更新当前学业记录。</p>
      <button
        class="button button--quiet"
        type="button"
        @click="showSchoolImport = false"
      >
        关闭
      </button>
    </dialog>
    <div v-if="store.schoolProgress" class="option-section">
      <h2 class="sub-label">学校学业情况</h2>
      <p class="microcopy">
        学校原始类别与培养方案核对并列显示；学校汇总不替代 Java
        核验结果。导入时间：{{
          new Date(store.schoolProgress.receipt.importedAt).toLocaleString(
            "zh-CN",
          )
        }}
      </p>
      <ul>
        <li
          v-for="item in store.schoolProgress.snapshot.nodes"
          :key="item.nodeId"
          :style="{ marginInlineStart: item.parentId ? '1.25rem' : '0' }"
        >
          {{ item.name
          }}<span v-if="item.schoolNodeId"
            >（学校类别 {{ item.schoolNodeId }}）</span
          >
          <template v-if="item.requiredCredits !== null">
            · 要求 {{ item.requiredCredits }} · 已获
            {{ item.earnedCredits ?? "未知" }} · 未获
            {{ item.remainingCredits ?? "未知" }}</template
          >
        </li>
      </ul>
      <p>
        课程行：{{
          store.schoolProgress.snapshot.courses.length
        }}；修读状态未知：{{
          store.schoolProgress.snapshot.courses.filter(
            (course) => course.outcome === "UNKNOWN",
          ).length
        }}。
      </p>
    </div>

    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      演示模式 · 虚构内容。这里显示的记录与核对结果都不是你的真实情况。
    </p>
    <p
      v-else-if="api.mode === 'simulation' && !store.schoolProgress"
      class="notice notice--demo"
      role="note"
    >
      服务联调模式 · 请只输入虚构课程和学分；记录将标记为虚构数据。
    </p>
    <p
      v-else-if="api.mode === 'simulation' && store.schoolProgress"
      class="notice notice--demo"
      role="note"
    >
      学校报告已保存为用户导入记录。当前仍是服务联调/模拟模式，不会因此提升培养方案或班次的来源核验状态；下学期时间继续按现有快照状态展示。
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
              {{ record.completedCourses.length }} 门课程 ·
              {{
                record.sourceKind === "USER_IMPORT" ? "用户导入" : "虚构数据"
              }}
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
        <div class="year-assist">
          <label class="field-label" for="records-curriculum">培养方案</label>
          <select
            id="records-curriculum"
            class="select-control"
            :value="store.selectedCurriculumId ?? ''"
            @change="
              pickCurriculum(
                ($event.target as HTMLSelectElement | null)?.value ?? '',
              )
            "
          >
            <option value="" disabled>选择培养方案</option>
            <option
              v-for="item in usableCurricula"
              :key="item.snapshotId"
              :value="item.snapshotId"
            >
              {{ item.displayName ?? item.snapshotId }} · {{ item.sourceKind }}
            </option>
          </select>
          <label class="field-label" for="study-year">目前年级</label>
          <select id="study-year" v-model="studyYear" class="select-control">
            <option value="">选择年级</option>
            <option value="1">大一</option>
            <option value="2">大二</option>
            <option value="3">大三</option>
            <option value="4">大四</option>
          </select>
          <button
            type="button"
            class="button button--secondary"
            :disabled="!studyYear || yearImportStatus === 'loading'"
            @click="addSuggestedCourses"
          >
            {{
              yearImportStatus === "loading"
                ? "正在整理…"
                : "按年级生成待确认课程"
            }}
          </button>
          <p class="microcopy">
            按培养方案的建议学年整理基础课；具体是否修过、是否通过需要你确认。选修课请另外添加。
          </p>
          <p v-if="yearImportMessage" class="year-assist__result" role="status">
            {{ yearImportMessage }}
          </p>
        </div>
        <details v-if="draftCourses.length" :open="draftCourses.length <= 8">
          <summary>
            已添加 {{ draftCourses.length }} 门课程，展开检查未修或未通过的课程
          </summary>
          <div
            v-for="(course, index) in draftCourses"
            :key="index"
            class="course-row"
          >
            <div class="course-field course-field--wide">
              <CourseSearchPicker
                :input-id="`code-${index}`"
                label="课程（输入课程号或课程名搜索）"
                :curriculum-snapshot-id="store.selectedCurriculumId"
                :model-value="course.courseCode"
                @select="(picked) => selectCourse(index, picked)"
              />
            </div>
            <div class="course-field">
              <label class="field-label" :for="`outcome-${index}`">结果</label>
              <select
                :id="`outcome-${index}`"
                class="select-control"
                :value="course.outcome"
                @change="
                  changeOutcome(
                    index,
                    ($event.target as HTMLSelectElement).value as CourseOutcome,
                  )
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
              <label class="field-label" :for="`credits-${index}`"
                >获得学分（自动填入，可修改）</label
              >
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
        </details>
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
            {{ explainAuditUnknown(issue.code, issue.message) }}
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
      <button
        v-if="store.audit"
        class="button button--primary"
        type="button"
        @click="goToCredits"
      >
        去凑学分选课
      </button>
    </nav>
  </section>
</template>

<style scoped>
/* 三个字段共用同一套标签间距和控件高度，删除按钮与控件底边对齐，标签才在同一水平线上。 */
/* 课程搜索独占一行，结果列表才有宽度；结果、学分、删除按钮排在下面一行。 */
.course-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.75rem;
  margin: 1rem 0;
}

.course-field {
  min-width: 0;
}

.course-field--wide {
  grid-column: 1 / -1;
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

  .course-remove {
    grid-column: 1 / -1;
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

<style scoped>
/*
 * 这一块原先一个样式都没有，所以「按年级生成」和下面的「添加一门已修课程」
 * 挤在一起，中间那句结果提示还按正文字号渲染，看着像标题。
 */
.year-assist {
  display: grid;
  gap: 0.6rem;
  justify-items: start;
  margin: 0 0 2rem;
  padding: 1rem 1.1rem;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--wash);
}

.year-assist .microcopy {
  margin: 0;
  line-height: 1.65;
}

.year-assist__result {
  margin: 0;
  padding: 0.7rem 0.85rem;
  border-radius: 10px;
  background: white;
  border: 1px solid var(--line);
  font-size: 0.88rem;
  line-height: 1.7;
  color: var(--ink);
}

.year-assist .select-control {
  max-width: 100%;
}
</style>

<style scoped>
.school-import-dialog {
  position: fixed;
  top: 15vh;
  width: min(32rem, 90vw);
  padding: 1.5rem;
  border: 1px solid #c6ddce;
  border-radius: 1rem;
  box-shadow: 0 1rem 4rem #173d2b40;
  z-index: 20;
}
</style>
