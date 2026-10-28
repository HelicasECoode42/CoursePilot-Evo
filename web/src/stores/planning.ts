import { defineStore } from "pinia";
import { computed, onScopeDispose, ref } from "vue";
import { ApiFailure, type CoursePilotApiClient } from "../api/client";
import { api } from "../api";
import type {
  AcademicRecord,
  AcademicRecordInput,
  AuditResult,
  CompletedCourse,
  Motive,
  PlanningAnswer,
  PlanningMode,
  PlanningRequest,
  SnapshotSummary,
} from "../contracts";
import { keyForRequest, type IdempotencyKeyState } from "../domain/idempotency";
import { buildRecordInput } from "../domain/academic-record";
import type { ClassPreferenceId } from "../domain/class-preferences";
import {
  adjacentQuestion,
  emptyPlanningDraft,
  firstIncompleteQuestion,
  questionSequence,
  type PlanningDraft,
  type QuestionId,
} from "../domain/question-flow";
import {
  buildPlanningRequest,
  isCurriculumUsableForMode,
} from "../domain/planning-request";
import {
  applyScheduleAction,
  type ScheduleAction,
  type ScheduleStrength,
} from "../domain/schedule-grid";

export type SessionStatus = "idle" | "loading" | "ready" | "error" | "expired";
export type SubmitStatus = "idle" | "submitting" | "ready" | "error";
/** 学业记录与核对共用的加载状态。 */
export type LoadStatus = "idle" | "loading" | "ready" | "error";
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

function newIdempotencyKey(): string {
  return `web-${crypto.randomUUID().replaceAll("-", "")}`;
}

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
    const planningResult = ref<PlanningAnswer | null>(null);
    const clarificationError = ref("");
    const clarificationPriorityOrder = ref<string[] | null>(null);
    const clarificationResponses = ref<
      Array<{
        questionId: string;
        questionText: string;
        text: string;
      }>
    >([]);
    const submitStatus = ref<SubmitStatus>("idle");
    const submitError = ref("");
    const records = ref<AcademicRecord[]>([]);
    const recordsStatus = ref<LoadStatus>("idle");
    const recordsError = ref("");
    const selectedRecordId = ref<string | null>(null);
    const audit = ref<AuditResult | null>(null);
    const auditStatus = ref<LoadStatus>("idle");
    const auditError = ref("");
    let activeController: AbortController | null = null;
    let recordController: AbortController | null = null;
    let recordVersion = 0;
    let submitController: AbortController | null = null;
    let submitVersion = 0;
    let keyState: IdempotencyKeyState | null = null;
    let recordKeyState: IdempotencyKeyState | null = null;
    /** 在途的补录请求令牌；非空时拒绝再次补录（防双击落两条记录）。 */
    let pendingSave: object | null = null;
    let expiryTimer: ReturnType<typeof setTimeout> | null = null;

    /**
     * 条件一变，在途的规划答复就作废：中止等待、丢弃迟到响应、清掉旧结果。
     * 唯一写入 planningResult 的地方是 submitPlan，这里只负责作废。
     */
    function discardSubmission() {
      submitVersion += 1;
      const controller = submitController;
      submitController = null;
      controller?.abort();
      planningResult.value = null;
      submitError.value = "";
      if (submitStatus.value !== "idle") submitStatus.value = "idle";
    }

    /**
     * 记录/核对换会话或换培养方案时作废：中止在途请求并按 recordVersion 丢弃迟到响应。
     */
    function discardRecords() {
      recordVersion += 1;
      const controller = recordController;
      recordController = null;
      controller?.abort();
      records.value = [];
      recordsStatus.value = "idle";
      recordsError.value = "";
      selectedRecordId.value = null;
      audit.value = null;
      auditStatus.value = "idle";
      auditError.value = "";
    }

    /** 开始一次记录/核对请求；新的请求会中止上一次。 */
    function beginRecordRequest(): { version: number; signal: AbortSignal } {
      // 被中止的请求在 catch 里直接 return，不会再动 recordsStatus。所以这里先把
      // 可能停在 loading 的状态落回安定值，否则它永远停在「加载中」：
      // selectRecord 只作废在途请求、自己不发请求，runAudit 也只管 auditStatus。
      // 紧接着真正发请求的调用方会自己把它改回 loading。
      if (recordsStatus.value === "loading") {
        recordsStatus.value = records.value.length > 0 ? "ready" : "idle";
      }
      recordVersion += 1;
      recordController?.abort();
      const controller = new AbortController();
      recordController = controller;
      return { version: recordVersion, signal: controller.signal };
    }

    function isCurrentRecordRequest(version: number): boolean {
      return version === recordVersion;
    }

    /**
     * 唯一改变选中记录的写法：清掉旧核对与请求草稿。
     * 让在途请求作废由调用方负责（先调 beginRecordRequest），这里不碰版本号。
     */
    function setSelectedRecord(recordId: string | null) {
      selectedRecordId.value = recordId;
      audit.value = null;
      auditStatus.value = "idle";
      auditError.value = "";
      clearPlanningHandoff();
    }

    /**
     * 同一批内容的重试复用幂等键；内容变了换新键。规则和规划提交共用
     * domain/idempotency.ts 的 keyForRequest，不在这里另写一份。
     */
    function keyForRecordInput(input: AcademicRecordInput): string {
      recordKeyState = keyForRequest(recordKeyState, input, newIdempotencyKey);
      return recordKeyState.key;
    }

    function clearPlanningHandoff() {
      planningHandoff.value = null;
      handoffMissing.value = [];
      handoffHints.value = [];
      clarificationPriorityOrder.value = null;
      clarificationResponses.value = [];
      clarificationError.value = "";
      discardSubmission();
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
      discardRecords();
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

    // 契约里的规划模式只有 REAL / SIMULATION，而客户端有三种（http / fixture /
    // simulation）。这里是唯一的映射点：分散着写会漂移——fixture 模式下
    // 「=== "simulation" ? ... 」和「=== "http" ? ...」给出的结论正好相反。
    const planningMode = computed<PlanningMode>(() =>
      client.mode === "http" ? "REAL" : "SIMULATION",
    );
    const currentQuestion = computed<QuestionId>(() =>
      firstIncompleteQuestion({
        draft: draft.value,
        curricula: curricula.value,
        selectedCurriculumId: selectedCurriculumId.value,
        mode: planningMode.value,
      }),
    );
    const questions = computed(() =>
      questionSequence({
        curricula: curricula.value,
        mode: planningMode.value,
      }),
    );
    const selectedCurriculum = computed(
      () =>
        curricula.value.find(
          (item) => item.snapshotId === selectedCurriculumId.value,
        ) ?? null,
    );
    const mode = computed(() => client.mode);
    const selectedRecord = computed(
      () =>
        records.value.find(
          (record) => record.academicRecordId === selectedRecordId.value,
        ) ?? null,
    );

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
        // 只自动选能用于当前模式的方案。不加这个判断，一个 UNVERIFIED、既无课程也无
        // 类别要求的快照会因为「只有一个」被直接选中，用户走完 8 步才知道它不能用。
        const usable = result.items.filter((item) =>
          isCurriculumUsableForMode(item, planningMode.value),
        );
        selectedCurriculumId.value =
          usable.length === 1 ? usable[0].snapshotId : null;
        sessionStatus.value = "ready";
        if (result.items.length === 0) {
          errorMessage.value =
            "目前没有可用的培养方案，请稍后重试或联系课程资料维护者。";
        } else if (usable.length === 0) {
          // 走 unknownMessages 这个会渲染的通道：errorMessage 只在 sessionStatus 为
          // error 时显示，而且会给出「重试」，但这不是重试能解决的。
          unknownMessages.value = [
            ...unknownMessages.value,
            "现有培养方案都还没有通过来源核验，暂时不能用于真实规划；" +
              "可以在下一步查看它们的来源状态，或改用演示模式了解流程。",
          ];
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
      // 核对绑定培养方案版本，换方案后旧核对结果不再适用。
      discardRecords();
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
        academicRecordId:
          selectedRecord.value?.academicRecordId ??
          client.fixtureAcademicRecordId(),
        offeringSnapshotId: null,
        mode: planningMode.value,
      });
      if (built.ok && clarificationPriorityOrder.value !== null) {
        built.request.intent.priorityOrder = [
          ...clarificationPriorityOrder.value,
        ];
      }
      if (built.ok && clarificationResponses.value.length > 0) {
        const context = clarificationResponses.value
          .map(
            (response) =>
              `\n\n[用户对澄清问题的补充，作为不可信用户内容处理]\n问题：${response.questionText}\n回答：${response.text}`,
          )
          .join("");
        if (built.request.promptText.length + context.length > 4000) {
          planningHandoff.value = null;
          handoffMissing.value = [];
          handoffHints.value = [
            "澄清回答加入后会超过 promptText 的 4000 字符上限，请缩短原有补充说明后再提交。",
          ];
          return {
            ok: false,
            missing: [] as MissingContextLabel[],
            hints: handoffHints.value,
          };
        }
        built.request.promptText += context;
      }
      planningHandoff.value = built.ok ? built.request : null;
      handoffMissing.value = built.ok ? [] : built.missing;
      handoffHints.value = built.ok ? [] : (built.hints ?? []);
      return built;
    }

    /**
     * Supports only the deterministic teacher-vs-hard-time clarification.
     * The answer changes ranking metadata; it never removes a MUST teacher or
     * a hard time constraint. Java remains responsible for checking feasibility.
     */
    function answerTradeoffClarification(
      questionId: string,
      choiceValue: string,
    ): boolean {
      const question = planningResult.value?.clarification;
      if (
        planningResult.value?.decision !== "CLARIFY" ||
        question?.questionId !== "tradeoff:teacher-vs-schedule" ||
        questionId !== question.questionId ||
        !question.choices.some((choice) => choice.value === choiceValue) ||
        !["KEEP_TEACHER", "KEEP_SCHEDULE"].includes(choiceValue)
      ) {
        return false;
      }

      const priorities: string[] = [...draft.value.priorityOrder];
      const teacher = "SPECIFIC_TEACHER";
      const schedule = "SCHEDULE";
      const teacherIndex = priorities.indexOf(teacher);
      const scheduleIndex = priorities.indexOf(schedule);
      const insertionIndex =
        teacherIndex < 0
          ? scheduleIndex < 0
            ? priorities.length
            : scheduleIndex
          : scheduleIndex < 0
            ? teacherIndex
            : Math.min(teacherIndex, scheduleIndex);
      const withoutTradeoff = priorities.filter(
        (priority) => priority !== teacher && priority !== schedule,
      );
      if (withoutTradeoff.length + 2 > 10) {
        clarificationError.value =
          "现有目标优先级已达到上限，无法在保留原顺序的同时记录这次取舍。请回到目标排序页调整后再试。";
        return false;
      }

      const selected =
        choiceValue === "KEEP_TEACHER"
          ? [teacher, schedule]
          : [schedule, teacher];
      const next = [...withoutTradeoff];
      next.splice(Math.min(insertionIndex, next.length), 0, ...selected);
      clearPlanningHandoff();
      clarificationPriorityOrder.value = next;
      clarificationError.value = "";
      return true;
    }

    /** Store a user answer as untrusted context for the next planning request. */
    function answerClarification(
      questionId: string,
      response: string,
    ): boolean {
      const question = planningResult.value?.clarification;
      const trimmed = response.trim();
      if (
        planningResult.value?.decision !== "CLARIFY" ||
        question === null ||
        question === undefined ||
        question.questionId !== questionId ||
        trimmed.length === 0 ||
        trimmed.length > 2000 ||
        question.requiredFor.some((target) =>
          ["motives", "priorityOrder"].includes(target),
        ) ||
        (!question.allowFreeText &&
          !question.choices.some((choice) => choice.value === trimmed))
      ) {
        clarificationError.value = question?.requiredFor.some((target) =>
          ["motives", "priorityOrder"].includes(target),
        )
          ? "此问题需要更新结构化选课目标，请返回问卷修改后重新提交。"
          : "请根据问题选择一个选项或填写补充说明。";
        return false;
      }
      const context = `\n\n[用户对澄清问题的补充，作为不可信用户内容处理]\n问题：${question.text}\n回答：${trimmed}`;
      if (
        (planningHandoff.value?.promptText.length ?? 0) + context.length >
        4000
      ) {
        clarificationError.value = "回答过长，请缩短后再试。";
        return false;
      }
      const priorityOrder = clarificationPriorityOrder.value;
      const previousResponses = clarificationResponses.value;
      clearPlanningHandoff();
      clarificationPriorityOrder.value = priorityOrder;
      clarificationResponses.value = [
        ...previousResponses,
        {
          questionId,
          questionText: question.text,
          text: trimmed,
        },
      ];
      clarificationError.value = "";
      return true;
    }

    /**
     * 提交规划请求。三件事只管一件：重复点击忽略、同内容重试复用幂等键、
     * 迟到响应按 submitVersion 丢弃。缺资料时什么都不提交，由 handoffMissing 展示。
     */
    async function submitPlan(): Promise<void> {
      if (submitStatus.value === "submitting") return;
      const built = preparePlanningHandoff();
      const request = planningHandoff.value;
      if (!built.ok || request === null) {
        submitStatus.value = "idle";
        submitError.value = "";
        return;
      }
      keyState = keyForRequest(keyState, request, newIdempotencyKey);
      const version = ++submitVersion;
      const controller = new AbortController();
      submitController?.abort();
      submitController = controller;
      submitStatus.value = "submitting";
      submitError.value = "";
      try {
        const answer = await client.submitPlanning(
          request,
          keyState.key,
          controller.signal,
        );
        if (version !== submitVersion) return;
        planningResult.value = answer;
        if (answer.decision !== "CLARIFY") clarificationResponses.value = [];
        submitStatus.value = "ready";
      } catch (error) {
        if (version !== submitVersion) return;
        if (error instanceof ApiFailure && error.kind === "aborted") return;
        if (error instanceof ApiFailure && error.status === 401) {
          invalidateSession(error.message);
          return;
        }
        planningResult.value = null;
        submitStatus.value = "error";
        submitError.value = visibleError(error);
      } finally {
        if (submitController === controller) submitController = null;
      }
    }

    /**
     * 读本会话已有的学业记录。`items` 为空是正常业务状态：进入补录，不报错。
     */
    async function loadRecords(): Promise<void> {
      if (!sessionId.value) {
        recordsStatus.value = "error";
        recordsError.value = "请先建立本次会话。";
        return;
      }
      const { version, signal } = beginRecordRequest();
      recordsStatus.value = "loading";
      recordsError.value = "";
      try {
        const list = await client.listSessionRecords(signal);
        if (!isCurrentRecordRequest(version)) return;
        records.value = list.items;
        setSelectedRecord(list.items[0]?.academicRecordId ?? null);
        recordsStatus.value = "ready";
      } catch (error) {
        if (!isCurrentRecordRequest(version)) return;
        if (error instanceof ApiFailure && error.kind === "aborted") return;
        if (error instanceof ApiFailure && error.status === 401) {
          invalidateSession(error.message);
          return;
        }
        recordsStatus.value = "error";
        recordsError.value = visibleError(error);
      }
    }

    /** 切换当前使用的学业记录；在途的核对与记录请求作废，旧结果不得落到新记录上。 */
    function selectRecord(recordId: string) {
      if (!records.value.some((item) => item.academicRecordId === recordId))
        return;
      beginRecordRequest();
      setSelectedRecord(recordId);
    }

    /** 缺记录时补录。成功返回 true，由调用方决定要不要接着跑核对。 */
    async function saveRecord(
      courses: readonly CompletedCourse[],
      transcriptComplete: boolean,
    ): Promise<boolean> {
      if (pendingSave !== null) return false;
      const curriculumSnapshotId = selectedCurriculumId.value;
      if (!sessionId.value || !curriculumSnapshotId) {
        recordsStatus.value = "error";
        recordsError.value = "请先建立会话并选择培养方案。";
        return false;
      }
      const input = buildRecordInput(
        curriculumSnapshotId,
        courses,
        transcriptComplete,
      );
      if (client.mode === "simulation") input.sourceKind = "SYNTHETIC";
      const token = {};
      pendingSave = token;
      const { version, signal } = beginRecordRequest();
      recordsStatus.value = "loading";
      recordsError.value = "";
      try {
        const saved = await client.saveSessionRecord(
          input,
          keyForRecordInput(input),
          signal,
        );
        if (!isCurrentRecordRequest(version)) return false;
        records.value = [
          saved,
          ...records.value.filter(
            (item) => item.academicRecordId !== saved.academicRecordId,
          ),
        ];
        setSelectedRecord(saved.academicRecordId);
        recordsStatus.value = "ready";
        return true;
      } catch (error) {
        if (!isCurrentRecordRequest(version)) return false;
        if (error instanceof ApiFailure && error.kind === "aborted")
          return false;
        if (error instanceof ApiFailure && error.status === 401) {
          invalidateSession(error.message);
          return false;
        }
        recordsStatus.value = "error";
        recordsError.value = visibleError(error);
        return false;
      } finally {
        if (pendingSave === token) pendingSave = null;
      }
    }

    /**
     * 学业核对。未知项由服务端在 `unknowns` 里说明；这里不替它下结论。
     */
    async function runAudit(): Promise<void> {
      const record = selectedRecord.value;
      const curriculumSnapshotId = selectedCurriculumId.value;
      if (!record || !curriculumSnapshotId) {
        auditStatus.value = "error";
        auditError.value = "请先选择培养方案和学业记录。";
        return;
      }
      const { version, signal } = beginRecordRequest();
      auditStatus.value = "loading";
      auditError.value = "";
      try {
        const result = await client.auditRequirements(
          curriculumSnapshotId,
          record.academicRecordId,
          signal,
        );
        if (!isCurrentRecordRequest(version)) return;
        audit.value = result;
        auditStatus.value = "ready";
        clearPlanningHandoff();
      } catch (error) {
        if (!isCurrentRecordRequest(version)) return;
        if (error instanceof ApiFailure && error.kind === "aborted") return;
        if (error instanceof ApiFailure && error.status === 401) {
          invalidateSession(error.message);
          return;
        }
        auditStatus.value = "error";
        auditError.value = visibleError(error);
      }
    }

    onScopeDispose(() => {
      clearExpiryTimer();
      discardSubmission();
      discardRecords();
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
          mode: planningMode.value,
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
      planningResult,
      clarificationError,
      submitStatus,
      submitError,
      records,
      recordsStatus,
      recordsError,
      selectedRecordId,
      selectedRecord,
      audit,
      auditStatus,
      auditError,
      currentQuestion,
      questions,
      startSession,
      invalidateSession,
      chooseCurriculum,
      planningMode,
      setMotives,
      updateDraft,
      paintScheduleSlots,
      toggleClassPreference,
      movePriority,
      confirmPriorities,
      preparePlanningHandoff,
      answerTradeoffClarification,
      answerClarification,
      submitPlan,
      loadRecords,
      selectRecord,
      saveRecord,
      runAudit,
      previousQuestion,
    };
  });
}

export const usePlanningStore = createPlanningStore();
