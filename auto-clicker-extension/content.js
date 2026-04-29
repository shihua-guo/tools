const LOG_LIMIT = 50;
const MIN_INTERVAL = 100;
const NOT_FOUND_STOP_MS = 3000;

let running = false;
let timerId = null;
let lastFoundAt = 0;
let currentConfig = null;
let clickCount = 0;
const logs = [];

function addLog(message) {
  logs.push({ ts: Date.now(), message });
  if (logs.length > LOG_LIMIT) logs.splice(0, logs.length - LOG_LIMIT);
}

function clearTimer() {
  if (timerId) {
    clearInterval(timerId);
    timerId = null;
  }
}

function isVisible(el) {
  if (!el || !(el instanceof Element)) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (parseFloat(style.opacity || "1") <= 0) return false;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  return true;
}

function isDisabled(el) {
  if (!el) return true;
  return el.matches(":disabled") || el.getAttribute("aria-disabled") === "true";
}

function dispatchMouseFallback(el) {
  const rect = el.getBoundingClientRect();
  const clientX = rect.left + rect.width / 2;
  const clientY = rect.top + rect.height / 2;
  const common = {
    bubbles: true,
    cancelable: true,
    view: window,
    clientX,
    clientY
  };
  el.dispatchEvent(new MouseEvent("mouseover", common));
  el.dispatchEvent(new MouseEvent("mousedown", common));
  el.dispatchEvent(new MouseEvent("mouseup", common));
  el.dispatchEvent(new MouseEvent("click", common));
}

function doClick(el, clickMode) {
  if (clickMode === "auto") {
    el.click();
    dispatchMouseFallback(el);
    return;
  }
  el.click();
}

function findCandidate(selector) {
  try {
    const el = document.querySelector(selector);
    if (!el) return { found: false, reason: "未找到元素" };
    if (!isVisible(el)) return { found: false, reason: "元素不可见" };
    if (isDisabled(el)) return { found: false, reason: "元素为 disabled" };
    return { found: true, el };
  } catch (e) {
    return { found: false, reason: `选择器无效: ${e.message}` };
  }
}

function stopAutoClickInternal(reason) {
  running = false;
  clearTimer();
  addLog(`停止: ${reason}`);
}

function tick() {
  if (!running || !currentConfig) return;
  const result = findCandidate(currentConfig.selector);
  if (result.found) {
    lastFoundAt = Date.now();
    doClick(result.el, currentConfig.clickMode);
    clickCount += 1;
    if (clickCount === 1 || clickCount % 20 === 0) {
      addLog(`点击中: 已触发 ${clickCount} 次`);
    }
    return;
  }

  if (Date.now() - lastFoundAt >= NOT_FOUND_STOP_MS) {
    stopAutoClickInternal("连续 3 秒未找到元素");
  }
}

function startAutoClick({ selector, interval, clickMode }) {
  const safeSelector = String(selector || "").trim();
  const safeInterval = Math.max(MIN_INTERVAL, Math.floor(Number(interval) || MIN_INTERVAL));
  const safeMode = clickMode || "auto";

  if (!safeSelector) {
    return { ok: false, reason: "选择器不能为空" };
  }

  const probe = findCandidate(safeSelector);
  if (!probe.found && String(probe.reason || "").startsWith("选择器无效")) {
    addLog(`启动失败: ${probe.reason}`);
    return { ok: false, reason: probe.reason };
  }

  running = true;
  clearTimer();
  currentConfig = {
    selector: safeSelector,
    interval: safeInterval,
    clickMode: safeMode
  };
  clickCount = 0;
  lastFoundAt = Date.now();
  timerId = setInterval(tick, safeInterval);

  addLog(`开始: selector="${safeSelector}", interval=${safeInterval}ms`);
  if (!probe.found) addLog(`启动时未找到: ${probe.reason}`);
  tick();
  return { ok: true };
}

function testSelector(selector) {
  const safeSelector = String(selector || "").trim();
  if (!safeSelector) return { ok: false, reason: "选择器不能为空" };
  const result = findCandidate(safeSelector);
  if (!result.found) {
    addLog(`测试失败: ${result.reason}`);
    return { ok: false, reason: result.reason };
  }
  const prev = result.el.style.outline;
  result.el.style.outline = "2px solid #ef4444";
  setTimeout(() => {
    result.el.style.outline = prev;
  }, 1000);
  addLog(`测试成功: ${safeSelector}`);
  return { ok: true };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg.type !== "string") return;

  if (msg.type === "startAutoClick") {
    sendResponse(startAutoClick(msg));
    return;
  }

  if (msg.type === "stopAutoClick") {
    if (running) {
      stopAutoClickInternal(msg.reason || "手动停止");
      sendResponse({ ok: true });
    } else {
      sendResponse({ ok: false, reason: "当前未运行" });
    }
    return;
  }

  if (msg.type === "getState") {
    sendResponse({
      running,
      config: currentConfig,
      logs: logs.slice()
    });
    return;
  }

  if (msg.type === "testSelector") {
    sendResponse(testSelector(msg.selector));
  }
});
