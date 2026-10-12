import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const require = createRequire(new URL("../web/package.json", import.meta.url));
const { JSDOM } = require("jsdom");
const htmlUrl = new URL("./coursepilot-guided-demo.html", import.meta.url);
const html = await readFile(htmlUrl, "utf8");
const flowSource = html.match(
  /\/\/ BEGIN coursepilot-demo-flow([\s\S]*?)\/\/ END coursepilot-demo-flow/,
);
assert.ok(flowSource, "demo flow source markers exist");

function createFlow() {
  const context = {};
  runInNewContext(
    `${flowSource[1]}\nglobalThis.testApi = { state, routeFor, setMotives, movePriority, advanceFlow, backFlow, applySlot, toggleSlot, toggleLine, dayKeys, periodKeys, summarizeSlots, setMajor, setCareerOther, directions };`,
    context,
  );
  return context.testApi;
}

test("the schedule step is always present and keeps must and prefer slots independently", () => {
  const { state, routeFor, setMotives, advanceFlow, backFlow } = createFlow();
  setMotives(["time", "career"]);
  assert.deepEqual(Array.from(state.route), [
    "goals",
    "preferences",
    "career",
    "interest",
    "teachers",
    "time",
    "priorities",
    "materials",
    "result",
  ]);
  state.index = state.route.indexOf("time");
  state.mustSlots.push("1-1");
  state.preferSlots.push("2-3");

  assert.equal(advanceFlow().ok, true);
  assert.equal(state.mustReviewed, true);
  assert.equal(state.preferReviewed, true);
  assert.deepEqual(Array.from(state.mustSlots), ["1-1"]);
  assert.deepEqual(Array.from(state.preferSlots), ["2-3"]);
  assert.equal(backFlow(), "time");
  assert.deepEqual(Array.from(state.mustSlots), ["1-1"]);
  assert.deepEqual(Array.from(state.preferSlots), ["2-3"]);
});

test("removing a goal keeps its branch answers, and reselecting it finds them still there", () => {
  const { state, setMotives } = createFlow();
  setMotives(["time", "career", "interest", "gpa", "teacher"]);
  state.mustSlots = ["2-1"];
  state.preferSlots = ["3-5"];
  state.mustReviewed = true;
  state.preferReviewed = true;
  state.career = ["backend"];
  state.interest = "机器人";
  state.preferences = ["homework"];
  state.preferencesReviewed = true;
  state.pinnedPair = "a";
  setMotives(["gpa", "interest"]);

  assert.deepEqual(Array.from(state.mustSlots), ["2-1"]);
  assert.deepEqual(Array.from(state.preferSlots), ["3-5"]);
  assert.equal(state.mustReviewed, true);
  assert.equal(state.preferReviewed, true);
  assert.deepEqual(Array.from(state.career), ["backend"]);
  assert.equal(state.pinnedPair, "a");
  assert.equal(state.interest, "机器人");
  assert.deepEqual(Array.from(state.preferences), ["homework"]);
  assert.equal(state.preferencesReviewed, true);

  setMotives(["interest"]);
  assert.deepEqual(Array.from(state.preferences), ["homework"]);
  assert.equal(state.preferencesReviewed, true);

  setMotives(["gpa", "interest", "time", "career", "teacher"]);
  assert.deepEqual(Array.from(state.mustSlots), ["2-1"]);
  assert.deepEqual(Array.from(state.preferSlots), ["3-5"]);
  assert.deepEqual(Array.from(state.career), ["backend"]);
  assert.equal(state.pinnedPair, "a");
});

test("routeFor returns the full nine-step route whatever goals are selected", () => {
  const { routeFor, setMotives, state } = createFlow();
  const full = [
    "goals",
    "preferences",
    "career",
    "interest",
    "teachers",
    "time",
    "priorities",
    "materials",
    "result",
  ];
  assert.deepEqual(Array.from(routeFor([])), full);
  assert.deepEqual(Array.from(routeFor(["gpa"])), full);
  assert.deepEqual(Array.from(routeFor(["time", "teacher", "interest"])), full);
  setMotives(["easy"]);
  assert.deepEqual(Array.from(state.route), full);
});

test("goal changes only reorder selected goals and require priority reconfirmation", () => {
  const { state, setMotives } = createFlow();
  setMotives(["time", "career", "interest", "gpa", "teacher"]);
  state.prioritiesConfirmed = true;
  setMotives(["gpa", "interest"]);
  assert.deepEqual(Array.from(state.priorityOrder), ["interest", "gpa"]);
  assert.equal(state.prioritiesConfirmed, false);

  state.prioritiesConfirmed = true;
  setMotives(["gpa", "interest", "time"]);
  assert.deepEqual(Array.from(state.priorityOrder), ["interest", "gpa", "time"]);
  assert.equal(state.prioritiesConfirmed, false);
});

test("priority and demonstration data each require an explicit confirmation", () => {
  const { state, routeFor, setMotives, advanceFlow } = createFlow();
  setMotives(["gpa"]);
  state.route = routeFor();
  state.index = state.route.indexOf("priorities");

  const unconfirmedPriority = advanceFlow();
  assert.equal(unconfirmedPriority.ok, false);
  assert.equal(unconfirmedPriority.message, "请检查目标顺序并勾选确认。");
  assert.equal(state.index, state.route.indexOf("priorities"));
  state.prioritiesConfirmed = true;
  assert.equal(advanceFlow().ok, true);
  assert.equal(state.route[state.index], "materials");

  const unconfirmedDemo = advanceFlow();
  assert.equal(unconfirmedDemo.ok, false);
  assert.equal(
    unconfirmedDemo.message,
    "如要查看候选，请先确认只使用虚构示例资料。",
  );
  assert.equal(state.route[state.index], "materials");
  state.demoAcknowledged = true;
  assert.equal(advanceFlow().ok, true);
  assert.equal(state.route[state.index], "result");
});

test("changing the selected order requires priority confirmation again", () => {
  const { state, setMotives, movePriority } = createFlow();
  setMotives(["gpa", "career"]);
  state.prioritiesConfirmed = true;
  movePriority(1, -1);
  assert.deepEqual(Array.from(state.priorityOrder), ["career", "gpa"]);
  assert.equal(state.prioritiesConfirmed, false);
});

test("the HTML labels synthetic materials, withholds real planning and provides a working details entry", () => {
  assert.match(html, /coursepilot-demo-flow/);
  assert.match(html, /虚构示例资料/);
  assert.match(html, /不能生成真实规划/);
  assert.match(html, /data-action="academic"/);
  assert.match(html, /查看需要补充什么/);
  assert.match(html, /function openAcademicInfo\(\)/);
  assert.match(html, /data-review=/);
  assert.match(html, /aria-modal="true"/);
  assert.doesNotMatch(html, /<script\s+src=/i);
});

// Clicks "next" until the given page label is shown (every page is always in the route).
function advanceTo(document, phaseLabel) {
  for (let i = 0; i < 12; i += 1) {
    if (document.getElementById("phase").textContent === phaseLabel) return;
    const confirm = document.getElementById("priorityConfirm");
    if (confirm) confirm.click();
    document.getElementById("next").click();
  }
  assert.equal(document.getElementById("phase").textContent, phaseLabel);
}

function openTeacherReview() {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    beforeParse(window) {
      window.scrollTo = () => {};
    },
  });
  const { document } = dom.window;
  document
    .querySelector('[data-group="motives"][data-value="teacher"]')
    .click();
  advanceTo(document, "课程和教师");
  const reviewButton = document.querySelector('[data-review="a"]');
  reviewButton.focus();
  reviewButton.click();
  return { dom, document, reviewButton };
}

test("closing a detail restores focus to the stable source after the question is re-rendered", () => {
  const closePaths = [
    ["close button", (document) => document.getElementById("close").click()],
    ["backdrop", (document) => document.getElementById("detail").click()],
    [
      "Escape",
      (document, window) =>
        document.getElementById("detail").dispatchEvent(
          new window.KeyboardEvent("keydown", {
            key: "Escape",
            bubbles: true,
          }),
        ),
    ],
    [
      "dialog pin",
      (document) => document.querySelector('[data-dialogpin="a"]').click(),
    ],
  ];

  for (const [name, close] of closePaths) {
    const { dom, document, reviewButton } = openTeacherReview();
    close(document, dom.window);
    const restoredReviewButton = document.querySelector('[data-review="a"]');

    assert.notEqual(
      restoredReviewButton,
      reviewButton,
      `${name} re-renders the source button`,
    );
    assert.equal(
      document.getElementById("detail").hidden,
      true,
      `${name} closes the detail`,
    );
    assert.equal(
      document.activeElement,
      restoredReviewButton,
      `${name} restores source focus`,
    );
    if (name === "dialog pin") {
      assert.equal(
        document.querySelector('[data-pin="a"]').getAttribute("aria-pressed"),
        "true",
      );
    }
    dom.window.close();
  }
});

test("closing academic record details returns focus to its persistent header button", () => {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    beforeParse(window) {
      window.scrollTo = () => {};
    },
  });
  const { document } = dom.window;
  const recordButton = document.getElementById("recordBtn");
  recordButton.focus();
  recordButton.click();
  document.getElementById("close").click();

  assert.equal(document.activeElement, recordButton);
  assert.equal(document.getElementById("detail").hidden, true);
  dom.window.close();
});

test("a slot belongs to at most one intensity and a click applies the current intensity", () => {
  const { state, applySlot, toggleSlot } = createFlow();
  state.slotMode = "must";
  toggleSlot("1-1");
  assert.deepEqual(Array.from(state.mustSlots), ["1-1"]);
  assert.deepEqual(Array.from(state.preferSlots), []);

  state.slotMode = "prefer";
  toggleSlot("1-1");
  assert.deepEqual(Array.from(state.mustSlots), []);
  assert.deepEqual(Array.from(state.preferSlots), ["1-1"]);

  applySlot("1-1", "paint", "must");
  assert.deepEqual(Array.from(state.mustSlots), ["1-1"]);
  assert.deepEqual(Array.from(state.preferSlots), []);

  toggleSlot("1-1");
  assert.deepEqual(Array.from(state.preferSlots), ["1-1"]);
  assert.deepEqual(Array.from(state.mustSlots), []);
  toggleSlot("1-1");
  assert.deepEqual(Array.from(state.preferSlots), []);
  assert.deepEqual(Array.from(state.mustSlots), []);
});

test("column selection fills all twelve periods in the current intensity and clears them when full", () => {
  const { state, toggleLine, dayKeys } = createFlow();
  state.slotMode = "must";
  state.preferSlots = ["3-1"];
  const column = dayKeys(3);
  assert.equal(column.length, 12);

  toggleLine(column);
  assert.deepEqual(Array.from(state.mustSlots), Array.from(column));
  assert.deepEqual(Array.from(state.preferSlots), []);

  toggleLine(column);
  assert.deepEqual(Array.from(state.mustSlots), []);
  assert.deepEqual(Array.from(state.preferSlots), []);
});

test("summaries merge full days and full periods and keep scattered cells", () => {
  const { summarizeSlots, dayKeys, periodKeys } = createFlow();
  assert.equal(summarizeSlots([]), "未设置");
  assert.equal(summarizeSlots(dayKeys(1)), "周一（整天）");
  assert.equal(summarizeSlots(periodKeys(1)), "每天第1节");
  assert.equal(summarizeSlots(["1-2", "3-4"]), "周一 第2节、周三 第4节");
  assert.equal(summarizeSlots([...dayKeys(1), ...periodKeys(1)]), "周一（整天）、每天第1节");
});

test("summaries compress consecutive days and periods into ranges", () => {
  const { summarizeSlots, dayKeys, periodKeys } = createFlow();
  const cells = (days, periods) =>
    days.flatMap((day) => periods.map((period) => `${day}-${period}`));
  assert.equal(summarizeSlots([]), "未设置");
  assert.equal(summarizeSlots(dayKeys(1)), "周一（整天）");
  assert.equal(summarizeSlots(periodKeys(1)), "每天第1节");
  assert.equal(summarizeSlots(cells([1, 2, 3, 4, 5], [1, 2])), "周一至周五 第1–2节");
  assert.equal(summarizeSlots(cells([2], [3])), "周二 第3节");
  assert.equal(summarizeSlots(cells([1, 4], [2])), "周一、周四 第2节");
  assert.equal(summarizeSlots(cells([3], [1, 3])), "周三 第1、3节");
  assert.equal(summarizeSlots(cells([1, 2, 3, 6], [2])), "周一至周三、周六 第2节");
  assert.equal(summarizeSlots(cells([1, 2, 3], [1, 2, 3, 5])), "周一至周三 第1–3节、第5节");
  assert.equal(summarizeSlots(cells([1, 2, 3], [1, 2, 3, 5])), "周一至周三 第1–3节、第5节");
});


test("materials summary keeps a chosen but empty interest row", () => {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    beforeParse(window) {
      window.scrollTo = () => {};
    },
  });
  const { document } = dom.window;
  const clickNext = () => document.getElementById("next").click();
  document.querySelector('[data-group="motives"][data-value="interest"]').click();
  for (let i = 0; i < 10; i += 1) {
    if (document.querySelector("dl.summary")) break;
    const confirm = document.getElementById("priorityConfirm");
    if (confirm) confirm.click();
    clickNext();
  }
  const text = document.querySelector("dl.summary").textContent;
  assert.match(text, /兴趣主题/);
  assert.match(text, /这一项留空了/);
  dom.window.close();
});

test("removing the time goal keeps both intensity groups and their review flags", () => {
  const { state, setMotives } = createFlow();
  setMotives(["time", "gpa"]);
  state.mustSlots = ["1-1"];
  state.preferSlots = ["2-2"];
  state.mustReviewed = true;
  state.preferReviewed = true;

  setMotives(["gpa"]);
  assert.deepEqual(Array.from(state.mustSlots), ["1-1"]);
  assert.deepEqual(Array.from(state.preferSlots), ["2-2"]);
  assert.equal(state.mustReviewed, true);
  assert.equal(state.preferReviewed, true);
});

function openDemo() {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    beforeParse(window) {
      window.scrollTo = () => {};
    },
  });
  return { dom, document: dom.window.document };
}

// Clicks through every page until the materials summary appears; returns the pages passed before it.
function walkToMaterials(document) {
  const passed = [];
  for (let i = 0; i < 12; i += 1) {
    if (document.querySelector("dl.summary")) break;
    passed.push(document.getElementById("phase").textContent);
    const confirm = document.getElementById("priorityConfirm");
    if (confirm) confirm.click();
    document.getElementById("next").click();
  }
  assert.equal(document.getElementById("phase").textContent, "核对学业资料");
  return passed;
}

test("a student with one goal passes every page and sees blank rows in the materials summary", () => {
  const { dom, document } = openDemo();
  document.querySelector('[data-group="motives"][data-value="gpa"]').click();
  const passed = walkToMaterials(document);
  assert.deepEqual(passed, [
    "这学期的想法",
    "上课与考核偏好",
    "了解发展方向",
    "想探索的主题",
    "课程和教师",
    "时间安排",
    "确认目标顺序",
  ]);

  const rows = [...document.querySelectorAll("dl.summary .summary-row")];
  const rowText = (label) =>
    rows.find((row) => row.querySelector("dt").textContent === label)?.textContent ?? "";
  assert.match(rowText("上课与考核偏好"), /这一项留空了/);
  assert.match(rowText("兴趣主题"), /这一项留空了/);
  assert.match(rowText("职业方向"), /这一项留空了/);
  assert.match(rowText("课程与教师"), /尚未选择具体课程与教师/);
  assert.match(rowText("目标与顺序"), /想拿高绩点/);
  dom.window.close();
});

test("materials and result summaries never use the old skipped-branch wording", () => {
  const { dom, document } = openDemo();
  for (const value of ["gpa", "interest", "career", "teacher", "time"]) {
    document.querySelector(`[data-group="motives"][data-value="${value}"]`).click();
  }
  walkToMaterials(document);
  const forbidden = /未选择此目标|未填写|暂未填写/;
  assert.doesNotMatch(document.querySelector("dl.summary").textContent, forbidden);

  document.getElementById("demoConsent").click();
  document.getElementById("next").click();
  assert.equal(document.getElementById("phase").textContent, "虚构演示候选");
  assert.doesNotMatch(document.querySelector("dl.summary").textContent, forbidden);
  assert.match(document.querySelector("dl.summary").textContent, /课程与教师/);
  dom.window.close();
});

function openTimePage() {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    beforeParse(window) {
      window.scrollTo = () => {};
    },
  });
  const { document } = dom.window;
  document.querySelector('[data-group="motives"][data-value="time"]').click();
  advanceTo(document, "时间安排");
  return { dom, document, window: dom.window };
}

const slotCell = (document, key) => document.querySelector(`[data-slot="${key}"]`);

test("the time page renders a labelled 7 by 12 grid of buttons without per-cell ids", () => {
  const { dom, document } = openTimePage();
  const group = document.querySelector(
    '[role="group"][aria-label="按星期和节次选择要避开的时段"]',
  );
  assert.ok(group, "grid group exists");
  assert.equal(group.querySelectorAll("[data-slot]").length, 84);
  assert.equal(group.querySelectorAll("[data-col]").length, 7);
  assert.equal(group.querySelectorAll("[data-row]").length, 12);

  const cell = slotCell(document, "1-1");
  assert.equal(cell.tagName, "BUTTON");
  assert.equal(cell.getAttribute("type"), "button");
  assert.equal(cell.getAttribute("aria-pressed"), "false");
  assert.equal(cell.getAttribute("aria-label"), "周一 第1节 未选择");
  assert.equal(cell.id, "");
  assert.equal(
    document.querySelector('[data-col="1"]').getAttribute("aria-label"),
    "整列选择 周一",
  );
  assert.match(html, /\.slotgrid\{[^}]*touch-action:none/);
  assert.match(html, /\.slotgrid\{[^}]*user-select:none/);
  dom.window.close();
});

test("dragging paints crossed cells in the mode chosen at pointerdown and stops at pointerup", () => {
  const { dom, document, window } = openTimePage();
  const fire = (target, type) => target.dispatchEvent(new window.Event(type, { bubbles: true }));
  const isMust = (key) => slotCell(document, key).classList.contains("is-must");

  fire(slotCell(document, "1-1"), "pointerdown");
  fire(slotCell(document, "1-2"), "pointerover");
  fire(slotCell(document, "1-3"), "pointerover");
  document.dispatchEvent(new window.Event("pointerup", { bubbles: true }));
  fire(slotCell(document, "1-4"), "pointerover");
  assert.equal(isMust("1-1"), true);
  assert.equal(isMust("1-2"), true);
  assert.equal(isMust("1-3"), true);
  assert.equal(isMust("1-4"), false);

  fire(slotCell(document, "1-1"), "pointerdown");
  fire(slotCell(document, "1-2"), "pointerover");
  document.dispatchEvent(new window.Event("pointerup", { bubbles: true }));
  assert.equal(isMust("1-1"), false);
  assert.equal(isMust("1-2"), false);
  assert.equal(isMust("1-3"), true);
  dom.window.close();
});

test("mode switch keeps existing picks and a click on the other intensity moves the cell", () => {
  const { dom, document } = openTimePage();
  const pressed = (key) => slotCell(document, key).getAttribute("aria-pressed");
  const mustButton = document.querySelector('[data-slotmode="must"]');
  const preferButton = document.querySelector('[data-slotmode="prefer"]');

  slotCell(document, "1-1").click();
  preferButton.click();
  assert.equal(preferButton.getAttribute("aria-pressed"), "true");
  assert.equal(mustButton.getAttribute("aria-pressed"), "false");
  assert.equal(slotCell(document, "1-1").classList.contains("is-must"), true);

  slotCell(document, "1-1").click();
  assert.equal(slotCell(document, "1-1").classList.contains("is-prefer"), true);
  assert.equal(slotCell(document, "1-1").classList.contains("is-must"), false);

  slotCell(document, "1-1").click();
  assert.equal(pressed("1-1"), "false");
  assert.equal(slotCell(document, "1-1").getAttribute("aria-label"), "周一 第1节 未选择");
  dom.window.close();
});

test("header buttons select a whole day or period and clear it when it is already full", () => {
  const { dom, document } = openTimePage();
  const pressedCount = () => document.querySelectorAll('[data-slot][aria-pressed="true"]').length;

  document.querySelector('[data-col="2"]').click();
  assert.equal(pressedCount(), 12);
  assert.equal(slotCell(document, "2-12").classList.contains("is-must"), true);
  document.querySelector('[data-col="2"]').click();
  assert.equal(pressedCount(), 0);

  document.querySelector('[data-row="5"]').click();
  assert.equal(pressedCount(), 7);
  dom.window.close();
});

test("switching major clears the chosen directions and keeps the free-text entry", () => {
  const { state, setMajor, setCareerOther } = createFlow();
  state.career = ["backend"];
  setCareerOther("教育科技");
  assert.equal(setMajor("自动化与电气"), true);
  assert.equal(state.major, "自动化与电气");
  assert.deepEqual(Array.from(state.career), []);
  assert.equal(state.careerOther, "教育科技");
  assert.equal(setMajor("不存在的专业"), false);
  assert.equal(state.major, "自动化与电气");
});

test("every major offers exactly four direction groups with complete text", () => {
  const { directions } = createFlow();
  assert.deepEqual(Object.keys(directions), ["计算机科学与技术", "自动化与电气", "机械类", "经管与财会"]);
  for (const [major, items] of Object.entries(directions)) {
    assert.equal(items.length, 4, `${major} has four direction groups`);
    assert.equal(new Set(items.map((item) => item[0])).size, 4, `${major} ids are unique`);
    for (const item of items) {
      assert.equal(item.length, 4, `${item[0]} has id, title, summary and detail`);
      assert.ok(item.every((value) => typeof value === "string" && value.trim()), `${item[0]} has no empty field`);
    }
  }
});

test("the picker lists four majors, each showing four direction buttons, and switching clears the selection", () => {
  const { dom, document } = openDemo();
  document.querySelector('[data-group="motives"][data-value="gpa"]').click();
  advanceTo(document, "了解发展方向");
  document.querySelector('[data-group="career"][data-value="backend"]').click();
  assert.equal(document.querySelector('[data-group="career"][data-value="backend"]').getAttribute("aria-pressed"), "true");

  const majors = [...document.querySelectorAll("#major option")].map((option) => option.value);
  assert.equal(majors.length, 4);
  for (const major of majors) {
    const select = document.getElementById("major");
    select.value = major;
    select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
    assert.equal(document.getElementById("major").value, major);
    assert.equal(document.querySelectorAll('[data-group="career"]').length, 4, major);
    if (major !== "计算机科学与技术") {
      assert.equal(document.querySelectorAll('[data-group="career"][aria-pressed="true"]').length, 0, `${major} starts with nothing chosen`);
    }
  }
  dom.window.close();
});

test("free-text career entry is escaped and appears in the materials summary", () => {
  const { dom, document } = openDemo();
  document.querySelector('[data-group="motives"][data-value="gpa"]').click();
  advanceTo(document, "了解发展方向");
  const input = document.getElementById("careerOther");
  input.value = "<i>教育科技</i>";
  input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  walkToMaterials(document);
  const row = [...document.querySelectorAll("dl.summary .summary-row")].find(
    (item) => item.querySelector("dt").textContent === "职业方向",
  );
  assert.match(row.textContent, /<i>教育科技<\/i>/);
  assert.equal(row.querySelector("i"), null);
  dom.window.close();
});

test("the career row says blank only when no direction and no free text is given, on both summaries", () => {
  const { dom, document } = openDemo();
  document.querySelector('[data-group="motives"][data-value="gpa"]').click();
  advanceTo(document, "了解发展方向");
  document.querySelector('[data-group="career"][data-value="backend"]').click();
  walkToMaterials(document);
  const careerRowText = () =>
    [...document.querySelectorAll("dl.summary .summary-row")].find(
      (item) => item.querySelector("dt").textContent === "职业方向",
    )?.textContent ?? "";
  assert.match(careerRowText(), /后端与业务系统/);
  assert.doesNotMatch(careerRowText(), /这一项留空了/);

  document.getElementById("demoConsent").click();
  document.getElementById("next").click();
  assert.equal(document.getElementById("phase").textContent, "虚构演示候选");
  assert.match(careerRowText(), /后端与业务系统/);
  dom.window.close();

  const blank = openDemo();
  blank.document.querySelector('[data-group="motives"][data-value="gpa"]').click();
  walkToMaterials(blank.document);
  const blankRow = [...blank.document.querySelectorAll("dl.summary .summary-row")].find(
    (item) => item.querySelector("dt").textContent === "职业方向",
  );
  assert.match(blankRow.textContent, /这一项留空了/);
  blank.dom.window.close();
});
