<script setup lang="ts">
import type { ReviewNote } from "../contracts";
import { reviewSourceLabel } from "../domain/review-source";
import { expandReviewItems } from "../domain/review-items";
import { summarizeReviewsByDimension } from "../domain/review-summary";

const props = withDefaults(
  defineProps<{
    courseCode: string;
    notes: ReviewNote[];
    unconfirmed?: boolean;
    /** 标题：课程级、按老师、未绑定老师等区块分别说明依据。 */
    title?: string;
  }>(),
  { title: "课程评价维度汇总" },
);

const LABELS: Record<string, string> = {
  GRADING: "给分方式",
  ATTENDANCE: "签到",
  WORKLOAD: "工作量",
  EXAM: "考试",
  GROUP_WORK: "小组任务",
  PRESENTATION: "汇报展示",
  TEACHING: "授课",
  OVERALL: "整体印象",
};
const SOURCE_LABEL: Record<ReviewNote["sourceKind"], string> = {
  OFFICIAL_SYLLABUS: "官方课程大纲",
  USER_IMPORT: "用户导入资料",
  EXTERNAL_LINK: "外部链接资料",
  SYNTHETIC: "合成样例（非真实评价）",
};
const MATCH_LABEL: Record<ReviewNote["matchStatus"], string> = {
  COURSE_TEACHER_MATCHED: "课程与教师均已对应",
  COURSE_ONLY: "只能确认课程",
  UNVERIFIED: "来源未核验",
};

function publishedYear(publishedAt: string | null): string {
  if (!publishedAt) return "年份未知";
  const timestamp = Date.parse(publishedAt);
  return Number.isNaN(timestamp)
    ? "年份未知"
    : `发布于 ${new Date(timestamp).getUTCFullYear()} 年`;
}
</script>

<template>
  <section
    v-if="summarizeReviewsByDimension(notes, courseCode).length > 0"
    aria-label="课程评价维度汇总"
  >
    <h2>{{ props.title }}</h2>
    <p class="microcopy">
      按评价记录统计；同一记录可能涉及多个维度，数量不等于评价人数。
    </p>
    <p v-if="unconfirmed" class="microcopy">
      评价资料未完整确认，以下统计可能不完整。
    </p>
    <details
      v-for="group in summarizeReviewsByDimension(notes, courseCode)"
      :key="group.dimension"
      class="review-summary__group"
    >
      <summary>
        {{ LABELS[group.dimension] }} · {{ group.count }} 条
        <template v-if="group.syntheticCount > 0">
          （其中 {{ group.syntheticCount }} 条为虚构样例）
        </template>
      </summary>
      <ul>
        <li
          v-for="item in expandReviewItems(group.notes)"
          :key="`${group.dimension}-${item.key}`"
          class="review-summary__item"
        >
          <p class="microcopy">
            {{ item.teacherLabel
            }}<template v-if="item.termPrefix">
              · {{ item.termPrefix }}</template
            >
          </p>
          <p>{{ item.text }}</p>
          <p class="microcopy">
            {{ SOURCE_LABEL[item.note.sourceKind] }} ·
            {{ publishedYear(item.note.publishedAt) }} ·
            {{ MATCH_LABEL[item.note.matchStatus] }}
          </p>
          <details class="review-summary__source">
            <summary>来源资料</summary>
            <p class="microcopy">
              {{ reviewSourceLabel(item.note.sourceRefId) }}
            </p>
            <code :title="item.note.sourceRefId">{{
              item.note.sourceRefId
            }}</code>
          </details>
        </li>
      </ul>
    </details>
  </section>
</template>

<style scoped>
.review-summary__group {
  margin-block: 10px;
}

.review-summary__group ul {
  margin-block: 6px;
}

.review-summary__source {
  margin-block: 4px;
}

.review-summary__item {
  margin-block: 8px;
}
</style>
