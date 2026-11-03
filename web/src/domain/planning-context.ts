/**
 * 结果页顶部的学期与课表参考说明（纯函数）。
 *
 * 方案的目标学期恒为下学期；课表参考是方案所用的开课快照。快照未知时只说「学期未知」，
 * 不猜学期，也不把未核验的课表说成已核验。
 */

import type { PlanningContext } from "../contracts";

const SEASON_BY_SUFFIX: Record<string, string> = {
  "1": "秋季",
  "2": "春季",
  "3": "夏季",
};

/** 学期代号 2026-2027-1 → 「2026-2027 秋季」；格式不认识时原样返回，不猜。 */
export function termLabel(termId: string): string {
  const match = /^(\d{4})-(\d{4})-(\d)$/.exec(termId);
  if (match === null) return termId;
  const season = SEASON_BY_SUFFIX[match[3]];
  return season === undefined ? termId : `${match[1]}-${match[2]} ${season}`;
}

const VALIDATION_TEXT: Record<
  NonNullable<PlanningContext["timetableSourceValidation"]>,
  string
> = {
  VERIFIED: "已核验",
  UNVERIFIED: "未核验",
  SYNTHETIC: "演示数据",
};

/** 一行说明：为下学期规划 · 暂用 2026-2027 秋季课表参考（未核验）。 */
export function planningContextLine(
  context: PlanningContext | null | undefined,
): string {
  const head = "为下学期规划";
  if (context === null || context === undefined) return head;
  if (
    context.timetableReferenceSnapshotId === null ||
    context.timetableReferenceTermId === null
  ) {
    return `${head} · 课表参考学期未知`;
  }
  const term = termLabel(context.timetableReferenceTermId);
  const validation =
    context.timetableSourceValidation === null
      ? "来源未知"
      : VALIDATION_TEXT[context.timetableSourceValidation];
  return `${head} · 暂用 ${term}课表参考（${validation}）`;
}
