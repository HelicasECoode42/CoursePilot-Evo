import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { usePlanningStore } from "../stores/planning";
import RecordsView from "./RecordsView.vue";

describe("学业资料", () => {
  it("用易读的记录名称展示核对结果并返回资料确认", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = usePlanningStore();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-test",
      selectedCurriculumId: "curr-test",
      recordsStatus: "ready",
      selectedRecordId: "session:internal-id",
      records: [
        {
          academicRecordId: "session:internal-id",
          revision: 1,
          curriculumSnapshotId: "curr-test",
          completedCourses: [
            {
              courseCode: "CS101",
              earnedCredits: 3,
              outcome: "PASSED",
              completedTerm: null,
            },
          ],
          transcriptComplete: false,
          sourceKind: "SYNTHETIC",
          createdAt: "2026-01-01T00:00:00Z",
        },
      ],
    });
    vi.spyOn(store, "loadRecords").mockResolvedValue();
    vi.spyOn(store, "runAudit").mockImplementation(async () => {
      store.$patch({
        auditStatus: "ready",
        audit: {
          curriculumSnapshotId: "curr-test",
          academicRecordId: "session:internal-id",
          recordRevision: 1,
          transcriptComplete: false,
          requirements: [
            {
              requirementId: "req-1",
              courseCodes: ["CS101"],
              requiredCredits: 4,
              earnedCredits: 3,
              gapCredits: null,
              state: "UNKNOWN",
              sourceRefIds: ["source:demo"],
            },
          ],
          suggestedCourseCodes: [],
          unknowns: [
            {
              code: "TRANSCRIPT_COMPLETENESS_UNKNOWN",
              message: "技术说明",
              field: null,
              retryable: false,
            },
          ],
        },
      });
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/records", component: RecordsView },
        {
          path: "/plan/questions/ready",
          component: { template: "<p>资料确认</p>" },
        },
      ],
    });
    await router.push("/records");
    await router.isReady();
    const wrapper = mount(RecordsView, {
      global: { plugins: [pinia, router] },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("学业记录 1 · 1 门课程");
    expect(wrapper.text()).not.toContain("session:internal-id");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "修改已填写课程")!
      .trigger("click");
    expect((wrapper.get("#code-0").element as HTMLInputElement).value).toBe(
      "CS101",
    );
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "核对培养要求")!
      .trigger("click");
    expect(wrapper.text()).toContain("核对结果");
    expect(wrapper.text()).toContain("暂时无法确定剩余要求");
    expect(wrapper.text()).not.toContain("req-1");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "返回资料确认")!
      .trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/plan/questions/ready");
  });
});
