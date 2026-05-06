const LOG_LIMIT = 50;
const MIN_INTERVAL = 100;
const NOT_FOUND_STOP_MS = 3000;
const PICKER_SESSION_PREFIX = "picker-session:";

let running = false;
let timerId = null;
let lastFoundAt = 0;
let currentConfig = null;
let clickCount = 0;
let pickerState = null;
let directTargetElement = null;
const logs = [];

function getFrameLabel() {
  if (window.top === window) return "top";
  try {
    const url = new URL(window.location.href);
    return `iframe:${url.origin}${url.pathname}`;
  } catch (e) {
    return "iframe";
  }
}

function pickerSessionKey(sessionId) {
  return `${PICKER_SESSION_PREFIX}${sessionId}`;
}

function publishPickerSessionState(sessionId, status, reason) {
  if (!sessionId) return;
  const key = pickerSessionKey(sessionId);
  chrome.storage.local.set({
    [key]: {
      status,
      reason,
      ts: Date.now()
    }
  });
  setTimeout(() => {
    chrome.storage.local.remove(key);
  }, 5000);
}

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

function querySelectorShadowDom(selector, root = document) {
  try {
    const el = root.querySelector(selector);
    if (el) return el;
  } catch (e) {
    // If selector is invalid, let the outer try/catch handle it
  }

  const elements = root.querySelectorAll('*');
  for (const el of elements) {
    if (el.shadowRoot) {
      const found = querySelectorShadowDom(selector, el.shadowRoot);
      if (found) return found;
    }
  }
  return null;
}

function querySelectorAllShadowDom(selector, root = document, matches = []) {
  const elements = root.querySelectorAll(selector);
  for (const el of elements) matches.push(el);

  const allElements = root.querySelectorAll("*");
  for (const el of allElements) {
    if (el.shadowRoot) {
      querySelectorAllShadowDom(selector, el.shadowRoot, matches);
    }
  }
  return matches;
}

function cssEscape(value) {
  const text = String(value);
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(text);
  }
  return text.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function attrEscape(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function selectorMatchesTarget(selector, target) {
  try {
    const matches = querySelectorAllShadowDom(selector);
    return matches.length === 1 && matches[0] === target;
  } catch (e) {
    return false;
  }
}

function tagName(el) {
  return el.tagName.toLowerCase();
}

function meaningfulClassNames(el) {
  return Array.from(el.classList || [])
    .filter((name) => name && !/^active$|^focus$|^hover$|^selected$/.test(name))
    .slice(0, 3);
}

function nthOfTypeSegment(el) {
  let index = 1;
  let sibling = el.previousElementSibling;
  while (sibling) {
    if (sibling.tagName === el.tagName) index += 1;
    sibling = sibling.previousElementSibling;
  }
  return `${tagName(el)}:nth-of-type(${index})`;
}

function elementSelectorCandidates(el) {
  const tag = tagName(el);
  const candidates = [];

  if (el.id) {
    candidates.push(`#${cssEscape(el.id)}`);
    candidates.push(`${tag}#${cssEscape(el.id)}`);
  }

  for (const attr of ["data-testid", "data-test", "data-cy", "aria-label", "name", "title", "role"]) {
    const value = el.getAttribute(attr);
    if (value) candidates.push(`${tag}[${attr}="${attrEscape(value)}"]`);
  }

  const classes = meaningfulClassNames(el);
  if (classes.length > 0) {
    candidates.push(`${tag}.${classes.map(cssEscape).join(".")}`);
  }

  candidates.push(nthOfTypeSegment(el));
  candidates.push(tag);
  return candidates;
}

function generateSelector(target) {
  for (const candidate of elementSelectorCandidates(target)) {
    if (selectorMatchesTarget(candidate, target)) return candidate;
  }

  const segments = [];
  let el = target;
  while (el && el instanceof Element && el !== document.documentElement) {
    let segment = nthOfTypeSegment(el);
    for (const candidate of elementSelectorCandidates(el)) {
      if (selectorMatchesTarget(candidate, el)) {
        segment = candidate;
        break;
      }
    }

    segments.unshift(segment);
    const selector = segments.join(" > ");
    if (selectorMatchesTarget(selector, target)) return selector;

    el = el.parentElement;
  }

  return segments.join(" > ") || tagName(target);
}

function validateCandidateElement(el) {
  if (!el) return { found: false, reason: "未找到元素" };
  if (!el.isConnected) return { found: false, reason: "元素已从页面移除" };
  if (!isVisible(el)) return { found: false, reason: "元素不可见" };
  if (isDisabled(el)) return { found: false, reason: "元素为 disabled" };
  return { found: true, el };
}

function findCandidate(selector) {
  try {
    let el = document.querySelector(selector);
    if (!el) el = querySelectorShadowDom(selector);

    return validateCandidateElement(el);
  } catch (e) {
    return { found: false, reason: `选择器无效: ${e.message}` };
  }
}

function findDirectTargetCandidate() {
  return validateCandidateElement(directTargetElement);
}

function stopAutoClickInternal(reason) {
  running = false;
  directTargetElement = null;
  clearTimer();
  addLog(`停止: ${reason}`);
}

function tick() {
  if (!running || !currentConfig) return;
  const result = directTargetElement ? findDirectTargetCandidate() : findCandidate(currentConfig.selector);
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

function startAutoClick({ selector, interval, clickMode }, directTarget = null) {
  const safeSelector = String(selector || "").trim();
  const safeInterval = Math.max(MIN_INTERVAL, Math.floor(Number(interval) || MIN_INTERVAL));
  const safeMode = clickMode || "auto";

  if (!safeSelector && !directTarget) {
    return { ok: false, reason: "选择器不能为空" };
  }

  const probe = directTarget ? validateCandidateElement(directTarget) : findCandidate(safeSelector);
  if (!probe.found && String(probe.reason || "").startsWith("选择器无效")) {
    addLog(`启动失败: ${probe.reason}`);
    return { ok: false, reason: probe.reason };
  }

  running = true;
  clearTimer();
  currentConfig = {
    selector: safeSelector,
    interval: safeInterval,
    clickMode: safeMode,
    directTarget: Boolean(directTarget)
  };
  directTargetElement = directTarget || null;
  clickCount = 0;
  lastFoundAt = Date.now();
  timerId = setInterval(tick, safeInterval);

  addLog(`开始: selector="${safeSelector}", interval=${safeInterval}ms${directTarget ? ", directTarget=true" : ""}`);
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

function probeSelector(selector) {
  const safeSelector = String(selector || "").trim();
  if (!safeSelector) return { ok: false, reason: "选择器不能为空" };
  const result = findCandidate(safeSelector);
  return result.found
    ? { ok: true }
    : { ok: false, reason: result.reason };
}

function createPickerNode(tag, className, styles, text) {
  const node = document.createElement(tag);
  node.className = className;
  Object.assign(node.style, styles);
  if (text) node.textContent = text;
  document.documentElement.appendChild(node);
  return node;
}

function isPickerNode(el) {
  return Boolean(el && el.closest && el.closest(".auto-clicker-picker-ui"));
}

function getEventElement(event) {
  const path = typeof event.composedPath === "function" ? event.composedPath() : [];
  for (const item of path) {
    if (item instanceof Element && !isPickerNode(item)) return item;
  }
  return event.target instanceof Element && !isPickerNode(event.target) ? event.target : null;
}

function preferClickableTarget(el) {
  if (!el || !el.closest) return el;
  return el.closest([
    "button",
    "a[href]",
    "input",
    "select",
    "textarea",
    "summary",
    "[role='button']",
    "[role='link']",
    "[onclick]",
    "[tabindex]"
  ].join(",")) || el;
}

function updatePickerHighlight(target) {
  if (!pickerState || !target) return;
  const rect = target.getBoundingClientRect();
  Object.assign(pickerState.highlight.style, {
    display: rect.width > 0 && rect.height > 0 ? "block" : "none",
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`
  });
}

function savePickedConfig(selector, interval, clickMode, hostHint = "") {
  const host = String(hostHint || window.location.host || "-").trim() || "-";
  const key = `config:${host}`;
  chrome.storage.local.get(key, (stored) => {
    const prev = stored[key] || {};
    chrome.storage.local.set({
      [key]: {
        ...prev,
        selector,
        interval,
        clickMode
      }
    });
  });
}

function stopElementPicker(reason, log = true) {
  if (!pickerState) return;

  document.removeEventListener("mousemove", pickerState.onMouseMove, true);
  document.removeEventListener("click", pickerState.onClick, true);
  document.removeEventListener("keydown", pickerState.onKeyDown, true);
  window.removeEventListener("scroll", pickerState.onViewportChange, true);
  window.removeEventListener("resize", pickerState.onViewportChange, true);

  pickerState.highlight.remove();
  pickerState.tip.remove();
  pickerState = null;

  if (log) addLog(`点选模式结束: ${reason}`);
}

function pickElement(target) {
  if (!pickerState || !target) return;
  const config = pickerState.config;
  const sessionId = config.sessionId;
  const selector = generateSelector(target);
  stopElementPicker("已选择元素", false);
  publishPickerSessionState(sessionId, "picked", "其他 frame 已选择元素");

  savePickedConfig(selector, config.interval, config.clickMode, config.topHost);
  addLog(`点选成功: ${selector}`);

  if (config.autoStart) {
    setTimeout(() => {
      const res = startAutoClick({
        selector,
        interval: config.interval,
        clickMode: config.clickMode
      }, target);
      if (!res.ok) addLog(`点选后启动失败: ${res.reason}`);
    }, 50);
  }
}

function startElementPicker({ interval, clickMode, autoStart, sessionId, topHost }) {
  const safeInterval = Math.max(MIN_INTERVAL, Math.floor(Number(interval) || MIN_INTERVAL));
  const safeMode = clickMode || "auto";
  const safeTopHost = String(topHost || "").trim();

  stopElementPicker("重新进入", false);

  const highlight = createPickerNode("div", "auto-clicker-picker-ui", {
    position: "fixed",
    zIndex: "2147483647",
    pointerEvents: "none",
    display: "none",
    border: "2px solid #ef4444",
    boxShadow: "0 0 0 999999px rgba(15, 23, 42, 0.12)",
    borderRadius: "4px"
  });
  const tip = createPickerNode("div", "auto-clicker-picker-ui", {
    position: "fixed",
    zIndex: "2147483647",
    left: "50%",
    top: "12px",
    transform: "translateX(-50%)",
    padding: "8px 10px",
    borderRadius: "8px",
    background: "#111827",
    color: "#fff",
    font: '13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    boxShadow: "0 8px 24px rgba(0, 0, 0, 0.22)",
    pointerEvents: "none"
  }, autoStart ? "点击目标元素后会自动开始；按 Esc 取消" : "点击目标元素；按 Esc 取消");

  pickerState = {
    highlight,
    tip,
    currentTarget: null,
    config: {
      interval: safeInterval,
      clickMode: safeMode,
      autoStart: Boolean(autoStart),
      sessionId: sessionId || "",
      topHost: safeTopHost || window.location.host || "-"
    },
    onMouseMove(event) {
      const target = preferClickableTarget(getEventElement(event));
      if (!target) return;
      pickerState.currentTarget = target;
      updatePickerHighlight(target);
    },
    onClick(event) {
      const target = pickerState.currentTarget || preferClickableTarget(getEventElement(event));
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      pickElement(target);
    },
    onKeyDown(event) {
      if (event.key !== "Escape") return;
      const activeSessionId = pickerState && pickerState.config ? pickerState.config.sessionId : "";
      event.preventDefault();
      event.stopPropagation();
      stopElementPicker("用户取消");
      publishPickerSessionState(activeSessionId, "cancelled", "用户取消");
    },
    onViewportChange() {
      if (pickerState && pickerState.currentTarget) {
        updatePickerHighlight(pickerState.currentTarget);
      }
    }
  };

  document.addEventListener("mousemove", pickerState.onMouseMove, true);
  document.addEventListener("click", pickerState.onClick, true);
  document.addEventListener("keydown", pickerState.onKeyDown, true);
  window.addEventListener("scroll", pickerState.onViewportChange, true);
  window.addEventListener("resize", pickerState.onViewportChange, true);

  addLog("点选模式: 请在页面中点击目标元素");
  return { ok: true };
}

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || !pickerState || !pickerState.config) return;
  const sessionId = pickerState.config.sessionId;
  if (!sessionId) return;

  const change = changes[pickerSessionKey(sessionId)];
  if (!change || !change.newValue) return;

  const payload = change.newValue;
  if (payload.status === "picked" || payload.status === "cancelled") {
    stopElementPicker(payload.reason || "点选模式已结束");
  }
});

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
      picking: Boolean(pickerState),
      config: currentConfig,
      logs: logs.slice(),
      frameLabel: getFrameLabel()
    });
    return;
  }

  if (msg.type === "probeSelector") {
    sendResponse(probeSelector(msg.selector));
    return;
  }

  if (msg.type === "testSelector") {
    sendResponse(testSelector(msg.selector));
    return;
  }

  if (msg.type === "startElementPicker") {
    sendResponse(startElementPicker(msg));
    return;
  }

  if (msg.type === "cancelElementPicker") {
    if (pickerState) {
      stopElementPicker(msg.reason || "手动取消");
      sendResponse({ ok: true });
    } else {
      sendResponse({ ok: false, reason: "当前未处于点选模式" });
    }
  }
});
