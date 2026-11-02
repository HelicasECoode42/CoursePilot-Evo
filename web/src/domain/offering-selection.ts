/**
 * 开课快照（班次来源）的默认选择、规划模式推导与课表横幅文案。
 *
 * 纯函数，无 IO，可直接单测。规则只写在这里，store 与横幅都从这里取。
 *
 * - 可用性：真实规划只接受已核验快照，或学校公布的课程表（OFFICIAL_DOCUMENT，仍待人工核验）。
 *   SYNTHETIC 只在演示/模拟客户端可用，真实服务永远不会自动选中它。
 * - 默认选择：VERIFIED 优先，其次 OFFICIAL_DOCUMENT，再次演示数据；同级取 createdAt 最新的。
 *   用户仍可在问答页改选，本模块只决定初始值。
 * - 模式：由所选快照推导（SYNTHETIC → SIMULATION，其余 → REAL）。
 *   fixture 客户端是纯演示，固定 SIMULATION，作为全局覆盖。
 */
import type { PlanningMode, SnapshotSummary } from "../contracts";

export type OfferingClientMode = "http" | "fixture" | "simulation";

export type OfferingCandidate = Pick<
  SnapshotSummary,
  | "snapshotId"
  | "kind"
  | "state"
  | "sourceKind"
  | "sourceValidation"
  | "createdAt"
>;

function isSynthetic(item: OfferingCandidate): boolean {
  return (
    item.sourceKind === "SYNTHETIC" || item.sourceValidation === "SYNTHETIC"
  );
}

/** 真实规划可用的开课快照：已核验，或学校公布的课程表（仍待核验）。 */
function isRealOfferingUsable(item: OfferingCandidate): boolean {
  if (isSynthetic(item)) return false;
  return (
    item.sourceValidation === "VERIFIED" ||
    (item.sourceKind === "OFFICIAL_DOCUMENT" &&
      item.sourceValidation === "UNVERIFIED")
  );
}

/** 某客户端模式下能否选用这份开课快照。 */
export function isOfferingUsable(
  item: OfferingCandidate,
  clientMode: OfferingClientMode,
): boolean {
  if (clientMode === "fixture") return isSynthetic(item);
  if (clientMode === "simulation")
    return isSynthetic(item) || isRealOfferingUsable(item);
  return isRealOfferingUsable(item);
}

/** 排序等级，越小越优先。只有可用的快照才会进入排序。 */
function precedence(item: OfferingCandidate): number {
  if (isSynthetic(item)) return 2;
  if (item.sourceValidation === "VERIFIED") return 0;
  return 1;
}

function createdAtMs(item: OfferingCandidate): number {
  const ms = Date.parse(item.createdAt);
  return Number.isFinite(ms) ? ms : Number.NEGATIVE_INFINITY;
}

/**
 * 默认开课快照：VERIFIED > OFFICIAL_DOCUMENT(UNVERIFIED) > SYNTHETIC（仅模拟/演示），
 * 同级取 createdAt 最新。没有可用项时返回 null，课表留空并说明原因。
 */
export function defaultOfferingSnapshotId(
  items: readonly OfferingCandidate[],
  clientMode: OfferingClientMode,
): string | null {
  const usable = items
    .filter(
      (item) =>
        item.kind === "OFFERING" &&
        item.state === "PUBLISHED" &&
        isOfferingUsable(item, clientMode),
    )
    .sort(
      (a, b) =>
        precedence(a) - precedence(b) || createdAtMs(b) - createdAtMs(a),
    );
  return usable[0]?.snapshotId ?? null;
}

/**
 * 规划模式。fixture 固定为 SIMULATION；其余客户端按所选快照推导，
 * 没有选中快照时，真实服务为 REAL，模拟客户端为 SIMULATION。
 */
export function planningModeFor(
  clientMode: OfferingClientMode,
  offering: OfferingCandidate | null,
): PlanningMode {
  if (clientMode === "fixture") return "SIMULATION";
  if (offering === null) return clientMode === "http" ? "REAL" : "SIMULATION";
  return isSynthetic(offering) ? "SIMULATION" : "REAL";
}

export interface OfferingBanner {
  tone: "synthetic" | "official";
  text: string;
}

/**
 * 课表横幅文案，依据所选开课快照。
 * VERIFIED 的核验人与日期不在 SnapshotSummary 里（契约未携带），按规则隐藏提示。
 */
export function offeringBanner(
  offering: OfferingCandidate | null,
): OfferingBanner | null {
  if (offering === null) return null;
  if (isSynthetic(offering)) {
    return { tone: "synthetic", text: "课表为模拟数据" };
  }
  if (
    offering.sourceKind === "OFFICIAL_DOCUMENT" &&
    offering.sourceValidation === "UNVERIFIED"
  ) {
    return {
      tone: "official",
      text: "课表来自学校公布的课程表（2026-2027 秋季），尚在人工核验",
    };
  }
  return null;
}
