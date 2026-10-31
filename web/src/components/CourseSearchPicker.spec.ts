import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { Course } from "../contracts";
import CourseSearchPicker from "./CourseSearchPicker.vue";

vi.mock("../api", () => ({
  api: {
    mode: "fixture",
    listCourses: vi.fn(),
  },
}));

const SNAPSHOT = "curriculum-2026";
const dataStructures: Course = {
  courseCode: "08305009",
  name: "数据结构",
  credits: 3,
  category: "学科基础课",
  sourceRefIds: ["source:c1"],
};
const software: Course = {
  courseCode: "08305020",
  name: "软件工程",
  credits: null,
  category: "专业选修课",
  sourceRefIds: ["source:c2"],
};

const waitForDebounce = () =>
  new Promise((resolve) => setTimeout(resolve, 300));

function mountPicker(modelValue = "") {
  return mount(CourseSearchPicker, {
    props: {
      curriculumSnapshotId: SNAPSHOT,
      inputId: "pick",
      label: "课程",
      modelValue,
    },
  });
}

describe("CourseSearchPicker", () => {
  beforeEach(() => {
    vi.mocked(api.listCourses).mockReset();
  });

  it("searches by course name and by course code through the backend query", async () => {
    vi.mocked(api.listCourses).mockResolvedValue({
      items: [dataStructures],
      nextCursor: null,
    });
    const wrapper = mountPicker();
    await wrapper.get("#pick").setValue("数据结构");
    await waitForDebounce();
    await flushPromises();
    expect(api.listCourses).toHaveBeenLastCalledWith(
      SNAPSHOT,
      null,
      expect.anything(),
      "数据结构",
    );
    expect(wrapper.text()).toContain("08305009");
    expect(wrapper.text()).toContain("数据结构");
    expect(wrapper.text()).toContain("3 学分");

    await wrapper.get("#pick").setValue("08305009");
    await waitForDebounce();
    await flushPromises();
    expect(api.listCourses).toHaveBeenLastCalledWith(
      SNAPSHOT,
      null,
      expect.anything(),
      "08305009",
    );
  });

  it("emits the chosen course and shows it as the selection", async () => {
    vi.mocked(api.listCourses).mockResolvedValue({
      items: [dataStructures],
      nextCursor: null,
    });
    const wrapper = mountPicker();
    await wrapper.get("#pick").setValue("dsa数据");
    await waitForDebounce();
    await flushPromises();
    await wrapper.get('button[aria-label^="选择 08305009"]').trigger("click");
    expect(wrapper.emitted("select")?.[0]).toEqual([dataStructures]);
    expect(wrapper.findAll(".course-picker__choice")).toHaveLength(0);
  });

  it("writes 学分未知 instead of 0 for a course with unknown credits", async () => {
    vi.mocked(api.listCourses).mockResolvedValue({
      items: [software],
      nextCursor: null,
    });
    const wrapper = mountPicker();
    await wrapper.get("#pick").setValue("软件");
    await waitForDebounce();
    await flushPromises();
    expect(wrapper.text()).toContain("学分未知");
    expect(wrapper.text()).not.toContain("0 学分");
  });

  it("shows the selected code and name when a course is already chosen", async () => {
    const wrapper = mountPicker("08305009");
    expect(wrapper.get(".course-picker__selected").text()).toContain(
      "08305009",
    );
    expect(api.listCourses).not.toHaveBeenCalled();
  });

  it("loads the next page with the cursor and keeps the query", async () => {
    vi.mocked(api.listCourses)
      .mockResolvedValueOnce({ items: [dataStructures], nextCursor: "p2" })
      .mockResolvedValueOnce({ items: [software], nextCursor: null });
    const wrapper = mountPicker();
    await wrapper.get("#pick").setValue("软");
    await waitForDebounce();
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "加载更多结果")!
      .trigger("click");
    await flushPromises();
    expect(api.listCourses).toHaveBeenLastCalledWith(
      SNAPSHOT,
      "p2",
      expect.anything(),
      "软",
    );
    expect(wrapper.text()).toContain("软件工程");
  });

  it("clears results when the query is emptied", async () => {
    vi.mocked(api.listCourses).mockResolvedValue({
      items: [dataStructures],
      nextCursor: null,
    });
    const wrapper = mountPicker();
    await wrapper.get("#pick").setValue("数据");
    await waitForDebounce();
    await flushPromises();
    await wrapper.get("#pick").setValue("");
    await waitForDebounce();
    await flushPromises();
    expect(wrapper.findAll(".course-picker__choice")).toHaveLength(0);
  });
});
