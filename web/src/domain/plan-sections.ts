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

export const UNMODELED_RULES_NOTE =
  "这些培养方案规则需要人工确认，系统暂不自动判断。";

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

export interface SectionLine {
  key: string;
  kind: "violation" | "unknown";
  text: string;
}

/**
 * 分项里要列出的每一行。violations 原样给 Java 文案；
 * unknownChecks 经 explain 翻译（调用方传入 unknown-explain 的包装，带课程名与快照上下文）。
 */
export function sectionLines(
  section: PlanSection,
  explain: (issue: Issue) => string,
): SectionLine[] {
  // 同一条未知项（代码与显示文字都相同）只列一次：Java 可能对同一约束给出多条相同判决。
  const seen = new Set<string>();
  const once = (code: string, text: string): boolean => {
    const fingerprint = `${code}\u0000${text}`;
    if (seen.has(fingerprint)) return false;
    seen.add(fingerprint);
    return true;
  };
  const violations: SectionLine[] = section.violations.flatMap(
    (issue, index) =>
      once(issue.code, issue.message)
        ? [
            {
              key: `v${index}:${issue.code}`,
              kind: "violation",
              text: issue.message,
            },
          ]
        : [],
  );
  const unknowns: SectionLine[] = section.unknownChecks.flatMap(
    (issue, index) => {
      // 未建模规则保留 Java 文案（含条数与原表位置），不走通用解释。
      const text =
        issue.code === UNMODELED_RULES_CODE ? issue.message : explain(issue);
      return once(issue.code, text)
        ? [{ key: `u${index}:${issue.code}`, kind: "unknown", text }]
        : [];
    },
  );
  return [...violations, ...unknowns];
}

/** 毕业要求分项因未建模规则而无法确认时的附注；其他情况返回 null。 */
export function unmodeledRulesNote(section: PlanSection): string | null {
  if (section.scope !== "CURRICULUM") return null;
  const hasUnmodeled = section.unknownChecks.some(
    (issue) => issue.code === UNMODELED_RULES_CODE,
  );
  return hasUnmodeled ? UNMODELED_RULES_NOTE : null;
}

/** 分项是否存在可展示的分项数据（旧后端不返回 sections 时为 false，调用方退回旧展示）。 */
export function hasSections(validation: PlanValidation): boolean {
  return Array.isArray(validation.sections) && validation.sections.length > 0;
}
