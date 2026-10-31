import { expect, it } from "vitest";
import { reviewSourceLabel } from "./review-source";

it("显示可读来源并保留准确页行", () => {
  expect(reviewSourceLabel("faculty-pdf:p012:l005")).toBe(
    "计算机学院评价资料 · 第12页第5行",
  );
  expect(reviewSourceLabel("winter-pdf:2.4:p031-p032:l005-l013")).toBe(
    "冬季刊评价资料 · 第31–32页",
  );
  expect(reviewSourceLabel("other:ref")).toBe("评价来源资料");
});
