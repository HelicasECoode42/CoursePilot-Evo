import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import HomeView from "./HomeView.vue";

const mountHome = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: HomeView },
      { path: "/setup", component: { template: "<p>setup</p>" } },
      { path: "/me", component: { template: "<p>me</p>" } },
    ],
  });
  await router.push("/");
  await router.isReady();
  return mount(HomeView, { global: { plugins: [router] } });
};

describe("欢迎页", () => {
  it("给出去配置和进控制台两个入口", async () => {
    const wrapper = await mountHome();
    const targets = wrapper.findAll("a").map((link) => link.attributes("href"));
    expect(targets).toContain("/setup");
    expect(targets).toContain("/me");
  });

  it("把做不到的事写在首页，不只写能做什么", async () => {
    const wrapper = await mountHome();
    const text = wrapper.text();
    // 这三条是对学生的承诺边界，首页就要讲明，不能等到出错才说。
    expect(text).toContain("不替你登录教务系统");
    expect(text).toContain("不替你提交选课");
    expect(text).toContain("选课开放后才公开");
  });

  it("不把评价说成分数或星级", async () => {
    const wrapper = await mountHome();
    const text = wrapper.text();
    expect(text).toContain("不折算成分数或星级");
    expect(text).not.toMatch(/评分|星级排名|打分/);
  });
});
