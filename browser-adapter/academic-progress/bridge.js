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
    const timer = setTimeout(() => {
      window.removeEventListener("message", accept);
      reply({ ok: false });
    }, 60000);
    window.addEventListener("message", accept);
    window.postMessage(message, location.origin);
    return true;
  });
})();
