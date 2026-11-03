import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SchoolProgressTree from "./SchoolProgressTree.vue";

describe("学校学业进度树", () => {
  it("按节点 ID 保留同名父子类别和未知缺口", async () => {
    const wrapper = mount(SchoolProgressTree, {
      props: {
        nodes: [
          {
            nodeId: "parent",
            parentId: null,
            schoolNodeId: "10",
            leaf: false,
            name: "公共基础课",
            requiredCredits: 12,
            earnedCredits: 6,
            remainingCredits: 6,
          },
          {
            nodeId: "child",
            parentId: "parent",
            schoolNodeId: "11",
            leaf: true,
            name: "公共基础课",
            requiredCredits: 4,
            earnedCredits: null,
            remainingCredits: null,
          },
        ],
        courses: [
          {
            nodeId: "child",
            courseCode: "CP001",
            name: "课程样例",
            credits: 2,
            outcome: "PASSED",
            completedYear: null,
            completedTerm: null,
            grade: null,
            makeup: null,
            retake: null,
            suggestedYear: null,
            suggestedTerm: null,
          },
        ],
      },
    });
    expect(
      wrapper.findAll(
        ".school-progress-tree:not(.school-progress-tree--nested) > .school-category > h3",
      ),
    ).toHaveLength(1);
    await wrapper.get("summary").trigger("click");
    expect(wrapper.findAll(".school-category")).toHaveLength(2);
    expect(
      wrapper.findAll(".school-category h3").map((el) => el.text()),
    ).toEqual(["公共基础课", "公共基础课"]);
    expect(wrapper.findAll(".school-category")).toHaveLength(2);
    expect(
      wrapper
        .findAll(".school-category details summary")
        .map((el) => el.text().replace(/\s+/g, " ").trim()),
    ).toEqual(["查看子类别", "查看关联课程 · 1 门课程"]);
    expect(wrapper.text()).toContain("课程样例 · CP001");
    expect(wrapper.text()).toContain("已修");
    expect(
      wrapper.findAll(".school-category__remaining dd").map((el) => el.text()),
    ).toEqual(["6", "待确认"]);
  });

  it("类别名或课程名读不出来时写明未读出，不留空白项目符号", async () => {
    const wrapper = mount(SchoolProgressTree, {
      props: {
        nodes: [
          {
            nodeId: "top",
            parentId: null,
            schoolNodeId: null,
            leaf: false,
            name: "",
            requiredCredits: 12,
            earnedCredits: 2,
            remainingCredits: 10,
          },
          {
            nodeId: "mid",
            parentId: "top",
            schoolNodeId: null,
            leaf: false,
            name: "()",
            requiredCredits: 4,
            earnedCredits: 0,
            remainingCredits: 4,
          },
        ],
        courses: [
          {
            nodeId: "mid",
            courseCode: "2200R200",
            name: "",
            credits: null,
            outcome: "IN_PROGRESS",
            completedYear: null,
            completedTerm: null,
            grade: null,
            makeup: null,
            retake: null,
            suggestedYear: null,
            suggestedTerm: null,
          },
        ],
        nameLookup: (code: string) =>
          code === "2200R200" ? "形势与政策" : null,
      },
    });
    expect(
      wrapper
        .findAll(
          ".school-progress-tree:not(.school-progress-tree--nested) > .school-category > h3",
        )
        .map((el) => el.text()),
    ).toEqual(["类别名未读出"]);
    expect(
      wrapper.findAll(".school-category h3").map((el) => el.text()),
    ).toEqual(["类别名未读出", "类别名未读出"]);
    await wrapper.findAll("summary")[1]!.trigger("click");
    expect(wrapper.get(".school-courses li").text()).toContain(
      "形势与政策 · 2200R200",
    );
    expect(wrapper.get(".school-courses li").text()).toContain("学分待确认");
    expect(wrapper.get(".school-courses li").text()).toContain("在读");
  });
  it("用学校接口的真实返回形状（GET /api/v1/school-progress）渲染，每门课程行都有名称、学分与状态", async () => {
    // 字段与 snapshot 结构一致（nodeId/parentId/schoolNodeId/leaf/name/…；课程含 courseCode/name/credits/outcome），值全部为虚构。
    const wrapper = mount(SchoolProgressTree, {
      props: {
        nodes: [
          {
            nodeId: "node-1",
            parentId: null,
            schoolNodeId: "SYN-A",
            leaf: false,
            name: "示例主修类别",
            requiredCredits: 20,
            earnedCredits: 4,
            remainingCredits: 16,
          },
          {
            nodeId: "node-2",
            parentId: "node-1",
            schoolNodeId: "SYN-A1",
            leaf: true,
            name: "示例子类别",
            requiredCredits: 8,
            earnedCredits: 2,
            remainingCredits: 6,
          },
        ],
        courses: [
          {
            nodeId: "node-2",
            courseCode: "SYN0001",
            name: "示例课程一",
            credits: 2,
            outcome: "PASSED",
            completedYear: "2025-2026",
            completedTerm: "1",
            grade: "A",
            makeup: null,
            retake: null,
            suggestedYear: null,
            suggestedTerm: null,
          },
          {
            nodeId: "node-2",
            courseCode: "SYN0002",
            name: "示例课程二",
            credits: null,
            outcome: "UNKNOWN",
            completedYear: null,
            completedTerm: null,
            grade: null,
            makeup: null,
            retake: null,
            suggestedYear: null,
            suggestedTerm: null,
          },
        ],
      },
    });
    await wrapper.findAll("details summary")[1].trigger("click");
    const lines = wrapper
      .findAll(".school-courses li")
      .map((li) => li.text().replace(/\s+/g, " ").trim());
    expect(lines).toHaveLength(2);
    for (const line of lines) expect(line).not.toBe("");
    expect(lines[0]).toContain("示例课程一 · SYN0001");
    expect(lines[0]).toContain("2 学分");
    expect(lines[0]).toContain("已修");
    expect(lines[1]).toContain("示例课程二 · SYN0002");
    expect(lines[1]).toContain("学分待确认");
    expect(lines[1]).toContain("状态待确认");
  });

  it("学校只给了子类别数字时，顶层无数字卡写一句说明而不是三个待确认，主修的一级子类别默认展开", () => {
    // 字段与学校快照一致；名称与数值全部为虚构。
    const wrapper = mount(SchoolProgressTree, {
      props: {
        nodes: [
          {
            nodeId: "major",
            parentId: null,
            schoolNodeId: "SYN-M",
            leaf: false,
            name: "示例主修",
            requiredCredits: null,
            earnedCredits: null,
            remainingCredits: null,
          },
          {
            nodeId: "general",
            parentId: "major",
            schoolNodeId: "SYN-G",
            leaf: false,
            name: "示例通识课",
            requiredCredits: 10,
            earnedCredits: 6,
            remainingCredits: 4,
          },
          {
            nodeId: "core",
            parentId: "major",
            schoolNodeId: "SYN-C",
            leaf: false,
            name: "示例基础课",
            requiredCredits: 40,
            earnedCredits: 6,
            remainingCredits: 34,
          },
          {
            nodeId: "core-sub",
            parentId: "core",
            schoolNodeId: "SYN-C1",
            leaf: true,
            name: "示例更深子类别",
            requiredCredits: 8,
            earnedCredits: 6,
            remainingCredits: 2,
          },
          {
            nodeId: "other",
            parentId: null,
            schoolNodeId: "SYN-O",
            leaf: false,
            name: "示例其他课程",
            requiredCredits: null,
            earnedCredits: null,
            remainingCredits: null,
          },
        ],
        courses: [],
      },
    });
    const topCards = wrapper.findAll(
      ".school-progress-tree:not(.school-progress-tree--nested) > .school-category",
    );
    expect(topCards).toHaveLength(2);
    // 主修：没有数字，只有一句说明，不出现三个「待确认」。
    expect(topCards[0]!.element.querySelector(":scope > dl")).toBeNull();
    expect(topCards[0]!.text()).toContain(
      "学校页面没有给出这一层的总学分，请看下面各类别",
    );
    // 其他课程：没有数字、没有子类别、没有课程，给一行说明。
    expect(topCards[1]!.element.querySelector(":scope > dl")).toBeNull();
    expect(topCards[1]!.text()).toContain("学校页面没有列出这一类的学分和课程");
    expect(topCards[1]!.text()).not.toContain("待确认");
    // 主修的 details 默认展开，第一级子类别的数字直接可见；更深一层仍收起。
    const details = wrapper
      .findAll("details")
      .map((d) => d.element as HTMLDetailsElement);
    expect(details[0]!.open).toBe(true);
    expect(details[1]!.open).toBe(false);
    // 还差 > 0 的类别有徽标；还差 0 或未知不显示。
    expect(
      wrapper.findAll(".school-category__badge").map((el) => el.text()),
    ).toEqual(["还差 4 学分", "还差 34 学分", "还差 2 学分"]);
    // 顶层摘要只列主修第一级、按还差从大到小，不把更深一层加进去。
    expect(wrapper.get(".school-remaining-summary").text()).toBe(
      "按学校报告还差：示例基础课 34、示例通识课 4",
    );
  });

  it("没有主修节点时不显示顶层摘要，已知数字仍按学校报告显示", () => {
    const wrapper = mount(SchoolProgressTree, {
      props: {
        nodes: [
          {
            nodeId: "solo",
            parentId: null,
            schoolNodeId: "SYN-S",
            leaf: true,
            name: "示例类别",
            requiredCredits: 5,
            earnedCredits: 0,
            remainingCredits: 5,
          },
        ],
        courses: [],
      },
    });
    expect(wrapper.find(".school-remaining-summary").exists()).toBe(false);
    expect(wrapper.get(".school-category__remaining dd").text()).toBe("5");
    expect(wrapper.get(".school-category__source").text()).toBe("学校报告");
  });
});
