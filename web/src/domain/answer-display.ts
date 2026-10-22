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

/**
 * 表示本次答复走过受控缺口的标记。C 在未接真实 Java 或真实模型时会把它们放进
 * unknowns（见 agent-runtime 的假工具与假模型）。只要出现任意一个，这一轮就不是
 * 真实结果，页面一律不许显示「真实通过」——`AGENTS.md` 的「不把计划/fixture 写成
 * 真实能力」。只看 verdict/scope 会漏掉这种情况：核验本身可以是 VALID +
 * REAL_TIMETABLE，而候选其实来自假模型。
 */
const SIMULATION_MARKERS = new Set(["FAKE_MODEL", "FAKE_TOOL"]);

/** 答复里是否带了受控缺口标记。 */
export function hasSimulationMarker(issues: readonly Issue[]): boolean {
  return issues.some((issue) => SIMULATION_MARKERS.has(issue.code));
}

export function describeVerification(
  validation: PlanValidation,
  /** 本次答复汇总后的未知项；带受控缺口标记时强制降级。 */
  answerIssues: readonly Issue[] = [],
): VerificationView {
  if (hasSimulationMarker(answerIssues)) {
    const base = describeVerificationByVerdict(validation);
    if (!base.allowGreenPass) return base;
    return {
      tone: "simulated",
      label: "演示链路结果，不代表真实核验",
      detail:
        "本次答复带有受控缺口标记（假模型或假工具），即使核验判决通过也不能算真实通过。",
      allowGreenPass: false,
    };
  }
  return describeVerificationByVerdict(validation);
}

function describeVerificationByVerdict(
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
