const DEFAULTS = {
  daemonUrl: "http://127.0.0.1:8765",
  sharedSecret: "",
  trackedUser: "shihua-guo",
  repos: ["shihua-guo/tools"],
  scanIntervalMinutes: 2,
  enabled: false
};

const els = {
  daemonUrl: document.getElementById("daemonUrl"),
  sharedSecret: document.getElementById("sharedSecret"),
  trackedUser: document.getElementById("trackedUser"),
  repos: document.getElementById("repos"),
  scanIntervalMinutes: document.getElementById("scanIntervalMinutes"),
  enabled: document.getElementById("enabled"),
  save: document.getElementById("save"),
  runNow: document.getElementById("runNow"),
  status: document.getElementById("status")
};

async function getSettings() {
  const raw = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...raw };
}

async function setStatus(message) {
  els.status.textContent = message;
}

async function load() {
  const settings = await getSettings();
  els.daemonUrl.value = settings.daemonUrl;
  els.sharedSecret.value = settings.sharedSecret;
  els.trackedUser.value = settings.trackedUser;
  els.repos.value = settings.repos.join("\n");
  els.scanIntervalMinutes.value = String(settings.scanIntervalMinutes);
  els.enabled.checked = Boolean(settings.enabled);
  setStatus(settings.enabled ? "Background scans are enabled." : "Ready.");
}

function readFormSettings() {
  return {
    daemonUrl: els.daemonUrl.value.trim(),
    sharedSecret: els.sharedSecret.value.trim(),
    trackedUser: els.trackedUser.value.trim(),
    repos: els.repos.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    scanIntervalMinutes: Math.max(1, Number(els.scanIntervalMinutes.value || "2")),
    enabled: els.enabled.checked
  };
}

async function saveSettings(settings) {
  await chrome.storage.local.set(settings);
  await chrome.runtime.sendMessage({ type: "settingsUpdated" });
}

async function save() {
  const settings = readFormSettings();
  await saveSettings(settings);
  setStatus(settings.enabled ? "Settings saved. Background scans are enabled." : "Settings saved. Background scans are disabled.");
}

async function startAndKeepRunning() {
  setStatus("Starting background scans...");
  const settings = {
    ...readFormSettings(),
    enabled: true
  };
  els.enabled.checked = true;
  await saveSettings(settings);
  const response = await chrome.runtime.sendMessage({ type: "startBackgroundScans" });
  if (response?.ok) {
    setStatus(`Background scans enabled.\n${response.message || ""}`);
    return;
  }
  setStatus(`Background start failed.\n${response?.error || "Unknown error"}`);
}

els.save.addEventListener("click", save);
els.runNow.addEventListener("click", startAndKeepRunning);

load();
