let serial = Promise.resolve();
function exclusive(action) {
  const current = serial.then(action, action);
  serial = current.then(() => undefined, () => undefined);
  return current;
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  const url = new URL(sender.url || "https://invalid.local");
  if (message.type === "CP_START_IMPORT" && ["127.0.0.1", "localhost"].includes(url.hostname) && url.port === "5173" && url.protocol === "http:" && sender.tab && sender.frameId === 0 && typeof message.requestId === "string") {
    exclusive(async () => {
      const { destination } = await chrome.storage.session.get("destination");
// 15 分钟，原先 5 分钟。流程是「先在 CoursePilot 点连接 → 去学校页面登录 → 回来导入」，
      // 登录本身就可能花掉几分钟，5 分钟太紧，过期后学校那一页只会说「请先点击连接教务」。
      const active = destination?.pending && Date.now() - destination.pendingAt < 900000;
      if (active) return { ok: false, error: "已有学业进度导入正在进行。" };
      await chrome.storage.session.set({ destination: { tabId: sender.tab.id, requestId: message.requestId, pending: true, pendingAt: Date.now() } });
      return { ok: true };
    }).then(reply);
    return true;
  }
  if (message.type === "CP_SEND_PROGRESS" && sender.frameId === 0 && url.origin === "https://jwxt.shu.edu.cn" && url.pathname === "/jwglxt/xsxy/xsxyqk_cxXsxyqkIndex.html") {
    exclusive(async () => {
      const { destination } = await chrome.storage.session.get("destination");
      if (!destination?.pending) throw new Error("请先在 CoursePilot 点击连接教务，再从这里导入。");
      try {
        const result = await chrome.tabs.sendMessage(destination.tabId, { type: "CP_DELIVER_PROGRESS", requestId: destination.requestId, payload: message.payload });
        if (!result?.ok) throw new Error("CoursePilot 未保存数据，请保持学业资料页面打开并重试。");
        await chrome.tabs.update(destination.tabId, { active: true });
        return { ok: true };
      } finally {
        await chrome.storage.session.remove("destination");
      }
    }).then(reply, (error) => reply({ ok: false, error: error.message }));
    return true;
  }
});
