/**
 * 方案核验的两个分项（本学期课表 / 毕业要求）在结果页的展示口径。
 *
 * 判决与分项内容全部来自 Java（PlanValidation.sections），这里只负责：
 *   - 分项标题与结论文字（通过 / 不通过 / 无法确认）；
 *   - 绿色「通过」仍只能由 answer-display 的门禁给出，分项 VALID 不单独决定颜色；
 *   - 把 violations 与 unknownChecks 排成可读列表，未知项文案复用 unknown-explain。
 *
 * 不在这里重算任何判决，也不从 violations 为空推断通过。
 */

import type {
  Issue,
  PlanSection,
  PlanValidation,
  PlanVerdict,
} from "../contracts";

export const SECTION_TITLE: Record<PlanSection["scope"], string> = {
  TIMETABLE: "本学期课表核验",
  CURRICULUM: "毕业要求核对",
};

export const UNMODELED_RULES_CODE = "UNMODELED_CURRICULUM_RULES";

export function verdictBadge(verdict: PlanVerdict): string {
  switch (verdict) {
    case "VALID":
      return "通过";
    case "INVALID":
      return "不通过";
    default:
      return "无法确认";
  }
}

export type SectionTone = "pass" | "fail" | "pending";

/**
 * 分项的颜色档位。VALID 只有在该分项依据真实班次（realCheck）时才是 pass，否则降为 pending。
 * realCheck 由调用方按门禁算出（REAL_TIMETABLE 且无受控缺口标记），这里不再推断。
 */
export function sectionTone(
  verdict: PlanVerdict,
  realCheck: boolean,
): SectionTone {
  if (verdict === "INVALID") return "fail";
  if (verdict === "VALID" && realCheck) return "pass";
  return "pending";
}

/** 未建模规则的条数：取自 Java 文案「有 N 条规则」，取不到按 1 条算。 */
export function unmodeledRuleCount(issue: Issue): number {
  const match = issue.message.match(/有 (\d+) 条规则/);
  return match ? Number(match[1]) : 1;
}

/** 学生页只显示条数，不显示原表位置和 Java 原文。规则原文目前接口未返回，故不提供展开。 */
export function unmodeledRuleLine(issue: Issue): string {
  return `有 ${unmodeledRuleCount(issue)} 条培养方案说明需人工确认`;
}

/** 分项是否存在可展示的分项数据（旧后端不返回 sections 时为 false，调用方退回旧展示）。 */
export function hasSections(validation: PlanValidation): boolean {
  return Array.isArray(validation.sections) && validation.sections.length > 0;
}
