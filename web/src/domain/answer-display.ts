/**
 * 把核验判决翻译成「页面该给什么颜色、什么文案」。
 *
 * 这是 TRD §5「状态和展示门禁」的唯一实现处：页面不许在其他地方自己判断
 * verdict/scope，更不许从「violations 是空数组」推断通过。
 *
 * 纯函数，无 IO、无框架依赖，可直接单测。
 */

import type { Issue, PlanValidation } from "../contracts";

export type VerificationTone =
  | "real-pass"
  | "simulated"
  | "pending"
  | "conflict";

export interface VerificationView {
  tone: VerificationTone;
  /** 一句话结论，直接展示给学生。 */
  label: string;
  /** 为什么是这个结论。 */
  detail: string;
  /** 唯一允许渲染成「真实通过」的条件；其他一律 false。 */
  allowGreenPass: boolean;
}

const PENDING_DETAIL = "补齐资料后可以再核验，现在不能算通过。";

export function describeVerification(
  validation: PlanValidation,
): VerificationView {
  if (validation.verdict === "INVALID") {
    return {
      tone: "conflict",
      label: "存在冲突或不满足项",
      detail: joinIssues(validation.violations, "请调整条件后重新规划。"),
      allowGreenPass: false,
    };
  }

  if (validation.verdict === "UNKNOWN") {
    return {
      tone: "pending",
      label: "部分条件无法确认",
      detail: joinIssues(validation.unknownChecks, PENDING_DETAIL),
      allowGreenPass: false,
    };
  }

  // verdict === "VALID"
  switch (validation.scope) {
    case "REAL_TIMETABLE":
      return {
        tone: "real-pass",
        label: "本次快照下核验通过",
        detail: "已用真实班次核验。",
        allowGreenPass: true,
      };
    case "SIMULATION":
      return {
        tone: "simulated",
        label: "模拟核验通过",
        detail: "用的是模拟班次，不代表本学期课表。",
        allowGreenPass: false,
      };
    default:
      // COURSE_ONLY：课程层没问题，但时间没有真实班次可核，仍然不是通过。
      return {
        tone: "pending",
        label: "课程层通过，时间待确认",
        detail: "没有真实班次，时间不能算通过。",
        allowGreenPass: false,
      };
  }
}

/**
 * 汇总一条答复里所有需要学生看到的未知项：答复级 + 每条候选的核验级。
 * 按 code+message 去重，避免同一件事重复列。
 */
export function collectUnknowns(
  answerUnknowns: readonly Issue[],
  validations: readonly PlanValidation[],
): Issue[] {
  const seen = new Set<string>();
  const merged: Issue[] = [];
  for (const issue of [
    ...answerUnknowns,
    ...validations.flatMap((item) => item.unknownChecks),
  ]) {
    const fingerprint = `${issue.code}\u0000${issue.message}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    merged.push(issue);
  }
  return merged;
}

function joinIssues(issues: readonly Issue[], fallback: string): string {
  if (issues.length === 0) return fallback;
  return issues.map((issue) => issue.message).join("；");
}
