<script setup lang="ts">
/**
 * 换班与加课共用的班次列表（只展示与选择，不判断冲突；判断在 ResultView 的 judgeOffering）。
 *
 * - swap：可以选中「可选」班次，选中后显示替换预览，并由学生触发整份方案重新核验；
 * - add：加课接口尚未提供（替换接口只能换掉方案里已有的课），所以班次只做预览，不给「加入」按钮。
 */

interface OfferingResultRow {
  classId: string;
  kind: "clear" | "conflict" | "unknown";
  label: string;
  note: string;
  noteId: string;
  timeText: string;
  teacherText: string;
}

defineProps<{
  mode: "swap" | "add";
  courseCode: string;
  rows: OfferingResultRow[];
  /** 班次资料无法确认：空列表不能说成「没有班次」。 */
  unconfirmed: boolean;
  /** 方案中时间没读到的其他课程号，冲突判断只比较已知时间。 */
  gapCodes: string[];
  /** 当前已选的班次（换班时标出「当前」）。 */
  currentClassId: string | null;
  selectedClassId: string | null;
  previewText: string;
  replaceStatus: "idle" | "submitting" | "error";
  replaceError: string;
}>();

const emit = defineEmits<{
  select: [classId: string];
  recheck: [];
}>();
</script>

<template>
  <div class="offering-results">
    <p v-if="mode === 'add'" class="notice notice--warning" role="note">
      加课还不能加入方案：后端的替换接口只能换掉方案里已有的课程，尚未提供「新增一门课」的操作。下面的时间比较只供参考。
    </p>
    <p v-if="unconfirmed" class="notice notice--warning" role="note">
      这门课的班次无法确认：当前快照缺失或不是当前版本，不能据此说没有班次，下面的班次也都不能直接选择。
    </p>
    <p v-else-if="rows.length === 0" class="notice notice--warning" role="note">
      {{ courseCode }} 在当前快照下没有开课班次。
    </p>
    <template v-if="rows.length > 0">
      <ul class="offering-list" :aria-label="`${courseCode} 的开课班次`">
        <li
          v-for="row in rows"
          :key="row.classId"
          class="offering-row"
          :class="{ 'offering-row--current': row.classId === currentClassId }"
        >
          <div class="offering-row__body">
            <strong>
              班次 {{ row.classId }}
              <span
                v-if="row.classId === currentClassId"
                class="offering-current"
                >当前</span
              >
            </strong>
            <p>
              {{ row.timeText }}
              <template v-if="row.teacherText"
                >· {{ row.teacherText }}</template
              >
            </p>
            <p :id="row.noteId" class="offering-row__note">{{ row.note }}</p>
          </div>
          <button
            v-if="row.classId === currentClassId"
            class="offering-tag offering-tag--current"
            type="button"
            disabled
            :aria-describedby="row.noteId"
          >
            当前班次
          </button>
          <button
            v-else-if="mode === 'add'"
            class="button button--secondary"
            type="button"
            disabled
            :aria-describedby="row.noteId"
          >
            加入方案（暂未开放）
          </button>
          <button
            v-else-if="row.kind === 'clear'"
            class="button button--secondary"
            type="button"
            :aria-describedby="row.noteId"
            :aria-pressed="selectedClassId === row.classId"
            @click="emit('select', row.classId)"
          >
            {{
              selectedClassId === row.classId ? "已选这个班次" : "选这个班次"
            }}
          </button>
          <button
            v-else
            class="offering-tag"
            :class="`offering-tag--${row.kind}`"
            type="button"
            disabled
            :aria-describedby="row.noteId"
          >
            {{ row.label }}
          </button>
        </li>
      </ul>
      <p v-if="gapCodes.length" class="microcopy">
        方案中
        {{ gapCodes.join("、") }}
        的时间没能从当前快照读到，上面的冲突判断只比较已知时间。
      </p>
    </template>

    <div
      v-if="mode === 'swap' && selectedClassId !== null"
      class="notice notice--warning swap-preview"
      role="group"
      aria-label="替换预览"
    >
      <strong>{{ previewText }}</strong>
      <p class="microcopy">
        提交前必须重新核验整份方案。上面的预览不能代替核验结果。
      </p>
      <p v-if="replaceStatus === 'submitting'" role="status" aria-live="polite">
        正在重新核验整份方案，请稍候。这一步不会重复提交。
      </p>
      <p
        v-else-if="replaceStatus === 'error'"
        class="notice notice--error"
        role="alert"
      >
        {{ replaceError }} 可以再点一次重新核验。
      </p>
      <button
        class="button button--primary"
        type="button"
        :disabled="replaceStatus === 'submitting'"
        @click="emit('recheck')"
      >
        重新核验这份方案
      </button>
    </div>
  </div>
</template>

<style scoped>
.offering-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--line);
}

.offering-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}

.offering-row--current {
  background: var(--wash);
}

.offering-row strong {
  color: var(--ink);
  font-size: 14px;
  font-weight: 550;
}

.offering-row p {
  margin: 3px 0 0;
  color: var(--soft);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.offering-current {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--green);
  background: #e7f4ec;
  font-size: 11px;
  font-weight: 600;
}

.offering-tag {
  font: inherit;
  font-size: 12px;
  font-weight: 550;
  white-space: nowrap;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
}

.offering-tag:disabled {
  opacity: 1;
  cursor: not-allowed;
}

.offering-tag--conflict {
  color: #8b3c31;
  background: #fff4f2;
  border-color: #efc4bd;
}

.offering-tag--unknown {
  color: #875817;
  background: #fff8ed;
  border-color: #ecd6b0;
}

.offering-tag--current {
  color: var(--green);
  background: #e7f4ec;
}

.swap-preview {
  margin: 12px 0 0;
}

@media (max-width: 540px) {
  .offering-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
