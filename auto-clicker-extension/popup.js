const DEFAULT_INTERVAL = 1000;
const MIN_INTERVAL = 100;
const LOG_LIMIT = 50;

const dom = {
  site: document.getElementById("site"),
  selector: document.getElementById("selector"),
  interval: document.getElementById("interval"),
  clickMode: document.getElementById("clickMode"),
  status: document.getElementById("status"),
  logs: document.getElementById("logs"),
  saveBtn: document.getElementById("saveBtn"),
  testBtn: document.getElementById("testBtn"),
  pickBtn: document.getElementById("pickBtn"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn")
};

let activeTabId = null;
let activeHost = null;
let poller = null;

function normalizeInterval(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_INTERVAL;
  return Math.max(MIN_INTERVAL, Math.floor(n));
}

function cfgKey(host) {
  return `config:${host}`;
}

function fmtTime(ts) {
  const d = new Date(ts);
  return d.toLocaleTimeString();
}

function renderLogs(logs) {
  if (!Array.isArray(logs) || logs.length === 0) {
    dom.logs.textContent = "暂无日志";
    return;
  }
  dom.logs.textContent = logs
    .map((x) => {
      const framePrefix = x.frameLabel ? `[${x.frameLabel}] ` : "";
      return `[${fmtTime(x.ts)}] ${framePrefix}${x.message}`;
    })
    .join("\n");
}

function isInjectableUrl(url) {
  try {
    const parsed = new URL(url || "");
    return ["http:", "https:", "file:"].includes(parsed.protocol);
  } catch (e) {
    return false;
  }
}

async function injectContentScript(frameIds = null) {
  if (!activeTabId) throw new Error("没有可用标签页");
  const tab = await chrome.tabs.get(activeTabId);
  if (!isInjectableUrl(tab.url)) {
    throw new Error("当前页面不支持注入脚本，请切换到普通网页后再使用");
  }

  const target = frameIds && frameIds.length > 0
    ? { tabId: activeTabId, frameIds }
    : { tabId: activeTabId, allFrames: true };

  await chrome.scripting.executeScript({
    target,
    files: ["content.js"]
  });
}

async function getFrameIds() {
  if (!activeTabId) throw new Error("没有可用标签页");

  const frames = await chrome.webNavigation.getAllFrames({ tabId: activeTabId });
  const frameIds = (frames || [])
    .map((frame) => frame.frameId)
    .filter((frameId) => Number.isInteger(frameId));

  if (!frameIds.includes(0)) frameIds.unshift(0);
  return Array.from(new Set(frameIds)).sort((a, b) => a - b);
}

async function sendToFrame(frameId, type, payload = {}) {
  if (!activeTabId) throw new Error("没有可用标签页");
  try {
    return await chrome.tabs.sendMessage(activeTabId, { type, ...payload }, { frameId });
  } catch (firstError) {
    await injectContentScript([frameId]);
    try {
      return await chrome.tabs.sendMessage(activeTabId, { type, ...payload }, { frameId });
    } catch (secondError) {
      throw new Error(secondError.message || firstError.message || "无法连接页面脚本");
    }
  }
}

async function sendToFrames(type, payload = {}) {
  const frameIds = await getFrameIds();
  const results = [];

  for (const frameId of frameIds) {
    try {
      const response = await sendToFrame(frameId, type, payload);
      results.push({ frameId, ok: true, response });
    } catch (e) {
      results.push({ frameId, ok: false, error: e.message || String(e) });
    }
  }

  return results;
}

function firstResultMessage(results, fallback) {
  for (const item of results) {
    if (!item.ok && item.error) return item.error;
    if (item.ok && item.response && item.response.reason) return item.response.reason;
  }
  return fallback;
}

function mergeLogs(states) {
  const merged = [];

  for (const state of states) {
    const frameLabel = state.frameLabel || (state.frameId === 0 ? "top" : `iframe:${state.frameId}`);
    for (const entry of state.logs || []) {
      merged.push({
        ...entry,
        frameLabel
      });
    }
  }

  merged.sort((a, b) => a.ts - b.ts);
  return merged.slice(-LOG_LIMIT);
}

async function locateSelectorFrame(selector) {
  const results = await sendToFrames("probeSelector", { selector });
  let invalidReason = "";
  let firstReason = "";

  for (const item of results) {
    if (!item.ok) {
      if (!firstReason) firstReason = item.error;
      continue;
    }

    const response = item.response || {};
    if (response.ok) {
      return { ok: true, frameId: item.frameId };
    }

    if (!invalidReason && String(response.reason || "").startsWith("选择器无效")) {
      invalidReason = response.reason;
    }
    if (!firstReason && response.reason) {
      firstReason = response.reason;
    }
  }

  return { ok: false, reason: invalidReason || firstReason || "未找到元素" };
}

async function collectFrameStates() {
  const results = await sendToFrames("getState");
  const states = results
    .filter((item) => item.ok && item.response)
    .map((item) => ({
      frameId: item.frameId,
      ...item.response
    }));

  return { states, results };
}

function createPickerSessionId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function getCurrentTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

async function loadSiteConfig() {
  if (!activeHost) return;
  const key = cfgKey(activeHost);
  const stored = await chrome.storage.local.get(key);
  const cfg = stored[key] || {};
  dom.selector.value = cfg.selector || "";
  dom.interval.value = normalizeInterval(cfg.interval || DEFAULT_INTERVAL);
  dom.clickMode.value = cfg.clickMode || "auto";
}

async function saveSiteConfig() {
  if (!activeHost) return;
  const selector = dom.selector.value.trim();
  const interval = normalizeInterval(dom.interval.value);
  dom.interval.value = String(interval);
  const clickMode = dom.clickMode.value || "auto";

  const key = cfgKey(activeHost);
  await chrome.storage.local.set({
    [key]: { selector, interval, clickMode }
  });
}

function setStatusText(text) {
  dom.status.textContent = text;
}

async function refreshState() {
  try {
    const { states, results } = await collectFrameStates();

    if (states.length === 0) {
      setStatusText(firstResultMessage(results, "无法连接页面脚本"));
      renderLogs([]);
      return;
    }

    const hasRunning = states.some((state) => state.running);
    const hasPicking = states.some((state) => state.picking);

    if (hasPicking) {
      setStatusText("点选中：请在页面点击目标元素");
    } else {
      setStatusText(hasRunning ? "运行中" : "未运行");
    }

    renderLogs(mergeLogs(states));
  } catch (e) {
    setStatusText(e.message || "无法连接页面脚本");
    renderLogs([]);
  }
}

async function onSave() {
  await saveSiteConfig();
  setStatusText("配置已保存");
}

async function onTest() {
  const selector = dom.selector.value.trim();
  if (!selector) {
    setStatusText("请先填写选择器");
    return;
  }

  const located = await locateSelectorFrame(selector);
  if (!located.ok) {
    setStatusText(`测试失败：${located.reason}`);
    await refreshState();
    return;
  }

  const res = await sendToFrame(located.frameId, "testSelector", { selector });
  setStatusText(res.ok ? "测试成功：元素可点击" : `测试失败：${res.reason}`);
  await refreshState();
}

async function onStart() {
  const selector = dom.selector.value.trim();
  if (!selector) {
    setStatusText("请先填写选择器");
    return;
  }

  const interval = normalizeInterval(dom.interval.value);
  dom.interval.value = String(interval);
  const clickMode = dom.clickMode.value || "auto";
  const located = await locateSelectorFrame(selector);

  if (!located.ok) {
    setStatusText(`启动失败：${located.reason}`);
    await refreshState();
    return;
  }

  await saveSiteConfig();
  const res = await sendToFrame(located.frameId, "startAutoClick", { selector, interval, clickMode });
  setStatusText(res.ok ? "运行中" : `启动失败：${res.reason}`);
  await refreshState();
}

async function onPickStart() {
  const interval = normalizeInterval(dom.interval.value);
  dom.interval.value = String(interval);
  const clickMode = dom.clickMode.value || "auto";
  const sessionId = createPickerSessionId();

  const results = await sendToFrames("startElementPicker", {
    interval,
    clickMode,
    autoStart: true,
    sessionId
  });
  const okCount = results.filter((item) => item.ok && item.response && item.response.ok).length;

  if (okCount === 0) {
    setStatusText(`点选失败：${firstResultMessage(results, "无法进入点选模式")}`);
  } else {
    setStatusText("请在页面点击目标元素，选中后会自动开始");
  }
  await refreshState();
}

async function onStop() {
  const results = await sendToFrames("stopAutoClick", { reason: "手动停止" });
  const stopped = results.some((item) => item.ok && item.response && item.response.ok);

  if (stopped) {
    setStatusText("已停止");
  } else {
    setStatusText(`停止失败：${firstResultMessage(results, "当前未运行")}`);
  }
  await refreshState();
}

async function init() {
  const tab = await getCurrentTab();
  if (!tab || !tab.id || !tab.url) {
    setStatusText("当前标签页不可用");
    return;
  }

  activeTabId = tab.id;
  let host = "-";
  try {
    const url = new URL(tab.url);
    host = url.host || "-";
    activeHost = host;
  } catch (e) {
    activeHost = null;
  }
  dom.site.textContent = host;

  await loadSiteConfig();
  await refreshState();
  poller = setInterval(() => {
    refreshState().catch(() => {});
  }, 1000);
}

dom.saveBtn.addEventListener("click", () => onSave().catch((e) => setStatusText(String(e.message || e))));
dom.testBtn.addEventListener("click", () => onTest().catch((e) => setStatusText(String(e.message || e))));
dom.pickBtn.addEventListener("click", () => onPickStart().catch((e) => setStatusText(String(e.message || e))));
dom.startBtn.addEventListener("click", () => onStart().catch((e) => setStatusText(String(e.message || e))));
dom.stopBtn.addEventListener("click", () => onStop().catch((e) => setStatusText(String(e.message || e))));

init().catch((e) => setStatusText(String(e.message || e)));

window.addEventListener("unload", () => {
  if (poller) clearInterval(poller);
});
