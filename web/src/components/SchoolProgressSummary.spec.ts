import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { SchoolProgressNode } from "../domain/school-progress";
import SchoolProgressSummary from "./SchoolProgressSummary.vue";

function node(
  partial: Partial<SchoolProgressNode> & Pick<SchoolProgressNode, "nodeId">,
): SchoolProgressNode {
  return {
    parentId: null,
    schoolNodeId: null,
    leaf: false,
    name: "",
    requiredCredits: null,
    earnedCredits: null,
    remainingCredits: null,
    ...partial,
  };
}

const nodes: SchoolProgressNode[] = [
  node({
    nodeId: "major",
    name: "主修",
    requiredCredits: 150,
    earnedCredits: 100,
    remainingCredits: 50,
  }),
  node({
    nodeId: "core",
    parentId: "major",
    name: "学科基础课",
    requiredCredits: 40,
    earnedCredits: 6,
    remainingCredits: 34,
  }),
  node({
    nodeId: "pe",
    parentId: "major",
    name: "实践教学环节",
    requiredCredits: 30,
    earnedCredits: 0,
    remainingCredits: 30,
  }),
  node({
    nodeId: "done",
    parentId: "major",
    name: "公共选修课",
    requiredCredits: 4,
    earnedCredits: 4,
    remainingCredits: 0,
  }),
  node({
    nodeId: "core-sub",
    parentId: "core",
    name: "更深一层",
    requiredCredits: 8,
    earnedCredits: 6,
    remainingCredits: 2,
  }),
  node({ nodeId: "empty", parentId: null, name: "其他课程" }),
];

describe("「我的」页学校进度紧凑摘要", () => {
  it("显示一句还差摘要和第一级类别表格，按还差从大到小", () => {
    const wrapper = mount(SchoolProgressSummary, {
      props: { nodes, courses: [] },
    });
    expect(wrapper.get(".school-summary-line").text()).toBe(
      "按学校报告还差：学科基础课 34、实践教学环节 30",
    );
    const rows = wrapper.findAll(".school-summary-table tbody tr");
    expect(rows).toHaveLength(3);
    expect(rows[0]!.text()).toContain("学科基础课");
    expect(rows[0]!.text()).toContain("6 / 40");
    expect(rows[0]!.text()).toContain("还差 34");
    expect(rows[2]!.text()).toContain("已凑满");
  });

  it("不展示没有任何内容的类别，也不在表格里出现更深一层", () => {
    const wrapper = mount(SchoolProgressSummary, {
      props: { nodes, courses: [] },
    });
    expect(wrapper.text()).not.toContain("其他课程");
    // 顶部表格只列第一级，更深一层只在「查看全部类别」的树里。
    const tableText = wrapper.get(".school-summary-table").text();
    expect(tableText).not.toContain("更深一层");
    expect(tableText).not.toContain("其他课程");
  });

  it("完整类别树收在「查看全部类别」里，默认收起", () => {
    const wrapper = mount(SchoolProgressSummary, {
      props: { nodes, courses: [] },
    });
    const details = wrapper.get(".school-summary-all");
    expect(details.attributes("open")).toBeUndefined();
    expect(details.text()).toContain("查看全部类别");
    // 树本身仍然渲染（嵌在 details 里），且不重复顶部摘要。
    expect(wrapper.findAll(".school-progress-tree").length).toBeGreaterThan(0);
    expect(wrapper.findAll(".school-remaining-summary")).toHaveLength(0);
  });
});
