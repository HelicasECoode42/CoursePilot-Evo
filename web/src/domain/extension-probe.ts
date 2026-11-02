/**
 * 浏览器插件探测的纯规则。
 *
 * 放在 domain 里是因为两条判断都容易搞错，必须能单独测：
 *  1. 端口。background.js 只接受来自 5173 的 CP_START_IMPORT，端口不对
 *     探测必然无声失败，这时要说清原因，而不是让学生以为插件没装好。
 *  2. 回话。background.js 在五分钟内重复收到 CP_START_IMPORT 会回
 *     { ok: false }（「已有一次导入正在进行」）。这仍然证明插件在，
 *     把它当成「没装」会让学生白装一遍。
 */

/** 插件 content script 只注入这个端口的本机页面。 */
export const REQUIRED_EXTENSION_PORT = "5173";

/** 端口不对时给出可照做的说明；端口正确返回 null。 */
export function describePortMismatch(port: string): string | null {
  if (port === REQUIRED_EXTENSION_PORT) return null;
  return `插件只在 ${REQUIRED_EXTENSION_PORT} 端口上工作，当前页面端口是 ${
    port || "（空）"
  }。请在 http://127.0.0.1:${REQUIRED_EXTENSION_PORT} 上打开本页再试。`;
}

/** 是否是插件的回话。只看 type，不看 ok —— ok 为假也说明插件在。 */
export function isExtensionReply(data: unknown): boolean {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { type?: unknown }).type === "CP_IMPORT_READY"
  );
}

/** 插件在场时的说明文案。ok 为假时解释清楚，不说成失败。 */
export function describeExtensionPresent(ok: unknown): string {
  return ok === true
    ? "插件已连接。"
    : "插件已连接（它回报「已有一次导入正在进行」，这不影响后面的步骤）。";
}
