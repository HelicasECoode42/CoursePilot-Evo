(() => {
  if (document.getElementById("coursepilot-academic-export")) return;
  const host = document.createElement("div");
  host.id = "coursepilot-academic-export";
  for (const [property, value] of Object.entries({
    position: "fixed",
    right: "20px",
    bottom: "24px",
    left: "auto",
    top: "auto",
    "z-index": "2147483647",
    "max-width": "calc(100vw - 40px)",
  })) host.style.setProperty(property, value, "important");
  const root = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `:host{position:fixed;right:20px;bottom:24px;z-index:2147483647;font:14px system-ui,sans-serif;color:#20352b} button{border:0;border-radius:10px;background:#276b50;color:white;padding:10px 14px;cursor:pointer} .panel{background:white;border:1px solid #cae0d2;border-radius:12px;padding:16px;box-shadow:0 5px 24px #0003;width:330px;max-width:80vw;max-height:65vh;overflow:auto} .panel[hidden]{display:none} table{width:100%;border-collapse:collapse;margin:8px 0} th,td{text-align:left;padding:5px 2px;border-bottom:1px solid #e5ece7} .close{float:right;background:#edf3ef;color:#20352b}`;
  const button = document.createElement("button");
  button.textContent = "导出到 CoursePilot";
  const panel = document.createElement("section");
  panel.className = "panel";
  panel.hidden = true;
  const close = document.createElement("button");
  close.className = "close";
  close.textContent = "关闭";
  const title = document.createElement("h3");
  title.textContent = "学业进度汇总";
  const message = document.createElement("p");
  message.setAttribute("role", "status");
  const table = document.createElement("table");
  const courseTable = document.createElement("table");
  const download = document.createElement("button");
  download.textContent = "下载学业进度";
  const send = document.createElement("button");
  send.textContent = "导入 CoursePilot 并返回";
  let sending = false;
  send.addEventListener("click", async () => {
    if (sending) return;
    sending = true;
    send.disabled = true;
    try {
      const payload = globalThis.coursepilotReadAcademicProgress();
      if (!payload.nodes.length) throw new Error("没有读取到学业进度，请等待教务页面加载。");
      const response = await chrome.runtime.sendMessage({ type: "CP_SEND_PROGRESS", payload });
      if (!response?.ok) throw new Error(response?.error || "发送失败，请重试。");
      message.textContent = "已发送至 CoursePilot。";
    } catch (error) {
      message.textContent = error.message;
    } finally {
      sending = false;
      send.disabled = false;
    }
  });
  let captured = null;
  button.addEventListener("click", () => {
    captured = globalThis.coursepilotReadAcademicProgress();
    panel.hidden = false;
    button.hidden = true;
    table.replaceChildren();
    courseTable.replaceChildren();
    download.disabled = captured.nodes.length === 0;
    const unknownCount = captured.courses.filter((course) => course.outcome === "UNKNOWN").length;
    const nodeById = new Map(captured.nodes.map((node) => [node.nodeId, node]));
    const categoryPath = (nodeId) => {
      const path = [];
      let node = nodeById.get(nodeId);
      while (node) {
        path.push(node.schoolNodeId ? `${node.name}（${node.schoolNodeId}）` : node.name);
        node = node.parentId ? nodeById.get(node.parentId) : null;
      }
      return path.reverse().join(" / ");
    };
    message.textContent = captured.nodes.length
      ? `读取到 ${captured.nodes.length} 个类别节点和 ${captured.courses.length} 门课程；${unknownCount} 门课程状态未知。请核对后发送。`
      : "没有读取到学业进度，请等待页面加载后重试。";
    for (const values of [["类别", "要求", "已获", "未获"], ...captured.nodes.map((node) => [node.schoolNodeId ? `${node.name}（${node.schoolNodeId}）` : node.name, node.requiredCredits ?? "未知", node.earnedCredits ?? "未知", node.remainingCredits ?? "未知"])]) {
      const row = document.createElement("tr");
      values.forEach((value) => { const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell); });
      table.append(row);
    }
    for (const values of [["课程号", "课程名称", "类别", "状态", "学分"], ...captured.courses.map((course) => [course.courseCode, course.name, categoryPath(course.nodeId), course.outcome, course.credits ?? "未知"])]) {
      const row = document.createElement("tr");
      values.forEach((value) => { const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell); });
      courseTable.append(row);
    }
  });
  close.addEventListener("click", () => { panel.hidden = true; button.hidden = false; });
  download.addEventListener("click", () => {
    if (!captured) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(captured, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "coursepilot-academic-progress.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message.textContent = "已发起下载。请返回 CoursePilot，在导入窗口选择下载的文件。";
  });
  panel.append(close, title, message, table, courseTable, send, download);
  root.append(style, button, panel);
  document.documentElement.append(host);
})();
