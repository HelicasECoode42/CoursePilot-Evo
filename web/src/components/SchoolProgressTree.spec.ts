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
    expect(wrapper.text()).toContain("已通过");
    expect(
      wrapper.findAll(".school-category__remaining dd").map((el) => el.text()),
    ).toEqual(["6", "待确认"]);
  });
});
