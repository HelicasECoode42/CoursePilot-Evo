<script setup lang="ts">
import { computed } from "vue";
import type { ReviewNote } from "../contracts";
import { courseSourceLabel } from "../domain/course-source";
import { reviewSourceLabel } from "../domain/review-source";
import { expandReviewItems } from "../domain/review-items";

const props = defineProps<{
  courseCode: string;
  reason: string;
  courseSourceRefIds: string[];
  reviewBasisStatus: "HAS_EVIDENCE" | "NO_RECORDS" | "NOT_QUERIED" | null;
  rationaleSource: "MODEL" | "COURSE_FACTS" | null;
  reviewNoteIds: string[];
  reviewEvidenceRefs?: Array<{ reviewNoteId: string; sourceRefId: string }>;
  reviewNotes: ReviewNote[];
  /** 原文读取状态：null 表示还没请求过。 */
  reviewStatus?: "loading" | "ready" | "error" | null;
  /** 读取失败时的原因（服务端或网络给出的文字），原样显示。 */
  reviewError?: string;
}>();
const emit = defineEmits<{ load: [] }>();

/** 展开「查看评价原文」时才请求；已经读过就不再发请求。 */
function onLoadToggle(event: globalThis.Event) {
  const target = event.target as { open?: boolean } | null;
  if (
    target?.open === true &&
    (props.reviewStatus == null || props.reviewStatus === "error")
  )
    emit("load");
}
/** 读取后仍对不上的编号：说明原文没找到，而不是继续显示「尚未加载」。 */
const missingRefs = computed(() =>
  evidenceRefs.value.filter(
    (ref) =>
      !props.reviewNotes.some((note) => note.reviewNoteId === ref.reviewNoteId),
  ),
);
const citedNotes = computed(() =>
  props.reviewNotes.filter((note) =>
    props.reviewNoteIds.includes(note.reviewNoteId),
  ),
);
const evidenceRefs = computed(() => props.reviewEvidenceRefs ?? []);
/** 已引用的评价按「一条一项」展示：拆分粘连原文，并带老师名与学期。 */
const citedItems = computed(() => expandReviewItems(citedNotes.value));
const uncachedEvidenceRefs = computed(() =>
  evidenceRefs.value.filter(
    (ref) =>
      !citedNotes.value.some((note) => note.reviewNoteId === ref.reviewNoteId),
  ),
);

const SOURCE_LABEL: Record<ReviewNote["sourceKind"], string> = {
  OFFICIAL_SYLLABUS: "官方课程大纲",
  USER_IMPORT: "用户导入资料",
  EXTERNAL_LINK: "外部链接资料",
  SYNTHETIC: "合成样例（非真实评价）",
};
</script>

<template>
  <section class="course-review-basis" :aria-label="`${courseCode} 推荐依据`">
    <p v-if="rationaleSource === 'MODEL'">模型理由：{{ reason }}</p>
    <p v-else-if="rationaleSource === 'COURSE_FACTS'">
      课程目录事实：{{ reason }}
    </p>
    <p v-else>推荐依据：{{ reason }}</p>
    <p class="microcopy">
      课程来源：
      <span v-if="courseSourceRefIds.length === 0">来源未提供</span>
      <span v-for="(ref, index) in courseSourceRefIds" :key="ref">
        <span v-if="index > 0">；</span>
        <span>{{ courseSourceLabel(ref) }}</span>
      </span>
    </p>
    <details v-if="courseSourceRefIds.length > 0" class="microcopy">
      <summary>查看课程来源引用</summary>
      <ul>
        <li v-for="ref in courseSourceRefIds" :key="ref">
          {{ courseSourceLabel(ref) }} · <code>{{ ref }}</code>
        </li>
      </ul>
    </details>
    <p v-if="reviewBasisStatus === 'NO_RECORDS'" class="microcopy">
      暂无评价依据。
    </p>
    <p v-else-if="reviewBasisStatus === 'NOT_QUERIED'" class="microcopy">
      本次规划未查询评价。
    </p>
    <p v-else-if="reviewBasisStatus === null" class="microcopy">
      评价依据状态未记录。
    </p>
    <p
      v-else-if="
        reviewBasisStatus === 'HAS_EVIDENCE' && reviewNoteIds.length === 0
      "
      class="microcopy"
    >
      该课程有评价记录，但本条理由未引用评价。
    </p>
    <div
      v-else-if="
        reviewBasisStatus === 'HAS_EVIDENCE' && citedNotes.length === 0
      "
    >
      <p v-if="evidenceRefs.length > 0" class="microcopy">
        已关联 {{ evidenceRefs.length }} 条评价记录。
      </p>
      <p v-else class="microcopy">已引用评价记录；该旧答复未附来源引用。</p>
      <details
        v-if="evidenceRefs.length > 0"
        class="microcopy"
        @toggle="onLoadToggle"
      >
        <summary>查看评价原文</summary>
        <p v-if="reviewStatus === 'loading'" role="status">正在读取评价原文…</p>
        <p
          v-else-if="reviewStatus === 'error'"
          class="notice notice--error"
          role="alert"
        >
          读取评价原文失败：{{ reviewError || "原因未知，请稍后重试。" }}
          <button class="linkbtn" type="button" @click="emit('load')">
            重新读取评价原文
          </button>
        </p>
        <p v-else-if="reviewStatus === 'ready'">
          评价库中没有找到这 {{ missingRefs.length }} 条记录的原文（编号见下）。
        </p>
        <p v-else>展开后读取评价原文。</p>
      </details>
      <details class="microcopy">
        <summary>查看评价来源引用</summary>
        <ul v-if="evidenceRefs.length > 0">
          <li v-for="ref in evidenceRefs" :key="ref.reviewNoteId">
            <span>{{ reviewSourceLabel(ref.sourceRefId) }}</span>
            <details>
              <summary>查看记录编号</summary>
              <code>{{ ref.reviewNoteId }}</code> ·
              <code>{{ ref.sourceRefId }}</code>
            </details>
          </li>
        </ul>
        <ul v-else>
          <li v-for="noteId in reviewNoteIds" :key="noteId">
            <code>{{ noteId }}</code>
          </li>
        </ul>
      </details>
    </div>
    <div
      v-if="
        reviewBasisStatus === 'HAS_EVIDENCE' &&
        uncachedEvidenceRefs.length > 0 &&
        citedNotes.length > 0
      "
      class="microcopy"
    >
      <template v-if="reviewStatus === 'ready'">
        本次读取未找到另 {{ uncachedEvidenceRefs.length }} 条已引用评价的原文。
      </template>
      <template v-else>
        另有 {{ uncachedEvidenceRefs.length }} 条已引用评价尚未显示原文。
      </template>
      <details @toggle="onLoadToggle">
        <summary>查看未显示记录的来源</summary>
        <p v-if="reviewStatus === 'loading'" role="status">正在读取评价原文…</p>
        <p
          v-else-if="reviewStatus === 'error'"
          class="notice notice--error"
          role="alert"
        >
          读取评价原文失败：{{ reviewError || "原因未知，请稍后重试。" }}
          <button class="linkbtn" type="button" @click="emit('load')">
            重新读取评价原文
          </button>
        </p>
        <ul>
          <li v-for="ref in uncachedEvidenceRefs" :key="ref.reviewNoteId">
            {{ reviewSourceLabel(ref.sourceRefId) }}
            <details>
              <summary>查看记录编号</summary>
              <code>{{ ref.reviewNoteId }}</code> ·
              <code>{{ ref.sourceRefId }}</code>
            </details>
          </li>
        </ul>
      </details>
    </div>
    <ul
      v-if="reviewBasisStatus === 'HAS_EVIDENCE' && citedNotes.length > 0"
      aria-label="评价证据"
    >
      <li v-for="item in citedItems" :key="item.key">
        <span class="microcopy">
          {{ item.teacherLabel
          }}<template v-if="item.termPrefix"> · {{ item.termPrefix }}</template>
        </span>
        <span>{{ item.text }}</span>
        <span class="microcopy">
          {{ SOURCE_LABEL[item.note.sourceKind] }} ·
          {{ reviewSourceLabel(item.note.sourceRefId) }}
          <details>
            <summary>查看记录编号</summary>
            <code>{{ item.reviewNoteId }}</code> ·
            <code>{{ item.note.sourceRefId }}</code>
          </details>
        </span>
      </li>
    </ul>
  </section>
</template>
