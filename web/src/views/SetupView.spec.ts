import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { usePlanningStore } from "../stores/planning";
import SetupView from "./SetupView.vue";

const mountSetup = async (pagePort = "5173") => {
  // 端口由 prop 注入：jsdom 的 location.port 不可改写，否则测不到这条分支。
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/setup", component: SetupView },
      { path: "/records", component: { template: "<p>records</p>" } },
      { path: "/me", component: { template: "<p>me</p>" } },
      { path: "/", component: { template: "<p>home</p>" } },
    ],
  });
  await router.push("/setup");
  await router.isReady();
  return mount(SetupView, {
    props: { pagePort },
    global: { plugins: [pinia, router] },
    attachTo: document.body,
  });
};

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("连接学业资料", () => {
  const connectButton = (wrapper: Awaited<ReturnType<typeof mountSetup>>) =>
    wrapper
      .findAll("button")
      .find((button) => button.text().includes("连接我的学业资料"))!;
  it("先解释连接与返回的顺序，打开页面不占用扩展的导入任务", async () => {
    const post = vi.spyOn(globalThis.window, "postMessage");
    const wrapper = await mountSetup();
    expect(wrapper.text()).toContain("先连接扩展，再打开学校学业情况");
    expect(wrapper.text()).toContain("导入 CoursePilot 并返回");
    expect(post).not.toHaveBeenCalled();
  });
  it("去导入之前建立会话", async () => {
    const wrapper = await mountSetup();
    const store = usePlanningStore();
    const start = vi
      .spyOn(store, "startSession")
      .mockImplementation(async () => {
        store.$patch({ sessionStatus: "ready", sessionId: "session-test" });
      });
    await connectButton(wrapper).trigger("click");
    await flushPromises();
    expect(start).toHaveBeenCalledOnce();
    expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe(
      "/records?import=school",
    );
  });
  it("连接失败时保留重试入口和具体错误", async () => {
    const wrapper = await mountSetup();
    const store = usePlanningStore();
    vi.spyOn(store, "startSession").mockImplementation(async () => {
      store.$patch({ sessionStatus: "error", errorMessage: "服务没启动" });
    });
    await connectButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("服务没启动");
    expect(wrapper.vm.$router.currentRoute.value.path).toBe("/setup");
    expect(connectButton(wrapper).attributes("disabled")).toBeUndefined();
  });
  it("已有会话直接沿用", async () => {
    const wrapper = await mountSetup();
    const store = usePlanningStore();
    store.$patch({ sessionStatus: "ready", sessionId: "session-test" });
    const start = vi.spyOn(store, "startSession");
    await connectButton(wrapper).trigger("click");
    await flushPromises();
    expect(start).not.toHaveBeenCalled();
    expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe(
      "/records?import=school",
    );
  });
  it("端口不匹配时给出扩展支持的入口，同时保留文件导入", async () => {
    const wrapper = await mountSetup("5176");
    expect(wrapper.find('a[href="http://127.0.0.1:5173/setup"]').exists()).toBe(
      true,
    );
    expect(wrapper.text()).toContain("当前页面端口是 5176");
    expect(wrapper.text()).toContain("已有的学业汇总文件");
  });
  it("读取范围说明可以展开查看", async () => {
    const wrapper = await mountSetup();
    expect(wrapper.get(".setup-privacy summary").text()).toBe(
      "会读取哪些内容？",
    );
    expect(wrapper.text()).toContain("不读密码、不读 Cookie");
  });
});
