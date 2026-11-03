import { describe, expect, it } from "vitest";
import type { ReviewNote } from "../contracts";
import {
  expandReviewItems,
  splitReviewExcerpt,
  termPrefixLabel,
  UNNAMED_TEACHER_LABEL,
} from "./review-items";

const note = (overrides: Partial<ReviewNote>): ReviewNote => ({
  reviewNoteId: "review:faculty:p010:l014:08305008",
  courseCode: "08305008",
  teacherKey: null,
  teacherDisplayName: "张三",
  termId: null,
  sourceKind: "USER_IMPORT",
  publishedAt: null,
  sourceUrl: null,
  excerpt: "上课有点催眠。",
  dimensions: ["OVERALL"],
  matchStatus: "UNVERIFIED",
  sourceRefId: "faculty-pdf:p010:l014",
  ...overrides,
});

describe("splitReviewExcerpt", () => {
  it("splits glued reviews on the Ⅱ separator and drops OCR artifacts", () => {
    const parts = splitReviewExcerpt(
      "上课有点催眠，作业管的不紧。Ⅱ水水水ⅡI 老师挺好说话的，但是课讲的不太清楚。Ⅱ水中贵族，如果你是 游泳健将，选他Ⅱ巨 水，选的话建议自学口Ⅱ",
    );
    expect(parts).toEqual([
      "上课有点催眠，作业管的不紧。",
      "水水水",
      "老师挺好说话的，但是课讲的不太清楚。",
      "水中贵族，如果你是游泳健将，选他",
      "巨水，选的话建议自学",
    ]);
  });

  it("splits on 丨 and 』 too, and keeps text without separators whole", () => {
    expect(
      splitReviewExcerpt(
        "神神叨叨，课上基本上就是创业小故事和元宇宙丨给 分还行",
      ),
    ).toEqual(["神神叨叨，课上基本上就是创业小故事和元宇宙", "给分还行"]);
    expect(splitReviewExcerpt("实验累点..』作业的蛮多的")).toEqual([
      "实验累点..",
      "作业的蛮多的",
    ]);
    expect(splitReviewExcerpt("普通的一条评价 with English")).toEqual([
      "普通的一条评价 with English",
    ]);
  });

  it("does not remove spaces between Latin words or numbers", () => {
    expect(splitReviewExcerpt("Python 作业 8587 分")).toEqual([
      "Python 作业 8587 分",
    ]);
  });
});

describe("termPrefixLabel", () => {
  it("maps contract term ids to the booklet prefix", () => {
    expect(termPrefixLabel("2022-2023-1")).toBe("22-秋");
    expect(termPrefixLabel("2022-2023-2")).toBe("23-春");
    expect(termPrefixLabel(null)).toBe("");
    expect(termPrefixLabel("2022-2023-9")).toBe("");
  });
});

describe("expandReviewItems", () => {
  it("shows bound teachers by name and unbound names as unverified mentions", () => {
    const [bound] = expandReviewItems([
      note({ teacherKey: "T001", excerpt: "好。" }),
    ]);
    expect(bound!.teacherLabel).toBe("张三");
  });

  it("returns one item per segment with teacher label and term", () => {
    const items = expandReviewItems([
      note({ excerpt: "第一条。Ⅱ第二条评价。", termId: "2022-2023-1" }),
      note({
        reviewNoteId: "review:x",
        teacherDisplayName: null,
        excerpt: "无老师名的一条",
      }),
    ]);
    expect(
      items.map((item) => [item.teacherLabel, item.termPrefix, item.text]),
    ).toEqual([
      ["来源标注：张三（未核实）", "22-秋", "第一条。"],
      ["来源标注：张三（未核实）", "22-秋", "第二条评价。"],
      [UNNAMED_TEACHER_LABEL, "", "无老师名的一条"],
    ]);
    expect(new Set(items.map((item) => item.key)).size).toBe(3);
  });
});
