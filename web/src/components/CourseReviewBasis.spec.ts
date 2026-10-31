import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import CourseReviewBasis from "./CourseReviewBasis.vue";

const base = {
  courseCode: "CS101",
  reason: "课程目录列示为数据结构。",
  courseSourceRefIds: ["faculty-pdf:p2:l8"],
  rationaleSource: "COURSE_FACTS" as const,
  reviewNoteIds: [],
  reviewEvidenceRefs: [],
  reviewNotes: [],
};

describe("CourseReviewBasis", () => {
  it("shows course source and an explicit empty review basis", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: { ...base, reviewBasisStatus: "NO_RECORDS" },
    });
    expect(wrapper.text()).toContain("数据结构");
    expect(wrapper.text()).toContain("课程来源资料");
    expect(wrapper.text()).toContain("faculty-pdf:p2:l8");
    expect(wrapper.find("details").element.open).toBe(false);
    expect(wrapper.text()).toContain("暂无评价依据");
  });

  it("distinguishes reviews that were not queried", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: { ...base, reviewBasisStatus: "NOT_QUERIED" },
    });
    expect(wrapper.text()).toContain("未查询评价");
    expect(wrapper.text()).not.toContain("暂无评价依据");
  });

  it("does not infer query status for older responses", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: {
        ...base,
        reviewBasisStatus: null,
        rationaleSource: null,
      },
    });
    expect(wrapper.text()).toContain("评价依据状态未记录");
    expect(wrapper.text()).toContain("推荐依据");
  });

  it("shows cited review IDs and source references before excerpts are loaded", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: {
        ...base,
        reviewBasisStatus: "HAS_EVIDENCE",
        reviewNoteIds: ["review-1"],
        reviewEvidenceRefs: [
          { reviewNoteId: "review-1", sourceRefId: "winter-pdf:p3-p4:l8-l12" },
        ],
      },
    });
    expect(wrapper.text()).toContain("review-1");
    expect(wrapper.text()).toContain("winter-pdf:p3-p4:l8-l12");
    expect(wrapper.find("details").element.open).toBe(false);
    expect(wrapper.text()).not.toContain("评价原文尚未加载");
  });

  it("says a course has records when this rationale cites none", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: { ...base, reviewBasisStatus: "HAS_EVIDENCE" },
    });
    expect(wrapper.text()).toContain("该课程有评价记录，但本条理由未引用评价");
  });
});
