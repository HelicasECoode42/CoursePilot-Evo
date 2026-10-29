import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import SetupView from "./SetupView.vue";

const mountSetup = async (pagePort = "5173") => {
  // 端口由 prop 注入：jsdom 的 location.port 不可改写，否则测不到这条分支。
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
    global: { plugins: [router] },
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
  it("第 3 步链到已有的学校导入入口，不另写一套导入", async () => {
    const wrapper = await mountSetup();
    const targets = wrapper.findAll("a").map((a) => a.attributes("href"));
    expect(targets).toContain("/records?import=school");
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
