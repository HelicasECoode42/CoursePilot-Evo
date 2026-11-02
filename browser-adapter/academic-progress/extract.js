globalThis.coursepilotReadAcademicProgress = () => {
  const textOf = (element) => (element?.textContent || "").replace(/\s+/g, " ").trim();
  const pattern = /([\s\S]{1,100}?)\s*要求学分\s*[:：]\s*(\d+(?:\.\d+)?)\s*获得学分\s*[:：]\s*(\d+(?:\.\d+)?)\s*未获得学分\s*[:：]\s*(\d+(?:\.\d+)?)/;
  const tree = document.querySelector("ul.treeview");
  const nodes = tree ? [...tree.querySelectorAll("li")].filter((li) => li.querySelector(":scope > .title")) : [];
  const ids = new Map(nodes.map((node, index) => [node, `node-${index + 1}`]));
  const categories = [];
  const courses = [];
  const number = (text) => /^\d+(?:\.\d+)?$/.test(text) ? Number(text) : null;
  const outcomeByLegend = new Map();
  const statusLabel = new Map([["已修", "PASSED"], ["在修", "IN_PROGRESS"], ["未修", "NOT_TAKEN"], ["未过", "FAILED"]]);
  const iconSignature = (element) => {
    if (!element) return "";
    const parts = [element, ...element.querySelectorAll("i, span, img, svg, [class*='icon']")]
      .filter((item) => item.matches("i, span, img, svg, [class*='icon']") && (item.getAttribute("class") || item.getAttribute("src")))
      .map((item) => {
        const tag = item.tagName.toLowerCase();
        const classes = [...item.classList].sort().join(".");
        const src = item.getAttribute("src");
        return `${tag}:${classes}:${src ? new URL(src, location.href).pathname : ""}`;
      })
      .sort();
    return parts.join("|");
  };
  for (const element of document.querySelectorAll("body *")) {
    const label = textOf(element);
    const outcome = statusLabel.get(label);
    if (!outcome) continue;
    let candidate = element;
    for (let depth = 0; depth < 3 && candidate; depth += 1) {
      if (textOf(candidate) !== label) break;
      const signature = iconSignature(candidate);
      if (signature) {
        if (outcomeByLegend.has(signature) && outcomeByLegend.get(signature) !== outcome) outcomeByLegend.set(signature, "UNKNOWN");
        else outcomeByLegend.set(signature, outcome);
        break;
      }
      candidate = candidate.parentElement;
    }
  }
  for (const node of nodes) {
    const title = node.querySelector(":scope > .title");
    const label = title.querySelector(".title1") || title;
    const match = textOf(label).match(pattern);
    const nodeId = ids.get(node);
    const parent = node.parentElement?.closest("li");
    categories.push({
      nodeId,
      parentId: ids.get(parent) || null,
      schoolNodeId: node.getAttribute("xfyqjd_id") || null,
      leaf: /^(true|1|yes)$/i.test(node.getAttribute("leaf") || ""),
      name: match ? match[1] : textOf(label).split(/共[（(]/)[0].trim(),
      requiredCredits: match ? Number(match[2]) : null,
      earnedCredits: match ? Number(match[3]) : null,
      remainingCredits: match ? Number(match[4]) : null,
    });
    for (const table of node.querySelectorAll("table")) {
      if (table.closest("li") !== node) continue;
      const headers = [...table.querySelectorAll("thead th")].map(textOf);
      const index = (name) => headers.indexOf(name);
      if (index("课程号") < 0 || index("课程名称") < 0) continue;
      for (const row of table.querySelectorAll("tbody tr")) {
        const cells = [...row.cells];
        const value = (name) => textOf(cells[index(name)]);
        const courseCode = value("课程号");
        if (!courseCode) continue;
        const statusCell = cells[index("修读状态")];
        const statusText = [textOf(statusCell), ...[...(statusCell?.querySelectorAll("[title], [aria-label], img[alt]") || [])].map((e) => e.getAttribute("title") || e.getAttribute("aria-label") || e.getAttribute("alt"))].join(" ");
        // Icon signatures are accepted only when the page legend uniquely labels them.
        let outcome = /未过|未通过/.test(statusText) ? "FAILED" : /在修|在读/.test(statusText) ? "IN_PROGRESS" : /已修|已通过/.test(statusText) ? "PASSED" : /未修/.test(statusText) ? "NOT_TAKEN" : "UNKNOWN";
        if (outcome === "UNKNOWN") {
          const signature = iconSignature(statusCell);
          outcome = signature ? (outcomeByLegend.get(signature) || "UNKNOWN") : "UNKNOWN";
        }
        courses.push({ nodeId, courseCode, name: value("课程名称"), credits: number(value("学分")), outcome, completedYear: value("成绩学年") || null, completedTerm: value("学期") || null, grade: value("成绩") || null, makeup: value("补考") || null, retake: value("重修") || null, suggestedYear: value("建议修读学年") || null, suggestedTerm: value("建议修读学期") || null });
      }
    }
  }
  if (!tree) {
    const seen = new Set();
    for (const element of document.querySelectorAll("div, span, li, p")) {
      const text = textOf(element);
      if ([...element.children].some((child) => pattern.test(textOf(child)))) continue;
      const match = text.match(pattern);
      if (!match) continue;
      const item = { name: match[1], requiredCredits: Number(match[2]), earnedCredits: Number(match[3]), remainingCredits: Number(match[4]) };
      const key = JSON.stringify(item);
      if (seen.has(key)) continue;
      seen.add(key);
      categories.push({ nodeId: `node-${categories.length + 1}`, parentId: null, schoolNodeId: null, leaf: true, ...item });
    }
  }
  const uniqueCourses = [...new Map(courses.map((course) => [JSON.stringify(course), course])).values()];
  return { format: "coursepilot-shu-academic-progress", version: 1, capturedAt: new Date().toISOString(), source: "上海大学学生学业情况查询", nodes: categories, categories: categories.filter((item) => item.requiredCredits !== null), courses: uniqueCourses };
};
globalThis.coursepilotReadAcademicProgress();
