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
});
