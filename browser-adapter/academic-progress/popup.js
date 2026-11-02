"use strict";

const message = document.getElementById("message");
const summary = document.getElementById("summary");
const download = document.getElementById("download");
let captured = null;

document.getElementById("read").addEventListener("click", async () => {
  captured = null;
  download.disabled = true;
  summary.hidden = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = new URL(tab.url);
    if (url.origin !== "https://jwxt.shu.edu.cn" || url.pathname !== "/jwglxt/xsxy/xsxyqk_cxXsxyqkIndex.html") {
      throw new Error("请先打开上海大学的学生学业情况查询页面。");
    }
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["extract.js"] });
    if (!result.categories.length) throw new Error("没有读取到学分汇总，请确认页面已加载并登录。");
    captured = result;
    const body = summary.querySelector("tbody");
    body.replaceChildren();
    for (const category of captured.categories) {
      const row = document.createElement("tr");
      for (const value of [category.name, category.requiredCredits, category.earnedCredits, category.remainingCredits]) {
        const cell = document.createElement("td");
        cell.textContent = String(value);
        row.append(cell);
      }
      body.append(row);
    }
    summary.hidden = false;
    download.disabled = false;
    message.textContent = `读取到 ${captured.categories.length} 个类别，请对照页面确认。`;
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : "读取失败，请重试。";
  }
});

download.addEventListener("click", () => {
  if (!captured) return;
  const blob = new Blob([JSON.stringify(captured, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "coursepilot-academic-progress.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
