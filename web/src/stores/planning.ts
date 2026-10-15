import { defineStore } from "pinia";
import { computed, onScopeDispose, ref } from "vue";
import { ApiFailure, type CoursePilotApiClient } from "../api/client";
import { api } from "../api";
import type { Motive, PlanningRequest, SnapshotSummary } from "../contracts";
import type { ClassPreferenceId } from "../domain/class-preferences";
import {
  adjacentQuestion,
  emptyPlanningDraft,
  firstIncompleteQuestion,
  questionSequence,
  type PlanningDraft,
  type QuestionId,
} from "../domain/question-flow";
import { buildPlanningRequest } from "../domain/planning-request";
import {
  applyScheduleAction,
  type ScheduleAction,
  type ScheduleStrength,
} from "../domain/schedule-grid";

export type SessionStatus = "idle" | "loading" | "ready" | "error" | "expired";
type MissingContextLabel =
  | "有效会话"
  | "培养方案"
  | "真实培养方案"
  | "已核验培养方案"
  | "学业记录"
  | "已确认目标优先级"
  | "上课与考核偏好"
  | "时间安排";

const MAX_TIMER_DELAY_MS = 2_147_000_000;

export function createPlanningStore(client: CoursePilotApiClient = api) {
  return defineStore("coursepilot-planning", () => {
    const sessionStatus = ref<SessionStatus>("idle");
    const sessionId = ref<string | null>(null);
    const expiresAt = ref<string | null>(null);
    const curricula = ref<SnapshotSummary[]>([]);
    const selectedCurriculumId = ref<string | null>(null);
    const unknownMessages = ref<string[]>([]);
    const errorMessage = ref("");
    const sessionVersion = ref(0);
    const draft = ref<PlanningDraft>(emptyPlanningDraft());
    const planningHandoff = ref<PlanningRequest | null>(null);
    const handoffMissing = ref<MissingContextLabel[]>([]);
    const handoffHints = ref<string[]>([]);
    let activeController: AbortController | null = null;
    let expiryTimer: ReturnType<typeof setTimeout> | null = null;

    function clearPlanningHandoff() {
      planningHandoff.value = null;
      handoffMissing.value = [];
      handoffHints.value = [];
    }

    function clearExpiryTimer() {
      if (expiryTimer !== null) clearTimeout(expiryTimer);
      expiryTimer = null;
    }

    function invalidateSession(message = "本次会话已失效，请重新开始。") {
      clearExpiryTimer();
      const controller = activeController;
      activeController = null;
      controller?.abort();
      sessionVersion.value += 1;
      client.clearSession();
      sessionId.value = null;
      expiresAt.value = null;
      curricula.value = [];
      selectedCurriculumId.value = null;
      sessionStatus.value = "expired";
      errorMessage.value = message;
      clearPlanningHandoff();
    }

    function expireSessionWhenDue() {
      expiryTimer = null;
      if (!sessionId.value || !expiresAt.value) return;
      const remaining = Date.parse(expiresAt.value) - Date.now();
      if (!Number.isFinite(remaining) || remaining <= 0) {
        invalidateSession("本次会话已过期，请重新开始。");
        return;
      }
      expiryTimer = setTimeout(
        expireSessionWhenDue,
        Math.min(remaining, MAX_TIMER_DELAY_MS),
      );
    }

    function scheduleSessionExpiry() {
      clearExpiryTimer();
      expireSessionWhenDue();
    }

    const currentQuestion = computed<QuestionId>(() =>
      firstIncompleteQuestion({
        draft: draft.value,
        curricula: curricula.value,
        selectedCurriculumId: selectedCurriculumId.value,
      }),
    );
    const questions = computed(() =>
      questionSequence({ curricula: curricula.value }),
    );
    const selectedCurriculum = computed(
      () =>
        curricula.value.find(
          (item) => item.snapshotId === selectedCurriculumId.value,
        ) ?? null,
    );
    const mode = computed(() => client.mode);

    function visibleError(error: unknown): string {
      if (error instanceof ApiFailure) return error.message;
      return "暂时无法完成请求，请稍后重试。";
    }

    async function startSession(): Promise<void> {
      if (sessionStatus.value === "loading") return;
      if (
        sessionId.value &&
        (!expiresAt.value ||
          !Number.isFinite(Date.parse(expiresAt.value)) ||
          Date.parse(expiresAt.value) <= Date.now())
      ) {
        invalidateSession();
      }
      const version = ++sessionVersion.value;
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      errorMessage.value = "";
      unknownMessages.value = [];
      clearPlanningHandoff();
      sessionStatus.value = "loading";

      try {
        if (!sessionId.value) {
          const session = await client.createSession(controller.signal);
          if (version !== sessionVersion.value) return;
          const expiry = Date.parse(session.expiresAt);
          if (!Number.isFinite(expiry) || expiry <= Date.now()) {
            throw new ApiFailure(
              "服务返回的会话已过期，请重新开始。",
              "invalid_response",
            );
          }
          sessionId.value = session.sessionId;
          expiresAt.value = session.expiresAt;
          scheduleSessionExpiry();
        }

        if (!sessionId.value)
          throw new ApiFailure("无法建立会话，请重试。", "invalid_response");
        const result = await client.listCurricula(controller.signal);
        if (version !== sessionVersion.value) return;
        clearPlanningHandoff();
        curricula.value = result.items;
        unknownMessages.value = result.unknownMessages;
        selectedCurriculumId.value =
          result.items.length === 1 ? result.items[0].snapshotId : null;
        sessionStatus.value = "ready";
        if (result.items.length === 0) {
          errorMessage.value =
            "目前没有可用的培养方案，请稍后重试或联系课程资料维护者。";
        }
      } catch (error) {
        if (
          version !== sessionVersion.value ||
          (error instanceof ApiFailure && error.kind === "aborted")
        ) {
          return;
        }
        if (error instanceof ApiFailure && error.status === 401) {
          invalidateSession(error.message);
          return;
        }
        if (!sessionId.value) client.clearSession();
        sessionStatus.value = "error";
        errorMessage.value = visibleError(error);
      } finally {
        if (activeController === controller) activeController = null;
      }
    }

    function chooseCurriculum(snapshotId: string) {
      if (!curricula.value.some((item) => item.snapshotId === snapshotId))
        return;
      selectedCurriculumId.value = snapshotId;
      clearPlanningHandoff();
    }

    function setMotives(motives: Motive[]) {
      const unique = [...new Set(motives)];
      const previouslySelected = new Set(draft.value.motives);
      draft.value.motives = unique;
      draft.value.priorityOrder = [
        ...draft.value.priorityOrder.filter((motive) =>
          unique.includes(motive),
        ),
        ...unique.filter((motive) => !previouslySelected.has(motive)),
      ];
      draft.value.prioritiesConfirmed = false;
      clearPlanningHandoff();
    }

    function updateDraft<K extends keyof PlanningDraft>(
      key: K,
      value: PlanningDraft[K],
    ) {
      draft.value[key] = value;
      clearPlanningHandoff();
    }

    /**
     * Paint or erase cells of one strength in a single update. Both strength
     * lists stay mutually exclusive; each cell is one "星期-节次" key.
     */
    function paintScheduleSlots(
      keys: readonly string[],
      strength: ScheduleStrength,
      action: ScheduleAction,
    ) {
      const next = applyScheduleAction(draft.value, keys, strength, action);
      draft.value.mustSlots = next.mustSlots;
      draft.value.preferSlots = next.preferSlots;
      draft.value.mustReviewed = false;
      draft.value.preferReviewed = false;
      clearPlanningHandoff();
    }

    function toggleClassPreference(preference: ClassPreferenceId) {
      updateDraft(
        "classPreferences",
        draft.value.classPreferences.includes(preference)
          ? draft.value.classPreferences.filter((item) => item !== preference)
          : [...draft.value.classPreferences, preference],
      );
      draft.value.classPreferencesReviewed = false;
    }

    function movePriority(motive: Motive, offset: -1 | 1) {
      const order = [...draft.value.priorityOrder];
      const index = order.indexOf(motive);
      const destination = index + offset;
      if (index < 0 || destination < 0 || destination >= order.length) return;
      [order[index], order[destination]] = [order[destination], order[index]];
      draft.value.priorityOrder = order;
      draft.value.prioritiesConfirmed = false;
      clearPlanningHandoff();
    }

    function confirmPriorities(confirmed = true) {
      draft.value.prioritiesConfirmed = confirmed;
      clearPlanningHandoff();
    }

    function preparePlanningHandoff() {
      const expiry = expiresAt.value ? Date.parse(expiresAt.value) : NaN;
      if (sessionStatus.value !== "ready" || !sessionId.value) {
        planningHandoff.value = null;
        handoffMissing.value = ["有效会话"];
        handoffHints.value = [];
        return { ok: false, missing: ["有效会话"] as MissingContextLabel[] };
      }
      if (!Number.isFinite(expiry) || expiry <= Date.now()) {
        invalidateSession("本次会话已过期，请重新开始。");
        handoffMissing.value = ["有效会话"];
        handoffHints.value = [];
        return { ok: false, missing: ["有效会话"] as MissingContextLabel[] };
      }
      const built = buildPlanningRequest(draft.value, {
        curriculumSnapshotId: selectedCurriculumId.value,
        curriculumSourceKind: selectedCurriculum.value?.sourceKind ?? null,
        curriculumSourceValidation:
          selectedCurriculum.value?.sourceValidation ?? null,
        academicRecordId: client.fixtureAcademicRecordId(),
        offeringSnapshotId: null,
        mode: client.mode === "fixture" ? "SIMULATION" : "REAL",
      });
      planningHandoff.value = built.ok ? built.request : null;
      handoffMissing.value = built.ok ? [] : built.missing;
      handoffHints.value = built.ok ? [] : (built.hints ?? []);
      return built;
    }

    onScopeDispose(() => {
      clearExpiryTimer();
      const controller = activeController;
      activeController = null;
      controller?.abort();
      sessionVersion.value += 1;
      client.clearSession();
    });

    function previousQuestion(question: QuestionId): QuestionId {
      return adjacentQuestion(
        question,
        {
          draft: draft.value,
          curricula: curricula.value,
          selectedCurriculumId: selectedCurriculumId.value,
        },
        -1,
      );
    }

    return {
      mode,
      sessionStatus,
      sessionId,
      expiresAt,
      curricula,
      selectedCurriculumId,
      selectedCurriculum,
      unknownMessages,
      errorMessage,
      draft,
      planningHandoff,
      handoffMissing,
      handoffHints,
      currentQuestion,
      questions,
      startSession,
      invalidateSession,
      chooseCurriculum,
      setMotives,
      updateDraft,
      paintScheduleSlots,
      toggleClassPreference,
      movePriority,
      confirmPriorities,
      preparePlanningHandoff,
      previousQuestion,
    };
  });
}

export const usePlanningStore = createPlanningStore();
