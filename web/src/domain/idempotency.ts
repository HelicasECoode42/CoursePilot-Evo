/**
 * 规划请求的幂等键规则。
 *
 * `docs/04`：重试同一次请求要保持相同幂等键与内容；内容变了就是一次新请求，
 * 必须换新键，否则服务端会把它当成重复并回放旧答复。
 *
 * 纯函数，无 IO，可直接单测。
 */

import type { AcademicRecordInput, PlanningRequest } from "../contracts";

/**
 * 适用这条规则的请求体。两者都由本地按固定字段顺序构造，所以摘要规则一致。
 * 规划提交和学业记录补录都要走同一条规则，不要各写一份。
 */
export type IdempotentPayload = PlanningRequest | AcademicRecordInput;

export interface IdempotencyKeyState {
  /** 上次提交的请求内容摘要。 */
  digest: string;
  /** 上次提交用的幂等键。 */
  key: string;
}

/**
 * 请求内容摘要。这两种请求体都由本地按固定字段顺序构造，
 * 因此 JSON.stringify 的键序是稳定的，不需要额外排序。
 */
export function requestDigest(request: IdempotentPayload): string {
  return JSON.stringify(request);
}

/**
 * 内容与上次一致时复用旧键（属于重试），内容变化时调用 createKey 生成新键。
 */
export function keyForRequest(
  previous: IdempotencyKeyState | null,
  request: IdempotentPayload,
  createKey: () => string,
): IdempotencyKeyState {
  const digest = requestDigest(request);
  if (previous !== null && previous.digest === digest) return previous;
  return { digest, key: createKey() };
}
