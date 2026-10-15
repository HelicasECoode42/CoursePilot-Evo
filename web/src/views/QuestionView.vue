<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import type { Motive, SnapshotSummary } from "../contracts";
import { CLASS_PREFERENCE_OPTIONS } from "../domain/class-preferences";
import { MOTIVE_LABELS, MOTIVE_OPTIONS } from "../domain/goals";
import type { QuestionId } from "../domain/question-flow";
import {
  dayKeys,
  lineAction,
  SCHEDULE_DAYS,
  SCHEDULE_SECTIONS,
  sectionKeys,
  slotAction,
  slotKey,
  summarizeSlots,
  WEEKDAY_NAMES,
  type ScheduleAction,
  type ScheduleStrength,
} from "../domain/schedule-grid";
import { usePlanningStore } from "../stores/planning";

const store = usePlanningStore();
const route = useRoute();
const router = useRouter();
const heading = ref<HTMLElement | null>(null);
const validationMessage = ref("");
const selectedQuestion = computed(
  () => String(route.params.questionId) as QuestionId,
);
const stepNumber = computed(() =>
  Math.max(1, store.questions.indexOf(selectedQuestion.value) + 1),
);
const progressPercent = computed(() =>
  Math.round((stepNumber.value / store.questions.length) * 100),
);
const selectedGoals = computed(() => store.draft.motives);
const interestText = computed(() => store.draft.interestTags.join("，"));
const classPreferenceLabels = new Map(
  CLASS_PREFERENCE_OPTIONS.map((option) => [option.id, option.label]),
);

async function beginSession() {
  await store.startSession();
  if (store.sessionStatus === "ready" && store.curricula.length > 0) {
    await router.replace(`/plan/questions/${store.currentQuestion}`);
  }
}

watch(
  () => route.params.questionId,
  async () => {
    validationMessage.value = "";
    await nextTick();
    heading.value?.focus();
  },
);

function setInterestText(value: string) {
  const tags = value
    .split(/[，,、\n]/)
    .map((tag) => tag.trim().slice(0, 80))
    .filter(Boolean)
    .slice(0, 20);
  store.updateDraft("interestTags", tags);
}

function toggleMotive(motive: Motive) {
  const next = selectedGoals.value.includes(motive)
    ? selectedGoals.value.filter((item) => item !== motive)
    : [...selectedGoals.value, motive];
  store.setMotives(next);
}

function advance() {
  validationMessage.value = "";
  const question = selectedQuestion.value;
  if (question === "goals" && store.draft.motives.length === 0) {
    validationMessage.value = "请至少选择一个本学期的目标。";
    return;
  }
  if (question === "curriculum" && !store.selectedCurriculumId) {
    validationMessage.value = "请选择一个培养方案后继续。";
    return;
  }
  if (question === "teacher") store.updateDraft("teacherHandoffAccepted", true);
  if (question === "preferences")
    store.updateDraft("classPreferencesReviewed", true);
  if (question === "career") store.updateDraft("careerReviewed", true);
  if (question === "interest") store.updateDraft("interestReviewed", true);
  if (question === "schedule") {
    store.updateDraft("mustReviewed", true);
    store.updateDraft("preferReviewed", true);
  }
  if (question === "priorities") {
    if (!store.draft.prioritiesConfirmed) {
      validationMessage.value = "请先勾选确认框，确认目标先后顺序。";
      return;
    }
  }
  if (question === "ready") {
    store.preparePlanningHandoff();
    return;
  }
  const index = store.questions.indexOf(question);
  const next = store.questions[index + 1] ?? "ready";
  void router.push(`/plan/questions/${next}`);
}

function goBack() {
  void router.push(
    `/plan/questions/${store.previousQuestion(selectedQuestion.value)}`,
  );
}

const scheduleStrength = ref<ScheduleStrength>("must");
const levelText: Record<ScheduleStrength | "none", string> = {
  must: "必须避开",
  prefer: "尽量避开",
  none: "未选择",
};
const mustCells = computed(() => new Set(store.draft.mustSlots));
const preferCells = computed(() => new Set(store.draft.preferSlots));
function cellLevel(key: string): ScheduleStrength | null {
  if (mustCells.value.has(key)) return "must";
  if (preferCells.value.has(key)) return "prefer";
  return null;
}
const gridRows = computed(() =>
  SCHEDULE_SECTIONS.map((section) => ({
    section,
    cells: SCHEDULE_DAYS.map((day) => {
      const key = slotKey(day, section);
      const level = cellLevel(key);
      return {
        key,
        level,
        label: `${WEEKDAY_NAMES[day - 1]} 第${section}节 ${levelText[level ?? "none"]}`,
      };
    }),
  })),
);

function paintCells(keys: readonly string[], action: ScheduleAction): void {
  store.paintScheduleSlots(keys, scheduleStrength.value, action);
}

// Pointer gesture: the start cell decides paint or erase for the whole drag.
let dragAction: ScheduleAction | null = null;
let gestureKey: string | null = null;

// Structural type: the view's lint globals do not declare the DOM PointerEvent.
type PointerLike = { button: number; clientX: number; clientY: number };

function onCellPointerDown(key: string, event: PointerLike) {
  if (event.button !== 0) return;
  gestureKey = key;
  dragAction = slotAction(store.draft, key, scheduleStrength.value);
  paintCells([key], dragAction);
}

function onCellPointerOver(key: string) {
  if (dragAction) paintCells([key], dragAction);
}

// Touch has implicit capture on the start cell, so resolve the cell under the finger.
function onGridPointerMove(event: PointerLike) {
  if (!dragAction) return;
  const target = globalThis.document.elementFromPoint(
    event.clientX,
    event.clientY,
  );
  const key = target?.closest<HTMLElement>("[data-slot]")?.dataset.slot;
  if (key) paintCells([key], dragAction);
}

function endGesture() {
  dragAction = null;
  // A click after pointerup belongs to the gesture; clear the marker afterwards.
  setTimeout(() => {
    gestureKey = null;
  }, 0);
}

function onCellClick(key: string) {
  if (gestureKey === key) {
    gestureKey = null;
    return;
  }
  paintCells([key], slotAction(store.draft, key, scheduleStrength.value));
}

function toggleColumn(dayOfWeek: number) {
  const keys = dayKeys(dayOfWeek);
  paintCells(keys, lineAction(store.draft, keys, scheduleStrength.value));
}

function toggleRow(section: number) {
  const keys = sectionKeys(section);
  paintCells(keys, lineAction(store.draft, keys, scheduleStrength.value));
}

onMounted(() => {
  globalThis.document.addEventListener("pointerup", endGesture);
  globalThis.document.addEventListener("pointercancel", endGesture);
});
onBeforeUnmount(() => {
  globalThis.document.removeEventListener("pointerup", endGesture);
  globalThis.document.removeEventListener("pointercancel", endGesture);
});

function curriculumOptionLabel(item: SnapshotSummary, index: number): string {
  const date = new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeZone: "Asia/Shanghai",
  }).format(new Date(item.createdAt));
  const label =
    item.sourceValidation === "SYNTHETIC"
      ? `演示培养方案 ${index + 1}`
      : `培养方案 ${index + 1}`;
  return `${label} · 资料记录于 ${date}`;
}

function scheduleSummary(keys: readonly string[]): string {
  return keys.length > 0 ? summarizeSlots(keys) : "这一项留空了";
}

function prepareRequest() {
  store.preparePlanningHandoff();
}

/** 提交规划并跳到结果页。缺资料时什么都不提交，也不会跳到结果页。 */
async function submitRequest() {
  await store.submitPlan();
  if (store.planningResult || store.submitStatus === "error") {
    await router.push("/plan/result");
  }
}
</script>

<template>
  <section
    v-if="store.sessionStatus !== 'ready'"
    class="start-card"
    aria-labelledby="start-title"
  >
    <p class="eyebrow">本学期课程规划</p>
    <h1 id="start-title" ref="heading" tabindex="-1">先整理你的选课目标</h1>
    <p class="lead">
      我们会逐步提问，每个问题都可以留空跳过。你可以返回修改，尚未确认的内容不会交给后续规划。
    </p>
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      当前是演示模式：页面使用虚构的示例资料，不会连接真实服务或生成真实课程推荐。
    </p>
    <p v-else class="notice" role="note">
      当前是服务连接模式。会话只保存在本次页面内存中；刷新页面后需要重新开始。
    </p>
    <p v-if="store.errorMessage" class="notice notice--error" role="alert">
      {{ store.errorMessage }}
    </p>
    <p v-if="store.sessionStatus === 'expired'" class="microcopy" role="status">
      已填写的目标暂存在本页内存中；建立新会话后可以继续，刷新页面会清除。
    </p>
    <button
      class="button button--primary"
      :disabled="store.sessionStatus === 'loading'"
      @click="beginSession"
    >
      {{
        store.sessionStatus === "loading"
          ? "正在连接…"
          : store.sessionStatus === "error" || store.sessionStatus === "expired"
            ? "重试"
            : "开始"
      }}
    </button>
    <p class="microcopy">
      不会读取教务账号，也不会在本页展示或保存你的会话密钥。
    </p>
  </section>

  <section
    v-else-if="store.curricula.length === 0"
    class="start-card"
    aria-labelledby="missing-curriculum-title"
  >
    <p class="eyebrow">学业资料</p>
    <h1 id="missing-curriculum-title" ref="heading" tabindex="-1">
      暂时没有可用的培养方案
    </h1>
    <p class="lead">
      没有培养方案时，我们无法安全整理课程规划请求。请稍后重试，或联系课程资料维护者。
    </p>
    <p
      v-for="message in store.unknownMessages"
      :key="message"
      class="notice"
      role="status"
    >
      {{ message }}
    </p>
    <p v-if="store.errorMessage" class="notice notice--error" role="alert">
      {{ store.errorMessage }}
    </p>
    <button class="button button--secondary" @click="beginSession">
      重新检查
    </button>
  </section>

  <section v-else class="question-card" aria-labelledby="question-title">
    <div class="progress-row">
      <span>第 {{ stepNumber }} 步，共 {{ store.questions.length }} 步</span>
      <div
        class="progress-track"
        role="progressbar"
        aria-label="规划进度"
        :aria-valuenow="progressPercent"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :style="{ width: `${progressPercent}%` }"></span>
      </div>
    </div>

    <template v-if="selectedQuestion === 'curriculum'">
      <p class="eyebrow">学业资料</p>
      <h1 id="question-title" ref="heading" tabindex="-1">选择你的培养方案</h1>
      <p class="lead">课程要求会按你选择的方案核对。</p>
      <label class="field-label" for="curriculum-select">培养方案</label>
      <select
        id="curriculum-select"
        :value="store.selectedCurriculumId ?? ''"
        class="select-control"
        @change="
          store.chooseCurriculum(($event.target as HTMLSelectElement).value)
        "
      >
        <option disabled value="">请选择</option>
        <option
          v-for="(item, index) in store.curricula"
          :key="item.snapshotId"
          :value="item.snapshotId"
        >
          {{ curriculumOptionLabel(item, index) }}
          {{ item.sourceValidation === "UNVERIFIED" ? " · 来源待核验" : "" }}
        </option>
      </select>
      <p
        v-if="store.selectedCurriculum?.sourceValidation === 'UNVERIFIED'"
        class="notice notice--warning"
      >
        这份资料的来源尚未核验，页面不会把它当作已验证的真实课程事实。
      </p>
    </template>

    <template v-else-if="selectedQuestion === 'goals'">
      <p class="eyebrow">目标</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        这学期你最在意什么？
      </h1>
      <p class="lead">
        可以多选。目标表示你在意什么、先后怎样排；之后每个问题都会看到，留空即可跳过。
      </p>
      <fieldset class="choice-grid">
        <legend class="visually-hidden">选择一个或多个选课目标</legend>
        <label
          v-for="option in MOTIVE_OPTIONS"
          :key="option.id"
          class="choice-card"
        >
          <input
            type="checkbox"
            :checked="selectedGoals.includes(option.id)"
            :value="option.id"
            @change="toggleMotive(option.id)"
          />
          <span class="choice-copy">
            <strong>{{ option.label }}</strong>
            <small>{{ option.detail }}</small>
          </span>
        </label>
      </fieldset>
    </template>

    <template v-else-if="selectedQuestion === 'preferences'">
      <p class="eyebrow">上课与考核偏好</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        什么样的课程更适合你？
      </h1>
      <p class="lead">
        可以多选，也可以暂不设置。偏好只帮助表达取舍，不保证成绩或课程要求。
      </p>
      <fieldset class="choice-grid">
        <legend class="visually-hidden">选择上课与考核偏好，可多选</legend>
        <label
          v-for="option in CLASS_PREFERENCE_OPTIONS"
          :key="option.id"
          class="choice-card"
        >
          <input
            type="checkbox"
            :checked="store.draft.classPreferences.includes(option.id)"
            :value="option.id"
            @change="store.toggleClassPreference(option.id)"
          />
          <span class="choice-copy">
            <strong>{{ option.label }}</strong>
            <small>{{ option.detail }}</small>
          </span>
        </label>
      </fieldset>
      <p class="microcopy">
        具体考勤和考核方式仍需以真实课程资料核对；这里不会承诺高分或少签到。
      </p>
    </template>

    <template v-else-if="selectedQuestion === 'interest'">
      <p class="eyebrow">兴趣方向</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        你想多接触哪些内容？
      </h1>
      <p class="lead">写几个关键词即可；暂时没有想法也可以继续。</p>
      <label class="field-label" for="interest-tags">感兴趣的主题</label>
      <textarea
        id="interest-tags"
        class="text-control"
        rows="3"
        maxlength="500"
        :value="interestText"
        placeholder="例如：数据可视化、人工智能、硬件"
        @input="setInterestText(($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <p class="microcopy">多个主题可用逗号分隔。</p>
    </template>

    <template v-else-if="selectedQuestion === 'career'">
      <p class="eyebrow">职业方向</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        你对哪些职业方向感兴趣？
      </h1>
      <p class="lead">
        这是可选补充。当前没有可用的来源目录时，我们不会编造职业选项。
      </p>
      <label class="field-label" for="career-notes">你想了解的方向</label>
      <textarea
        id="career-notes"
        class="text-control"
        rows="3"
        maxlength="1000"
        :value="store.draft.careerText"
        placeholder="可以写一个方向，也可以暂时留空"
        @input="
          store.updateDraft(
            'careerText',
            ($event.target as HTMLTextAreaElement).value,
          )
        "
      ></textarea>
    </template>

    <template v-else-if="selectedQuestion === 'teacher'">
      <p class="eyebrow">教师偏好</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        你有希望保留的教师吗？
      </h1>
      <p class="lead">
        教师必须和具体课程一起选择。当前页面没有课程教师选项，后续课程详情会提供可选资料。
      </p>
      <div class="handoff-note" role="note">
        <strong>这里不会替你指定教师</strong>
        <span
          >你可以先继续。之后有真实选项时，再分别标记“必须保留”或“优先考虑”。</span
        >
      </div>
    </template>

    <template v-else-if="selectedQuestion === 'schedule'">
      <p class="eyebrow">时间安排</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        哪些时间适合你的安排？
      </h1>
      <p class="lead">
        选择一种避开强度后点格子或拖动涂选；点星期或节次可整列、整行选择。没有要求可直接继续。
      </p>
      <div class="seg" role="group" aria-label="避开强度">
        <button
          type="button"
          :aria-pressed="scheduleStrength === 'must'"
          @click="scheduleStrength = 'must'"
        >
          必须避开
        </button>
        <button
          type="button"
          :aria-pressed="scheduleStrength === 'prefer'"
          @click="scheduleStrength = 'prefer'"
        >
          尽量避开
        </button>
      </div>
      <div
        class="slotgrid"
        role="group"
        aria-label="按星期和节次选择要避开的时段"
        @pointermove="onGridPointerMove"
      >
        <span class="slot-corner" aria-hidden="true"></span>
        <button
          v-for="(name, index) in WEEKDAY_NAMES"
          :key="name"
          class="slot-head"
          type="button"
          :aria-label="`整列选择 ${name}`"
          @click="toggleColumn(index + 1)"
        >
          {{ name }}
        </button>
        <template v-for="row in gridRows" :key="row.section">
          <button
            class="slot-head"
            type="button"
            :aria-label="`整行选择 第${row.section}节`"
            @click="toggleRow(row.section)"
          >
            第{{ row.section }}节
          </button>
          <button
            v-for="cell in row.cells"
            :key="cell.key"
            class="slot"
            :class="cell.level ? `is-${cell.level}` : undefined"
            type="button"
            :data-slot="cell.key"
            :aria-pressed="cell.level !== null"
            :aria-label="cell.label"
            @pointerdown="onCellPointerDown(cell.key, $event)"
            @pointerover="onCellPointerOver(cell.key)"
            @click="onCellClick(cell.key)"
          >
            <span class="slot-mark" aria-hidden="true"></span>
          </button>
        </template>
      </div>
      <p class="microcopy">本学期上课时间待确认，暂时不能判断是否冲突。</p>
    </template>

    <template v-else-if="selectedQuestion === 'priorities'">
      <p class="eyebrow">确认优先级</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        请确认目标的先后顺序
      </h1>
      <p class="lead">
        当前顺序只是初始排列。请检查目标先后，再勾选确认；没有勾选前不会交给后续规划。
      </p>
      <ol class="priority-list" aria-label="目标优先顺序">
        <li v-for="(motive, index) in store.draft.priorityOrder" :key="motive">
          <span class="priority-number">{{ index + 1 }}</span>
          <span class="priority-name">{{ MOTIVE_LABELS[motive] }}</span>
          <button
            class="icon-button"
            type="button"
            :disabled="index === 0"
            :aria-label="`将${MOTIVE_LABELS[motive]}上移`"
            @click="store.movePriority(motive, -1)"
          >
            ↑
          </button>
          <button
            class="icon-button"
            type="button"
            :disabled="index === store.draft.priorityOrder.length - 1"
            :aria-label="`将${MOTIVE_LABELS[motive]}下移`"
            @click="store.movePriority(motive, 1)"
          >
            ↓
          </button>
        </li>
      </ol>
      <p class="handoff-note">
        <strong>必须条件和偏好会分开传递</strong>
        <span
          >当前可明确记录必须或尽量避开的时间。具体教师选择会在有真实选项后再确认。</span
        >
      </p>
      <label class="confirm-row">
        <input
          type="checkbox"
          :checked="store.draft.prioritiesConfirmed"
          @change="
            store.confirmPriorities(($event.target as HTMLInputElement).checked)
          "
        />
        <span>我已检查并确认这个优先顺序</span>
      </label>
    </template>

    <template v-else>
      <p class="eyebrow">目标整理完成</p>
      <h1 id="question-title" ref="heading" tabindex="-1">
        确认下一步所需资料
      </h1>
      <div
        v-if="store.planningHandoff"
        class="notice notice--success"
        role="status"
      >
        <strong>演示请求已整理完成。</strong>
        <span
          >其中包含虚构学业记录，只用于展示流程；本页没有调用课程推荐服务。</span
        >
      </div>
      <div v-else class="handoff-note">
        <strong>你的目标已整理好</strong>
        <span v-if="api.mode === 'fixture'">
          你正在使用虚构示例资料。本页只核对并整理演示请求，不会生成课程推荐。
        </span>
        <span v-else>
          还不能开始真实规划：目前没有读取到你的学业记录。我们不会猜测记录编号或把空记录当作完整资料。
        </span>
      </div>
      <p
        v-if="store.handoffMissing.length > 0"
        class="missing-list"
        role="status"
      >
        还缺少：{{ store.handoffMissing.join("、") }}。
      </p>
      <div
        v-for="hint in store.handoffHints"
        :key="hint"
        class="notice notice--warning"
        role="status"
      >
        <span>{{ hint }}</span>
        <RouterLink class="linkbtn" to="/plan/questions/schedule"
          >返回修改时间安排</RouterLink
        >
      </div>
      <dl class="summary-list">
        <div>
          <dt>本学期目标</dt>
          <dd>
            <ol class="summary-priorities">
              <li v-for="motive in store.draft.priorityOrder" :key="motive">
                {{ MOTIVE_LABELS[motive] }}
              </li>
            </ol>
          </dd>
        </div>
        <div>
          <dt>必须避开</dt>
          <dd>{{ scheduleSummary(store.draft.mustSlots) }}</dd>
        </div>
        <div>
          <dt>尽量避开</dt>
          <dd>{{ scheduleSummary(store.draft.preferSlots) }}</dd>
        </div>
        <div>
          <dt>上课与考核偏好</dt>
          <dd v-if="store.draft.classPreferences.length === 0">这一项留空了</dd>
          <dd v-else>
            {{
              store.draft.classPreferences
                .map((id) => classPreferenceLabels.get(id))
                .filter(Boolean)
                .join("、")
            }}
          </dd>
        </div>
        <div>
          <dt>兴趣主题</dt>
          <dd>
            {{
              store.draft.interestTags.length > 0
                ? store.draft.interestTags.join("、")
                : "这一项留空了"
            }}
          </dd>
        </div>
        <div>
          <dt>职业补充</dt>
          <dd>
            {{ store.draft.careerText.trim() || "这一项留空了" }}
          </dd>
        </div>
        <div>
          <dt>教师偏好</dt>
          <dd>尚未选择具体课程与教师</dd>
        </div>
        <div>
          <dt>培养方案</dt>
          <dd>
            <template
              v-if="store.selectedCurriculum?.sourceValidation === 'SYNTHETIC'"
            >
              虚构演示资料，不能用于真实规划
            </template>
            <template
              v-else-if="
                store.selectedCurriculum?.sourceValidation === 'UNVERIFIED'
              "
            >
              已选方案，来源待核验
            </template>
            <template v-else-if="store.selectedCurriculum">
              已选方案，来源已核验
            </template>
            <template v-else>尚未选择</template>
          </dd>
        </div>
        <div>
          <dt>学业记录</dt>
          <dd>
            {{
              api.mode === "fixture"
                ? "虚构演示记录，不含真实修读情况"
                : "尚未读取，真实规划暂不能继续"
            }}
          </dd>
        </div>
      </dl>
      <details v-if="api.mode === 'http'" class="record-help">
        <summary>为什么还缺学业记录？</summary>
        <p>
          当前接口只能在已有记录编号时读取记录，没有“查找本次会话记录”的入口；本页也没有安全的导入与核对流程。需由学业资料功能补齐课程、成绩和培养方案核对后，才能继续真实规划。
        </p>
      </details>
      <details v-else class="record-help">
        <summary>演示记录包含什么？</summary>
        <p>
          这份记录和培养方案均为虚构样例，只用于检查页面能否整理请求，不表示你的已修课程、成绩或学分缺口。
        </p>
      </details>
      <button
        class="button button--secondary"
        type="button"
        @click="prepareRequest"
      >
        检查下一步资料
      </button>
      <button
        v-if="store.planningHandoff"
        class="button button--primary"
        type="button"
        :disabled="store.submitStatus === 'submitting'"
        @click="submitRequest"
      >
        {{
          store.submitStatus === "submitting"
            ? "正在规划…"
            : "提交规划并查看结果"
        }}
      </button>
    </template>

    <p v-if="validationMessage" class="inline-error" role="alert">
      {{ validationMessage }}
    </p>
    <div
      v-for="message in store.unknownMessages"
      :key="message"
      class="notice notice--warning"
      role="status"
    >
      {{ message }}
    </div>

    <nav
      v-if="store.sessionStatus === 'ready'"
      class="question-nav"
      aria-label="问题导航"
    >
      <button
        class="button button--quiet"
        type="button"
        :disabled="selectedQuestion === store.questions[0]"
        @click="goBack"
      >
        返回
      </button>
      <button
        v-if="selectedQuestion !== 'ready'"
        class="button button--primary"
        type="button"
        @click="advance"
      >
        {{ selectedQuestion === "priorities" ? "确认顺序并继续" : "继续" }}
      </button>
      <RouterLink v-else class="button button--quiet" to="/plan/questions/goals"
        >返回修改目标</RouterLink
      >
    </nav>
  </section>
</template>
