const DEFAULT_INTERVAL = 1000;
const MIN_INTERVAL = 100;

const dom = {
  site: document.getElementById("site"),
  selector: document.getElementById("selector"),
  interval: document.getElementById("interval"),
  clickMode: document.getElementById("clickMode"),
  status: document.getElementById("status"),
  logs: document.getElementById("logs"),
  saveBtn: document.getElementById("saveBtn"),
  testBtn: document.getElementById("testBtn"),
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
    .map((x) => `[${fmtTime(x.ts)}] ${x.message}`)
    .join("\n");
}

async function sendToTab(type, payload = {}) {
  if (!activeTabId) throw new Error("没有可用标签页");
  return chrome.tabs.sendMessage(activeTabId, { type, ...payload });
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
    const state = await sendToTab("getState");
    setStatusText(state.running ? "运行中" : "未运行");
    renderLogs(state.logs || []);
  } catch (e) {
    setStatusText("无法连接页面脚本");
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
  const res = await sendToTab("testSelector", { selector });
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

  await saveSiteConfig();
  const res = await sendToTab("startAutoClick", { selector, interval, clickMode });
  setStatusText(res.ok ? "运行中" : `启动失败：${res.reason}`);
  await refreshState();
}

async function onStop() {
  const res = await sendToTab("stopAutoClick", { reason: "手动停止" });
  setStatusText(res.ok ? "已停止" : `停止失败：${res.reason}`);
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
dom.startBtn.addEventListener("click", () => onStart().catch((e) => setStatusText(String(e.message || e))));
dom.stopBtn.addEventListener("click", () => onStop().catch((e) => setStatusText(String(e.message || e))));

init().catch((e) => setStatusText(String(e.message || e)));

window.addEventListener("unload", () => {
  if (poller) clearInterval(poller);
});
