import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
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
});
