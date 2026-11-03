// 运行：node --test browser-adapter/academic-progress/extract.test.mjs
// 使用虚构 fixture（非真实成绩），验证各层类别节点与课程行都读到名称。
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import test from "node:test";

const require = createRequire(new URL("../../web/package.json", import.meta.url));
const { JSDOM } = require("jsdom");

const extractSource = await readFile(new URL("./extract.js", import.meta.url), "utf8");
const fixture = await readFile(new URL("./fixtures/synthetic-progress-tree.html", import.meta.url), "utf8");

function runExtractor(html) {
  const dom = new JSDOM(html, {
    url: "https://jwxt.shu.edu.cn/jwglxt/xsxy/xsxyqk_cxXsxyqkIndex.html",
    runScripts: "outside-only",
  });
  return dom.window.eval(extractSource);
}

test("每一层类别节点都读到名称并保留父子关系", () => {
  const payload = runExtractor(fixture);
  const byId = new Map(payload.nodes.map((node) => [node.schoolNodeId, node]));
  assert.equal(payload.nodes.length, 4);
  for (const node of payload.nodes) assert.notEqual(node.name, "", `节点 ${node.schoolNodeId} 名称为空`);
  assert.equal(byId.get("SYN-A").name, "示例主修类别");
  assert.equal(byId.get("SYN-A1").name, "示例子类别甲");
  assert.equal(byId.get("SYN-A1a").name, "示例孙类别");
  assert.equal(byId.get("SYN-A2").name, "示例子类别乙");
  assert.equal(byId.get("SYN-A1").parentId, byId.get("SYN-A").nodeId);
  assert.equal(byId.get("SYN-A1a").parentId, byId.get("SYN-A1").nodeId);
  assert.equal(byId.get("SYN-A1a").requiredCredits, 8);
  assert.equal(byId.get("SYN-A1a").earnedCredits, 2);
  assert.equal(byId.get("SYN-A1a").remainingCredits, 6);
});

test("每门课程行都有课程号与名称，状态按标签识别，无标签为 UNKNOWN", () => {
  const payload = runExtractor(fixture);
  assert.equal(payload.courses.length, 5);
  for (const course of payload.courses) {
    assert.notEqual(course.name, "", `${course.courseCode} 名称为空`);
    assert.match(course.courseCode, /^SYN000\d$/);
  }
  const outcome = Object.fromEntries(payload.courses.map((c) => [c.courseCode, c.outcome]));
  assert.deepEqual(outcome, {
    SYN0001: "PASSED",
    SYN0002: "NOT_TAKEN",
    SYN0003: "IN_PROGRESS",
    SYN0004: "UNKNOWN",
    SYN0005: "FAILED",
  });
  const names = Object.fromEntries(payload.courses.map((c) => [c.courseCode, c.name]));
  assert.equal(names.SYN0001, "示例课程一");
  assert.equal(names.SYN0005, "示例课程五");
});
