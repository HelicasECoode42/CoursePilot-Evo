(() => {
  window.addEventListener("message", (event) => {
    if (event.source !== window || event.origin !== location.origin || event.data?.type !== "CP_START_IMPORT") return;
    chrome.runtime.sendMessage({ type: "CP_START_IMPORT", requestId: event.data.requestId }).then((response) => {
      window.postMessage({ type: "CP_IMPORT_READY", ok: response?.ok }, location.origin);
    });
  });
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (message.type !== "CP_DELIVER_PROGRESS") return;
    const accept = (event) => {
      if (event.source !== window || event.origin !== location.origin || event.data?.type !== "CP_IMPORT_ACCEPTED" || event.data.requestId !== message.requestId) return;
      clearTimeout(timer);
      window.removeEventListener("message", accept);
      reply({ ok: event.data.ok });
    };
    // 10 秒，原先是 60 秒。页面侧的接收者现在挂在应用级（不再只活在 /records），
    // 所以只要 CoursePilot 开着就会立刻应答；真的没人应答时，让学生 10 秒内看到
    // 失败，而不是盯着「导入 CoursePilot 并返回」干等一分钟。
    const timer = setTimeout(() => {
      window.removeEventListener("message", accept);
      reply({ ok: false, error: "CoursePilot 页面没有应答。请确认 CoursePilot 还开着，并刷新那一页后重试。" });
    }, 10000);
    window.addEventListener("message", accept);
    window.postMessage(message, location.origin);
    return true;
  });
})();
