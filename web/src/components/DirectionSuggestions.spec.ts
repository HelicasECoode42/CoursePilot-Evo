import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api";
import DirectionSuggestions from "./DirectionSuggestions.vue";

describe("direction suggestions", () => {
  it("loads only when requested and adds an explicitly chosen direction", async () => {
    const load = vi.spyOn(api, "listCareerDirections").mockResolvedValue([
      {
        directionId: "direction-test",
        title: "软件系统开发",
        description: "方向示例：设计接口与数据服务。",
        subjectTags: [],
        courseCodes: [],
        sourceRefIds: ["ref:example"],
      },
    ]);
    const wrapper = mount(DirectionSuggestions, {
      props: { selectedText: "" },
    });
    expect(load).not.toHaveBeenCalled();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("方向示例");
    await wrapper.get("article button").trigger("click");
    expect(wrapper.emitted("choose")).toEqual([["软件系统开发"]]);
  });
  it("keeps direction text separate from an unconfirmed choice", async () => {
    vi.spyOn(api, "listCareerDirections").mockResolvedValue([
      {
        directionId: "direction-test",
        title: "软件系统开发",
        description: "方向示例",
        subjectTags: [],
        courseCodes: [],
        sourceRefIds: [],
      },
    ]);
    const wrapper = mount(DirectionSuggestions, {
      props: { selectedText: "想了解软件系统开发" },
    });
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get("article button").attributes("disabled")).toBeDefined();
    expect(wrapper.emitted("choose")).toBeUndefined();
  });

  it("does not offer additions that exceed the career text limit", async () => {
    vi.spyOn(api, "listCareerDirections").mockResolvedValue([
      {
        directionId: "direction-test",
        title: "软件系统开发",
        description: "方向示例",
        subjectTags: [],
        courseCodes: [],
        sourceRefIds: [],
      },
    ]);
    const wrapper = mount(DirectionSuggestions, {
      props: { selectedText: `保留原文${"x".repeat(995)}` },
    });
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get("article button").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("内容已达长度上限");
    expect(wrapper.emitted("choose")).toBeUndefined();
  });
});
