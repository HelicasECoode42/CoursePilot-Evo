/**
 * 应用级的学业进度接收：挂在 App.vue 上，不依赖当前路由。
 *
 * 原先监听器只在 /records 里 onMounted，学生停在别的页面时扩展送过来没人接，
 * bridge.js 要干等 60 秒超时。挂在这里之后，停在哪一页都能收到并保存；
 * 保存成功再把人带到 /records 看结果。
 */
import { ref } from "vue";
import type { Router } from "vue-router";
import { api } from "./api";
import {
  createSchoolProgressBridge,
  type SchoolProgressBridge,
} from "./domain/school-progress-bridge";
import { schoolProgressFromBridge } from "./domain/school-progress";
import { usePlanningStore } from "./stores/planning";

/** 给界面看的一句话。空串表示没有要说的。 */
export const schoolImportMessage = ref("");

/** 正在保存时置真，界面据此禁用按钮。 */
export const schoolImporting = ref(false);

let bridge: SchoolProgressBridge | null = null;
let listener: ((event: MessageEvent) => void) | null = null;

/** 供「连接导入扩展」按钮调用：登记本页为接收页面。 */
export function requestSchoolImport(): void {
  if (!bridge) return;
  schoolImportMessage.value =
    "正在连接扩展；若没有响应，请确认扩展已加载并刷新本页。";
  bridge.requestImport();
}

/**
 * 校验并保存一份学业进度快照。
 *
 * 扩展送来的和学生手动选的 JSON 文件走的是同一条路：同样的校验、同样的报错，
 * 不存在「扩展能存、文件不能存」这种差别。
 */
export async function saveSchoolProgressPayload(
  payload: unknown,
): Promise<void> {
  const store = usePlanningStore();
  const snapshot = schoolProgressFromBridge(payload);
  if (api.mode === "fixture")
    throw new Error("学校学业进度导入需要真实服务模式。");
  if (!store.selectedCurriculumId)
    throw new Error("请先选择培养方案，再导入学校学业进度。");
  schoolImporting.value = true;
  schoolImportMessage.value = "正在保存学校学业进度并更新学业核对。";
  try {
    const saved = await store.importSchoolProgress(snapshot);
    if (!saved)
      throw new Error(store.schoolProgressError || "保存失败，请重试。");
  } finally {
    schoolImporting.value = false;
  }
}

export function startSchoolProgressBridge(router: Router): () => void {
  bridge = createSchoolProgressBridge({
    save: (payload) => saveSchoolProgressPayload(payload),
    post(message) {
      globalThis.window.postMessage(message, globalThis.location.origin);
    },
    newRequestId: () => crypto.randomUUID(),
  });

  listener = (event: MessageEvent) => {
    if (
      event.source !== globalThis.window ||
      event.origin !== globalThis.location.origin
    )
      return;
    void bridge?.handle(event.data).then(async (outcome) => {
      if (outcome.kind === "ignored") return;
      schoolImportMessage.value = outcome.message;
      // 存成功了但人不在学业资料页，就把他带过去看结果。
      if (
        outcome.kind === "saved" &&
        !router.currentRoute.value.path.startsWith("/records")
      ) {
        await router.push("/records");
      }
    });
  };
  globalThis.window.addEventListener("message", listener);

  return () => {
    if (listener) globalThis.window.removeEventListener("message", listener);
    listener = null;
    bridge = null;
  };
}
