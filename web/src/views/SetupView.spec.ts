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

const probeButton = (wrapper: ReturnType<typeof mount>) =>
  wrapper.findAll("button").find((b) => b.text().includes("探测插件"))!;

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("配置三步", () => {
  it("讲明「先连接再导入」的顺序，并说反过来会看到什么", async () => {
    // background.js 要求先由 CoursePilot 页面发 CP_START_IMPORT 登记接收标签页，
    // 学校页面的导入才有地方送。顺序反了学校那边会提示「请先在 CoursePilot
    // 点击连接教务」，不说清楚就会被当成故障。
    const wrapper = await mountSetup();
    const text = wrapper.text();
    expect(text).toContain("先连接，再导入");
    expect(text).toContain("先不要点浮窗里的导入");
    expect(text).toContain("请先在 CoursePilot 点击连接教务");
  });

  it("去学业资料页之前先建会话，不把人送进死胡同", async () => {
    // /records 自己不建会话，没有会话时只显示「还没有可用会话，请先回到引导页」。
    // 从配置页直接链过去就是死路，所以这一步必须先 startSession 再跳。
    const wrapper = await mountSetup();
    const store = usePlanningStore();
    const startSession = vi
      .spyOn(store, "startSession")
      .mockImplementation(async () => {
        store.$patch({ sessionStatus: "ready", sessionId: "session-test" });
      });
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("去学业资料页"))!
      .trigger("click");
    await flushPromises();
    expect(startSession).toHaveBeenCalled();
    expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe(
      "/records?import=school",
    );
  });

  it("建会话失败时留在原地并说明，不是静悄悄什么都不发生", async () => {
    const wrapper = await mountSetup();
    const store = usePlanningStore();
    vi.spyOn(store, "startSession").mockImplementation(async () => {
      store.$patch({ sessionStatus: "error", errorMessage: "服务没启动" });
    });
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("去学业资料页"))!
      .trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("服务没启动");
    expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe("/setup");
  });

  it("写明不代登录、不读密码、不读 Cookie", async () => {
    const wrapper = await mountSetup();
    const text = wrapper.text();
    expect(text).toContain("不替你登录");
    expect(text).toContain("不读密码");
    expect(text).toContain("不读 Cookie");
  });

  it("插件回 ok:false 也算装着了，不能误报成没装", async () => {
    // background.js 在五分钟内重复收到 CP_START_IMPORT 会回 ok:false。
    // 把这种情况当成「没装插件」会让学生白装一遍，所以必须区分开。
    const wrapper = await mountSetup();
    await probeButton(wrapper).trigger("click");
    // 直接派发事件：jsdom 的 postMessage 不填 source，过不了同源同窗守卫。
    globalThis.window.dispatchEvent(
      new MessageEvent("message", {
        data: { type: "CP_IMPORT_READY", ok: false },
        origin: globalThis.location.origin,
        source: globalThis.window,
      }),
    );
    await flushPromises();
    expect(wrapper.text()).toContain("插件已连接");
    expect(wrapper.text()).not.toContain("插件没有回应");
  });

  it("端口不是 5173 时直接说清原因，不发探测也不冤枉插件", async () => {
    const wrapper = await mountSetup("5175");
    await probeButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("5173 端口");
    expect(wrapper.text()).toContain("当前页面端口是 5175");
  });

  it("插件不回应时说明可能是没刷新，而不是断言没装", async () => {
    vi.useFakeTimers();
    const wrapper = await mountSetup();
    await probeButton(wrapper).trigger("click");
    vi.advanceTimersByTime(3000);
    await flushPromises();
    expect(wrapper.text()).toContain("插件没有回应");
    expect(wrapper.text()).toContain("刷新本页");
  });
});
