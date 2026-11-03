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
    expect(wrapper.text()).toContain("本次规划未查询评价");
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

  it("asks the page to load review originals when the evidence details are opened", async () => {
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
    const details = wrapper
      .findAll("details")
      .find((d) => d.text().includes("查看评价原文"))!;
    expect(details.text()).toContain("展开后读取评价原文");
    details.element.open = true;
    await details.trigger("toggle");
    expect(wrapper.emitted("load")).toHaveLength(1);
  });

  it("shows why loading the originals failed, not a generic pending line", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: {
        ...base,
        reviewBasisStatus: "HAS_EVIDENCE",
        reviewNoteIds: ["review-1"],
        reviewEvidenceRefs: [
          { reviewNoteId: "review-1", sourceRefId: "winter-pdf:p3-p4:l8-l12" },
        ],
        reviewStatus: "error",
        reviewError: "暂时无法完成请求，请稍后重试。",
      },
    });
    expect(wrapper.text()).toContain("读取评价原文失败：暂时无法完成请求");
    expect(wrapper.text()).not.toContain("尚未加载");
  });

  it("says the originals were not found once a load has finished without them", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: {
        ...base,
        reviewBasisStatus: "HAS_EVIDENCE",
        reviewNoteIds: ["review-1"],
        reviewEvidenceRefs: [
          { reviewNoteId: "review-1", sourceRefId: "winter-pdf:p3-p4:l8-l12" },
        ],
        reviewStatus: "ready",
        reviewNotes: [],
      },
    });
    expect(wrapper.text()).toContain("评价库中没有找到这 1 条记录的原文");
  });

  it("shows the excerpt once the matching original is passed in", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: {
        ...base,
        reviewBasisStatus: "HAS_EVIDENCE",
        reviewNoteIds: ["review-1"],
        reviewEvidenceRefs: [
          { reviewNoteId: "review-1", sourceRefId: "winter-pdf:p3-p4:l8-l12" },
        ],
        reviewStatus: "ready",
        reviewNotes: [
          {
            reviewNoteId: "review-1",
            courseCode: "CS101",
            teacherKey: null,
            termId: null,
            sourceKind: "SYNTHETIC",
            publishedAt: null,
            sourceUrl: null,
            excerpt: "示例评价原文（虚构）",
            dimensions: ["WORKLOAD"],
            matchStatus: "COURSE_ONLY",
            sourceRefId: "winter-pdf:p3-p4:l8-l12",
          },
        ],
      },
    });
    expect(wrapper.text()).toContain("示例评价原文（虚构）");
  });
});

describe("CourseReviewBasis review items", () => {
  it("shows each glued review as its own item with teacher name", () => {
    const wrapper = mount(CourseReviewBasis, {
      props: {
        ...base,
        reviewBasisStatus: "HAS_EVIDENCE",
        reviewNoteIds: ["review-glued"],
        reviewEvidenceRefs: [
          {
            reviewNoteId: "review-glued",
            sourceRefId: "faculty-pdf:p010:l014",
          },
        ],
        reviewNotes: [
          {
            reviewNoteId: "review-glued",
            courseCode: "CS101",
            teacherKey: null,
            teacherDisplayName: "张三",
            termId: null,
            sourceKind: "USER_IMPORT",
            publishedAt: null,
            sourceUrl: null,
            excerpt: "第一条评价。Ⅱ第二条评价。",
            dimensions: ["OVERALL"],
            matchStatus: "UNVERIFIED",
            sourceRefId: "faculty-pdf:p010:l014",
          },
        ],
      },
    });
    const items = wrapper.findAll('[aria-label="评价证据"] > li');
    expect(items).toHaveLength(2);
    expect(items[0]!.text()).toContain("来源标注：张三（未核实）");
    expect(items[0]!.text()).toContain("第一条评价。");
    expect(items[1]!.text()).toContain("第二条评价。");
    expect(wrapper.text()).not.toContain("Ⅱ");
  });
});
