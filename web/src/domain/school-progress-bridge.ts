/**
 * 扩展 → 网页的学业进度接收逻辑（纯逻辑，不碰 window）。
 *
 * 为什么要把它从 RecordsView 里搬出来：原先这个监听器只活在 /records 这一个
 * 路由上。学生从别的页面（首页、配置页、控制台）按扩展里的「导入 CoursePilot
 * 并返回」，扩展确实把数据送过来了，但页面没有监听者，于是 bridge.js 要干等
 * 60 秒超时才回 ok:false——这就是「导入并返回，回不去」的观感。
 *
 * 搬到应用级之后，不管学生停在哪一页，收到就存。
 *
 * 另外两条边界由调用方保证，这里不重复：
 *  - 只处理同源、同窗口的消息（event.source / event.origin 校验）
 *  - 回执必须带上原来的 requestId，否则 bridge.js 认不出是哪一次
 */

export type BridgeOutcome =
  | { kind: "ignored" }
  | { kind: "ready"; message: string }
  | { kind: "saved"; message: string }
  | { kind: "failed"; message: string };

export type BridgeDeps = {
  /** 把快照存进服务端。抛错即视为失败，错误文案直接给学生看。 */
  save: (payload: unknown) => Promise<void>;
  /** 向同源窗口回发消息（CP_IMPORT_ACCEPTED）。 */
  post: (message: unknown) => void;
  /** 生成本次导入的请求号。 */
  newRequestId: () => string;
};

export type SchoolProgressBridge = {
  /** 登记接收页面，并返回本次的 requestId。 */
  requestImport: () => string;
  /** 处理一条已通过同源校验的消息。 */
  handle: (data: unknown) => Promise<BridgeOutcome>;
  /** 当前等待中的 requestId，测试和排查用。 */
  pendingRequestId: () => string;
};

function messageType(data: unknown): string | null {
  if (typeof data !== "object" || data === null) return null;
  const type = (data as { type?: unknown }).type;
  return typeof type === "string" ? type : null;
}

export function createSchoolProgressBridge(
  deps: BridgeDeps,
): SchoolProgressBridge {
  let pending = "";
  let saving: Promise<BridgeOutcome> | null = null;

  return {
    requestImport() {
      // Reconnecting from the same page must retain the request registered in the extension.
      if (!pending) pending = deps.newRequestId();
      deps.post({ type: "CP_START_IMPORT", requestId: pending });
      return pending;
    },

    pendingRequestId() {
      return pending;
    },

    async handle(data: unknown): Promise<BridgeOutcome> {
      const type = messageType(data);
      if (type === "CP_IMPORT_READY") {
        const ok = (data as { ok?: unknown }).ok === true;
        if (!ok) {
          return {
            kind: "failed",
            message:
              "另一个 CoursePilot 页面有待完成的导入，请返回原页面，或完成后再连接。",
          };
        }
        return {
          kind: "ready",
          message: "扩展已连接。请打开学校学业情况，在浮窗点击导入并返回。",
        };
      }
      if (type !== "CP_DELIVER_PROGRESS") return { kind: "ignored" };

      const requestId = (data as { requestId?: unknown }).requestId;
      if (
        pending === "" ||
        typeof requestId !== "string" ||
        requestId !== pending
      ) {
        // 不是本次登记的那一笔，不处理也不回执，免得抢别的标签页的回执。
        return { kind: "ignored" };
      }

      if (saving) return saving;
      saving = (async (): Promise<BridgeOutcome> => {
        try {
          await deps.save((data as { payload?: unknown }).payload);
          deps.post({ type: "CP_IMPORT_ACCEPTED", requestId, ok: true });
          pending = "";
          return {
            kind: "saved",
            message: "学校学业进度已保存，课程明细已更新到学业记录。",
          };
        } catch (error) {
          deps.post({ type: "CP_IMPORT_ACCEPTED", requestId, ok: false });
          return {
            kind: "failed",
            message:
              error instanceof Error && error.message
                ? error.message
                : "未能保存学校学业进度，请重试。",
          };
        }
      })();
      try {
        return await saving;
      } finally {
        saving = null;
      }
    },
  };
}
