import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import LocalAuditSummary from "./LocalAuditSummary.vue";

// 形状与 GET /api/v1/requirements/audit 返回的 unknowns 一致，课程号与文字均为虚构。
describe("本地核对摘要", () => {
  it("每个分组下的课程与说明都有可读文字，不出现空白列表项", async () => {
    const wrapper = mount(LocalAuditSummary, {
      props: {
        audit: {
          transcriptComplete: true,
          unknowns: [
            {
              code: "COURSE_NOT_IN_CATALOG",
              field: null,
              message: "课程 SYN0901 不在课程库中，无法归入培养要求。",
              retryable: false,
            },
            {
              code: "PENDING_COURSE",
              field: null,
              message: "课程 SYN0902 尚未出成绩。",
              retryable: false,
            },
            {
              code: "UNMODELED_CURRICULUM_RULES",
              field: null,
              message: "本培养方案有 2 条规则系统未建模、不参与核验。",
              retryable: false,
            },
          ],
        },
        lookupName: (code: string) =>
          code === "SYN0902" ? "示例在读课程" : null,
      },
    });
    const items = wrapper.findAll(".local-audit-summary__list li");
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) expect(item.text().trim()).not.toBe("");
    expect(wrapper.text()).toContain("SYN0901");
    expect(wrapper.text()).toContain("示例在读课程 · SYN0902");
    expect(wrapper.text()).toContain("2 条培养方案规则需人工确认");
  });
});
