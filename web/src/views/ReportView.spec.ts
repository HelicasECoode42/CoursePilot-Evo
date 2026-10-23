import { flushPromises, mount } from "@vue/test-utils";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { api } from "../api";
import { ApiFailure } from "../api/client";
import type { RunReport } from "../contracts";
import ReportView from "./ReportView.vue";

const report: RunReport = {
  runId: "run-2026-10-01",
  harnessVersion: "harness-v2",
  parentVersion: "harness-v1",
  decision: "PROMOTED",
  heldOutScore: 0.82,
  averageInputTokens: 1520,
  averageOutputTokens: 384.5,
  averageToolCalls: 3,
  averageLatencyMs: 2150,
  failureCategories: ["TOOL_TIMEOUT", "SCHEMA_MISMATCH"],
};

describe("teacher run report page", () => {
  let router: ReturnType<typeof createRouter>;
  let getRunReport: MockInstance<typeof api.getRunReport>;

  beforeEach(async () => {
    getRunReport = vi.spyOn(api, "getRunReport");
    router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/report/runs/:runId", component: ReportView }],
    });
    await router.push("/report/runs/run-2026-10-01");
    await router.isReady();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  const mountPage = () =>
    mount(
      { template: "<RouterView />" },
      { global: { plugins: [router] }, attachTo: document.body },
    );

  it("requests the report for the route runId and shows all four groups with units", async () => {
    getRunReport.mockResolvedValue(report);
    const wrapper = mountPage();
    await flushPromises();

    expect(getRunReport).toHaveBeenCalledWith(
      "run-2026-10-01",
      expect.any(AbortSignal),
    );
    const text = wrapper.text();
    expect(text).toContain("真实基线");
    expect(text).toContain("harness-v2");
    expect(text).toContain("harness-v1");
    expect(text).toContain("0.82");
    expect(text).toContain("候选决策");
    expect(text).toContain("候选已晋升");
    expect(text).toContain("PROMOTED");
    expect(text).toContain("质量成本");
    expect(text).toContain("1520 tokens");
    expect(text).toContain("384.50 tokens");
    expect(text).toContain("3 次");
    expect(text).toContain("2150 毫秒");
    expect(text).toContain("失败记录");
    expect(text).toContain("TOOL_TIMEOUT");
    expect(text).toContain("SCHEMA_MISMATCH");
    expect(wrapper.text()).toContain("这不是学生页面");
    expect(wrapper.findAll("h1")).toHaveLength(1);
  });

  it("shows null measurements as not recorded instead of zero", async () => {
    getRunReport.mockResolvedValue({
      ...report,
      parentVersion: null,
      heldOutScore: null,
      averageLatencyMs: null,
    });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("无父版本记录");
    expect(wrapper.text()).toContain("未记录");
    expect(wrapper.text()).not.toContain("毫秒");
  });

  it("says no failure categories were recorded, not that there were no failures", async () => {
    getRunReport.mockResolvedValue({ ...report, failureCategories: [] });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("本次运行没有记录失败分类。");
    expect(wrapper.text()).not.toContain("没有失败");
    expect(wrapper.findAll("ul li")).toHaveLength(0);
  });

  it.each([401, 403])(
    "reports that management permission is required on %i",
    async (status) => {
      getRunReport.mockRejectedValue(
        new ApiFailure("会话无效", "http", status, "FORBIDDEN"),
      );
      const wrapper = mountPage();
      await flushPromises();

      expect(wrapper.get("[role='alert']").text()).toContain("需要管理权限");
      expect(wrapper.text()).toContain("学生页面不会显示这些内容");
      expect(wrapper.text()).not.toContain("真实基线");
      expect(wrapper.find("dl").exists()).toBe(false);
    },
  );

  it("404 shows that the run record was not found, not an empty report", async () => {
    getRunReport.mockRejectedValue(
      new ApiFailure("需要的资料暂不可用", "http", 404, "NOT_FOUND"),
    );
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain("找不到这次运行记录");
    expect(wrapper.text()).not.toContain("真实基线");
    expect(wrapper.find("dl").exists()).toBe(false);
    expect(wrapper.find("[role='alert']").text()).toContain(
      "找不到这次运行记录",
    );
  });

  it("gives a retry prompt on other failures and never falls back to fake data", async () => {
    getRunReport.mockRejectedValue(
      new ApiFailure("服务暂时不可用", "http", 503, null, true),
    );
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain("请稍后重试");
    expect(wrapper.text()).not.toContain("需要管理权限");
    expect(wrapper.text()).not.toContain("真实基线");
    expect(wrapper.find("dl").exists()).toBe(false);

    getRunReport.mockResolvedValueOnce(report);
    await wrapper.get("button.button--secondary").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("harness-v2");
  });

  it("moves focus to the heading after loading finishes", async () => {
    getRunReport.mockResolvedValue(report);
    const wrapper = mountPage();
    await flushPromises();

    const title = wrapper.get("h1").element as HTMLElement;
    expect(title.id).toBe("report-title");
    expect(title.getAttribute("tabindex")).toBe("-1");
    expect(document.activeElement).toBe(title);
  });

  it("moves focus to the heading after a failed load as well", async () => {
    getRunReport.mockRejectedValue(
      new ApiFailure("报告不存在", "http", 404, "NOT_FOUND"),
    );
    const wrapper = mountPage();
    await flushPromises();

    expect(document.activeElement).toBe(wrapper.get("h1").element);
  });

  it("never writes the report or any credential to browser storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    getRunReport.mockResolvedValue(report);
    mountPage();
    await flushPromises();

    expect(setItem).not.toHaveBeenCalled();
    expect(getItem).not.toHaveBeenCalled();
    expect(sessionStorage.length + localStorage.length).toBe(0);
  });
});
