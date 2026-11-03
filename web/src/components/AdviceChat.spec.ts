import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdviceChatAnswer } from "../contracts";
import { emptyPlanningDraft } from "../domain/question-flow";
import { usePlanningStore } from "../stores/planning";
import AdviceChat from "./AdviceChat.vue";

const answer: AdviceChatAnswer = {
  schemaVersion: "1.0",
  reply: "可以看看这门实践课。",
  question: null,
  courses: [
    {
      courseCode: "08306099",
      name: "Java程序设计(实践)",
      credits: 4,
      category: "专业选修课",
      reason: "偏实践",
      reviewNoteIds: [],
      reviews: [],
      reviewStatus: "NOT_QUERIED",
    },
  ],
  suggestions: [
    {
      suggestionId: "suggestion:prefer",
      kind: "SELECT_COURSE",
      // 模型写成「优先考虑」，但动作是选入：按钮文字必须跟动作走。
      label: "优先考虑Java程序设计(实践)",
      value: "08306099",
    },
    {
      suggestionId: "suggestion:interest",
      kind: "INTEREST",
      label: "更偏软件开发实践",
      value: "偏软件开发实践",
    },
  ],
  schoolProgress: null,
  unknowns: [],
  usage: { inputTokens: null, outputTokens: null, toolCalls: 0, elapsedMs: 0 },
};

describe("advice chat suggestions", () => {
  let store: ReturnType<typeof usePlanningStore>;

  beforeEach(() => {
    setActivePinia(createPinia());
    store = usePlanningStore();
    store.$patch({
      adviceMessages: [{ role: "assistant", text: answer.reply, answer }],
      draft: emptyPlanningDraft(),
    });
  });

  it("names a course action by what it does, not by the model's wording", () => {
    const wrapper = mount(AdviceChat, { global: { plugins: [] } });
    const texts = wrapper.findAll("button").map((button) => button.text());
    expect(texts).toContain("加入待选：Java程序设计(实践)");
    expect(texts).not.toContain("优先考虑Java程序设计(实践)");
    expect(texts).toContain("更偏软件开发实践");
  });

  it("adds a course chosen from the chat to the pending selection exactly once", async () => {
    const wrapper = mount(AdviceChat);
    const button = wrapper
      .findAll("button")
      .find((item) => item.text() === "加入待选：Java程序设计(实践)");
    expect(button).toBeDefined();
    await button!.trigger("click");
    await button!.trigger("click");
    expect(store.draft.selectedCourseCodes).toEqual(["08306099"]);
    expect(store.draft.preferredCourseCodes).toEqual([]);
  });

  it("keeps the conversation in a fixed-height box and scrolls it to the newest message", async () => {
    const wrapper = mount(AdviceChat);
    const box = wrapper.get(".advice-chat__scroll").element as HTMLElement;
    Object.defineProperty(box, "scrollHeight", {
      configurable: true,
      value: 900,
    });
    store.$patch({
      adviceMessages: [
        ...store.adviceMessages,
        { role: "user", text: "再问一个问题" },
      ],
    });
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(900);
  });

  describe("advice chat keyboard", () => {
    beforeEach(() => {
      setActivePinia(createPinia());
    });

    function pressEnter(
      wrapper: ReturnType<typeof mount>,
      init: KeyboardEventInit,
    ): void {
      const area = wrapper.get("#dash-question").element as HTMLTextAreaElement;
      area.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          ...init,
          bubbles: true,
          cancelable: true,
        }),
      );
    }

    it("Enter sends the question, Shift+Enter does not", async () => {
      const store = usePlanningStore();
      store.$patch({ adviceMessages: [], draft: emptyPlanningDraft() });
      const send = vi.spyOn(store, "sendAdviceMessage").mockResolvedValue(true);
      const wrapper = mount(AdviceChat);
      await wrapper.get("#dash-question").setValue("想学数据库");
      pressEnter(wrapper, { shiftKey: true });
      expect(send).not.toHaveBeenCalled();
      pressEnter(wrapper, {});
      expect(send).toHaveBeenCalledWith("想学数据库");
    });

    it("ignores Enter while an IME is composing, and never sends an empty question", async () => {
      const store = usePlanningStore();
      store.$patch({ adviceMessages: [], draft: emptyPlanningDraft() });
      const send = vi.spyOn(store, "sendAdviceMessage").mockResolvedValue(true);
      const wrapper = mount(AdviceChat);
      await wrapper.get("#dash-question").setValue("数据库");
      pressEnter(wrapper, { isComposing: true });
      pressEnter(wrapper, { keyCode: 229 } as KeyboardEventInit);
      expect(send).not.toHaveBeenCalled();
      await wrapper.get("#dash-question").setValue("   ");
      pressEnter(wrapper, {});
      expect(send).not.toHaveBeenCalled();
    });
  });

  describe("已选课程列表", () => {
    beforeEach(() => {
      setActivePinia(createPinia());
    });

    it("对话里出现过的课程：显示课程名、课程号只出现一次", () => {
      const store = usePlanningStore();
      store.$patch({
        adviceMessages: [{ role: "assistant", text: answer.reply, answer }],
        draft: { ...emptyPlanningDraft(), selectedCourseCodes: ["08306099"] },
      });
      const wrapper = mount(AdviceChat);
      const text = wrapper.get("[aria-label='已加入待选课程']").text();
      expect(text).toContain("Java程序设计(实践)（08306099）· 4 学分");
      expect(text.split("08306099")).toHaveLength(2);
      expect(text).not.toContain("08306099 08306099");
    });

    it("对话里没有、但页面目录里有的课程：用目录里的名字", () => {
      const store = usePlanningStore();
      store.$patch({
        adviceMessages: [],
        draft: {
          ...emptyPlanningDraft(),
          preferredCourseCodes: ["08305092"],
        },
      });
      const wrapper = mount(AdviceChat, {
        props: {
          lookupCourse: (code: string) =>
            code === "08305092" ? { name: "数据结构", credits: 3 } : null,
        },
      });
      const text = wrapper.get("[aria-label='优先考虑课程']").text();
      expect(text).toContain("数据结构（08305092）· 3 学分 · 优先考虑");
      expect(text.split("08305092")).toHaveLength(2);
    });

    it("名字都查不到时写「课程号（名称未加载）」，不把课程号写两遍", () => {
      const store = usePlanningStore();
      store.$patch({
        adviceMessages: [],
        draft: {
          ...emptyPlanningDraft(),
          selectedCourseCodes: ["08305092"],
        },
      });
      const wrapper = mount(AdviceChat);
      const text = wrapper.get("[aria-label='已加入待选课程']").text();
      expect(text).toContain("课程号 08305092（名称未加载）");
      expect(text.split("08305092")).toHaveLength(2);
      expect(wrapper.find("[aria-label='取消选择 08305092']").exists()).toBe(
        true,
      );
    });
  });
});
