const DEFAULTS = {
  daemonUrl: "http://127.0.0.1:8765",
  sharedSecret: "",
  trackedUser: "shihua-guo",
  repos: ["shihua-guo/tools"],
  scanIntervalMinutes: 2,
  enabled: false
};

const SCAN_ALARM = "issueBridgeScan";
let activeScan = null;

async function getSettings() {
  const raw = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...raw };
}

async function setLog(message) {
  const current = await chrome.storage.local.get({ logs: [] });
  const logs = [...current.logs, `${new Date().toISOString()} ${message}`].slice(-100);
  await chrome.storage.local.set({ logs });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseIssueNumbers(html, repo) {
  const escapedRepo = repo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`/${escapedRepo}/issues/(\\d+)`, "g");
  const numbers = new Set();
  let match;
  while ((match = re.exec(html)) !== null) {
    numbers.add(Number(match[1]));
  }
  return [...numbers].sort((a, b) => b - a);
}

async function fetchHtml(url) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} for ${url}`);
  }
  return await res.text();
}

function isoTimestamps(html) {
  return html.match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z/g) || [];
}

function stableTimestamp(value, fallback) {
  return value || fallback;
}

function decodeHtml(value) {
  const entities = {
    amp: "&",
    apos: "'",
    gt: ">",
    lt: "<",
    nbsp: " ",
    quot: "\""
  };
  return (value || "").replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (_match, entity) => {
    if (entity[0] === "#") {
      const isHex = entity[1]?.toLowerCase() === "x";
      const code = Number.parseInt(entity.slice(isHex ? 2 : 1), isHex ? 16 : 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : "";
    }
    return entities[entity] || `&${entity};`;
  });
}

function stripTags(value) {
  return decodeHtml(value || "")
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<template\b[\s\S]*?<\/template>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:blockquote|div|h[1-6]|li|p|pre)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeText(value) {
  return stripTags(value).replace(/\s+/g, " ").trim();
}

function tagAttribute(tag, name) {
  const re = new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, "i");
  const match = re.exec(tag || "");
  return decodeHtml(match?.[1] || match?.[2] || match?.[3] || "");
}

function absoluteGithubUrl(value) {
  return value ? new URL(value, "https://github.com").toString() : "";
}

function dataTestIdTag(html, testId) {
  const idx = html.indexOf(`data-testid="${testId}"`);
  if (idx < 0) return "";
  const start = html.lastIndexOf("<", idx);
  const end = html.indexOf(">", idx);
  if (start < 0 || end < 0) return "";
  return html.slice(start, end + 1);
}

function textByDataTestId(html, testId) {
  const tag = dataTestIdTag(html, testId);
  if (!tag) return "";
  const idx = html.indexOf(tag);
  const openEnd = idx + tag.length;
  const tagName = /^<([a-z0-9-]+)/i.exec(tag)?.[1];
  if (!tagName) return "";
  if (tagName.toLowerCase() === "img") {
    return normalizeText(tagAttribute(tag, "alt"));
  }
  const close = new RegExp(`</${tagName}>`, "i");
  const rest = html.slice(openEnd);
  const closeMatch = close.exec(rest);
  const inner = closeMatch ? rest.slice(0, closeMatch.index) : rest.slice(0, 8000);
  return normalizeText(inner);
}

function chunkByDataTestId(html, testId, stopTestIds = []) {
  const idx = html.indexOf(`data-testid="${testId}"`);
  if (idx < 0) return "";
  const start = html.lastIndexOf("<", idx);
  let end = html.length;
  for (const stopTestId of stopTestIds) {
    const stopIdx = html.indexOf(`data-testid="${stopTestId}"`, idx + testId.length);
    if (stopIdx >= 0) {
      const stopStart = html.lastIndexOf("<", stopIdx);
      if (stopStart > start && stopStart < end) end = stopStart;
    }
  }
  return html.slice(start, end);
}

function chunksByDataTestId(html, testId) {
  const chunks = [];
  let searchFrom = 0;
  while (true) {
    const idx = html.indexOf(`data-testid="${testId}"`, searchFrom);
    if (idx < 0) break;
    const start = html.lastIndexOf("<", idx);
    const next = html.indexOf(`data-testid="${testId}"`, idx + testId.length);
    const end = next >= 0 ? html.lastIndexOf("<", next) : html.length;
    chunks.push(html.slice(start, end));
    searchFrom = idx + testId.length;
  }
  return chunks;
}

function firstIsoTimestamp(html, fallback) {
  const timestamps = isoTimestamps(html);
  return stableTimestamp(timestamps[0] || "", fallback);
}

function hrefByDataTestId(html, testId) {
  return absoluteGithubUrl(tagAttribute(dataTestIdTag(html, testId), "href"));
}

function collectLabels(html) {
  const labels = new Set();
  for (const match of html.matchAll(/<a\b[^>]*href=["'][^"']*\/labels\/[^"']*["'][^>]*>([\s\S]*?)<\/a>/gi)) {
    const text = normalizeText(match[1]);
    if (text) labels.add(text);
  }
  return [...labels];
}

function detectIssueState(html) {
  if (/data-status=["']issueClosed["']/i.test(html) || /StateLabel[\s\S]{0,500}>\s*Closed\s*</i.test(html)) {
    return "closed";
  }
  if (/data-status=["']issueOpened["']/i.test(html) || /StateLabel[\s\S]{0,500}>\s*Open\s*</i.test(html)) {
    return "open";
  }
  return "open";
}

function parseIssueDocument(repo, number, url, html) {
  const timestamps = isoTimestamps(html);
  const fallbackCreatedAt = stableTimestamp(timestamps[0] || "", `${repo}#${number}:created`);
  const fallbackUpdatedAt = stableTimestamp(timestamps[timestamps.length - 1] || "", fallbackCreatedAt);
  const title = textByDataTestId(html, "issue-title") ||
    normalizeText((/<title>([\s\S]*?)<\/title>/i.exec(html)?.[1] || "").split("· Issue")[0]);

  const comments = [];
  const issueBodyChunk = chunkByDataTestId(html, "issue-body", ["issue-comment"]);
  if (issueBodyChunk) {
    const issueAuthor = (
      textByDataTestId(issueBodyChunk, "issue-body-header-author") ||
      /aria-label="@([^"]+?)(?:'s|&#x27;s) profile"/i.exec(issueBodyChunk)?.[1] ||
      /href="https:\/\/github\.com\/([^"#?]+)"/i.exec(issueBodyChunk)?.[1] ||
      ""
    ).replace(/^@/, "");
    const issueBody = textByDataTestId(issueBodyChunk, "markdown-body") ||
      textByDataTestId(issueBodyChunk, "issue-body-viewer");
    const issueUrl = hrefByDataTestId(issueBodyChunk, "issue-body-header-link") ||
      absoluteGithubUrl(/href=["']([^"']*#issue-\d+)["']/i.exec(issueBodyChunk)?.[1] || "") ||
      url;
    const issueId = (issueUrl.match(/#(issue-\d+)/) || [])[1] || `${repo}#${number}:body`;
    if (issueAuthor || issueBody) {
      comments.push({
        id: issueId,
        author_login: normalizeText(issueAuthor),
        body: normalizeText(issueBody),
        created_at: firstIsoTimestamp(issueBodyChunk, fallbackCreatedAt),
        url: issueUrl
      });
    }
  }

  for (const chunk of chunksByDataTestId(html, "issue-comment")) {
    const authorLogin = textByDataTestId(chunk, "issue-comment-header-author") ||
      textByDataTestId(chunk, "comment-author") ||
      /<a\b[^>]*class="[^"]*\bauthor\b[^"]*"[^>]*>([\s\S]*?)<\/a>/i.exec(chunk)?.[1] ||
      "";
    const body = textByDataTestId(chunk, "comment-body") ||
      textByDataTestId(chunk, "markdown-body") ||
      /<td\b[^>]*class="[^"]*\bcomment-body\b[^"]*"[^>]*>([\s\S]*?)<\/td>/i.exec(chunk)?.[1] ||
      "";
    const commentUrl = absoluteGithubUrl(/href=["']([^"']*issuecomment-\d+[^"']*)["']/i.exec(chunk)?.[1] || "");
    const chunkId = tagAttribute(/^<[^>]+>/i.exec(chunk)?.[0] || "", "id");
    const commentId = (commentUrl.match(/issuecomment-(\d+)/) || [])[1] || chunkId || `${repo}#${number}:${comments.length + 1}`;
    if (authorLogin || body) {
      comments.push({
        id: commentId,
        author_login: normalizeText(authorLogin),
        body: normalizeText(body),
        created_at: firstIsoTimestamp(chunk, fallbackUpdatedAt),
        url: commentUrl
      });
    }
  }

  const issueAuthor = comments[0]?.author_login || "";
  const issueBody = comments[0]?.body || "";
  const createdAt = comments[0]?.created_at || fallbackCreatedAt;
  const updatedAt = comments[comments.length - 1]?.created_at || fallbackUpdatedAt;

  return {
    issue_key: `${repo}#${number}`,
    repo,
    number,
    url,
    title,
    body: issueBody,
    author_login: issueAuthor,
    labels: collectLabels(html),
    state: detectIssueState(html),
    created_at: createdAt,
    updated_at: updatedAt,
    comments
  };
}

async function fetchIssueDetails(repo, number) {
  const url = `https://github.com/${repo}/issues/${number}`;
  const html = await fetchHtml(url);
  return parseIssueDocument(repo, number, url, html);
}

async function fetchIssueCandidates(repo, trackedUser) {
  const authoredQuery = encodeURIComponent(`is:issue is:open author:${trackedUser}`);
  const commentedQuery = encodeURIComponent(`is:issue is:open commenter:${trackedUser}`);
  const authoredHtml = await fetchHtml(`https://github.com/${repo}/issues?q=${authoredQuery}`);
  const commentedHtml = await fetchHtml(`https://github.com/${repo}/issues?q=${commentedQuery}`);
  const numbers = new Set([
    ...parseIssueNumbers(authoredHtml, repo),
    ...parseIssueNumbers(commentedHtml, repo)
  ]);
  return [...numbers].sort((a, b) => b - a);
}

async function postToDaemon(settings, issues) {
  const res = await fetch(`${settings.daemonUrl}/v1/issues/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      version: "1",
      secret: settings.sharedSecret,
      client_id: "browser-extension",
      scan_id: `${new Date().toISOString()}#scan`,
      scanned_at: new Date().toISOString(),
      issues
    })
  });
  if (!res.ok) {
    throw new Error(`Daemon sync failed: HTTP ${res.status}`);
  }
  return await res.json();
}

async function fetchOutbox(settings) {
  const res = await fetch(`${settings.daemonUrl}/v1/outbox?limit=20`);
  if (!res.ok) {
    throw new Error(`Daemon outbox failed: HTTP ${res.status}`);
  }
  return await res.json();
}

function meaningfulCommentText(body) {
  return normalizeText((body || "")
    .replace(/<details>[\s\S]*?<\/details>/gi, "")
    .replace(/^\s*\[AI\]\s*/i, ""));
}

async function waitForTabLoad(tabId, timeoutMs = 30000) {
  const tab = await chrome.tabs.get(tabId);
  if (tab.status === "complete") return;

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("Issue tab did not finish loading"));
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function issueTabForUrl(issueUrl) {
  const parsed = new URL(issueUrl);
  const matchingTabs = await chrome.tabs.query({ url: `${parsed.origin}${parsed.pathname}*` });
  if (matchingTabs.length > 0 && matchingTabs[0].id) {
    await waitForTabLoad(matchingTabs[0].id);
    return { tabId: matchingTabs[0].id, created: false };
  }

  const tab = await chrome.tabs.create({ url: issueUrl, active: false });
  if (!tab.id) throw new Error("Could not open issue tab");
  await waitForTabLoad(tab.id);
  return { tabId: tab.id, created: true };
}

async function runPageScript(tabId, func, args) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func,
    args
  });
  return results?.[0]?.result;
}

function markerExistsInPage(marker) {
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll("form, textarea, input, [contenteditable='true']").forEach((el) => el.remove());
  return clone.innerText.includes(marker) || clone.innerHTML.includes(marker);
}

async function waitForPageMarker(tabId, marker, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const exists = await runPageScript(tabId, markerExistsInPage, [marker]);
    if (exists) return true;
    await sleep(1000);
  }
  return false;
}

async function submitCommentInPage(commentBody, commentMarker) {
  function pageHasMarker(marker) {
    const clone = document.body.cloneNode(true);
    clone.querySelectorAll("form, textarea, input, [contenteditable='true']").forEach((el) => el.remove());
    return clone.innerText.includes(marker) || clone.innerHTML.includes(marker);
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function isVisible(el) {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden" &&
      style.display !== "none" &&
      rect.width > 0 &&
      rect.height > 0;
  }

  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value") ||
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (descriptor?.set) descriptor.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function buttonText(el) {
    return (el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "").trim();
  }

  function isCommentSubmitButton(el) {
    const text = buttonText(el);
    const attrs = [
      text,
      el.name,
      el.value,
      el.id,
      el.getAttribute("aria-label"),
      el.getAttribute("data-testid")
    ].filter(Boolean).join(" ");
    if (/close|reopen|delete|lock|unlock|关闭|重新打开|删除|锁定/i.test(attrs)) {
      return false;
    }
    return /(^|\b)(comment|reply|submit)(\b|$)|评论|提交|回复/i.test(attrs);
  }

  if (pageHasMarker(commentMarker)) {
    return { status: "already_exists" };
  }

  const textareas = [...document.querySelectorAll("textarea")]
    .filter((el) => !el.disabled && !el.readOnly && isVisible(el));
  const textarea = textareas.find((el) => {
    const haystack = [
      el.name,
      el.id,
      el.placeholder,
      el.getAttribute("aria-label"),
      el.closest("form")?.getAttribute("action"),
      el.closest("[data-testid]")?.getAttribute("data-testid")
    ].filter(Boolean).join(" ");
    return /comment|discussion|reply|leave/i.test(haystack);
  }) || textareas[textareas.length - 1];

  if (!textarea) {
    return { status: "failed", error: "Comment textarea not found in issue page" };
  }

  textarea.scrollIntoView({ block: "center" });
  textarea.focus();
  setNativeValue(textarea, commentBody);
  await wait(500);

  const root = textarea.closest("form") ||
    textarea.closest("[data-testid*='comment']") ||
    textarea.closest("[class*='Comment']") ||
    document;

  let submitButton = null;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const buttons = [
      ...root.querySelectorAll("button, input[type='submit']"),
      ...document.querySelectorAll("button[type='submit'], input[type='submit']")
    ].filter((el) => isVisible(el) && !el.disabled && el.getAttribute("aria-disabled") !== "true");

    submitButton = buttons.find(isCommentSubmitButton);
    if (submitButton) break;
    await wait(250);
  }

  if (!submitButton) {
    return { status: "failed", error: "Comment submit button not found or disabled" };
  }

  submitButton.click();
  return { status: "submitted" };
}

async function postComment(item) {
  if (!meaningfulCommentText(item.comment_body)) {
    throw new Error("Outbox comment body is empty; restart the daemon with the latest code and retry with a new issue comment");
  }

  const html = await fetchHtml(item.issue_url);
  if (html.includes(item.comment_marker)) {
    return { status: "already_exists", commentUrl: item.issue_url };
  }

  const { tabId, created } = await issueTabForUrl(item.issue_url);
  const result = await runPageScript(tabId, submitCommentInPage, [item.comment_body, item.comment_marker]);
  if (result?.status === "already_exists") {
    if (created) await chrome.tabs.remove(tabId);
    return { status: "already_exists", commentUrl: item.issue_url };
  }
  if (result?.status !== "submitted") {
    throw new Error(result?.error || "Comment submission failed");
  }

  const markerFound = await waitForPageMarker(tabId, item.comment_marker);
  const verifyHtml = markerFound ? "" : await fetchHtml(item.issue_url);
  if (!markerFound && !verifyHtml.includes(item.comment_marker)) {
    throw new Error("Comment posted but marker verification failed");
  }
  if (created) await chrome.tabs.remove(tabId);
  return { status: "posted", commentUrl: item.issue_url };
}

async function ackOutbox(settings, item, status, githubCommentUrl, failureReason) {
  await fetch(`${settings.daemonUrl}/v1/outbox/ack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      version: "1",
      secret: settings.sharedSecret,
      outbox_id: item.outbox_id,
      status,
      posted_at: new Date().toISOString(),
      github_comment_url: githubCommentUrl || "",
      failure_reason: failureReason || ""
    })
  });
}

async function runScanCycle() {
  const settings = await getSettings();
  if (!settings.enabled) {
    return { ok: true, message: "Extension disabled." };
  }
  if (!settings.sharedSecret) {
    throw new Error("Shared secret is empty.");
  }
  const issues = [];
  for (const repo of settings.repos) {
    const numbers = await fetchIssueCandidates(repo, settings.trackedUser);
    for (const number of numbers) {
      issues.push(await fetchIssueDetails(repo, number));
    }
  }
  const syncResponse = await postToDaemon(settings, issues);
  const outbox = await fetchOutbox(settings);
  for (const item of outbox.items || []) {
    try {
      const result = await postComment(item);
      await ackOutbox(settings, item, result.status, result.commentUrl, "");
    } catch (error) {
      await ackOutbox(settings, item, "failed", "", error.message || String(error));
    }
  }
  return {
    ok: true,
    message: `accepted=${(syncResponse.accepted_issue_keys || []).length}, queued=${(syncResponse.queued_issue_keys || []).length}, outbox=${(outbox.items || []).length}`
  };
}

async function runScanCycleOnce() {
  if (activeScan) return activeScan;
  activeScan = runScanCycle().finally(() => {
    activeScan = null;
  });
  return activeScan;
}

async function scheduleAlarm() {
  const settings = await getSettings();
  await chrome.alarms.clear(SCAN_ALARM);
  if (!settings.enabled) return;
  const interval = Math.max(1, Number(settings.scanIntervalMinutes || 2));
  await chrome.alarms.create(SCAN_ALARM, {
    delayInMinutes: interval,
    periodInMinutes: interval
  });
}

async function startBackgroundScans() {
  await chrome.storage.local.set({ enabled: true });
  await scheduleAlarm();
  return await runScanCycleOnce();
}

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(DEFAULTS);
  await chrome.storage.local.set({ ...DEFAULTS, ...current });
  await scheduleAlarm();
});

chrome.runtime.onStartup.addListener(scheduleAlarm);

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== SCAN_ALARM) return;
  try {
    const result = await runScanCycleOnce();
    await setLog(`scan ok: ${result.message}`);
  } catch (error) {
    await setLog(`scan failed: ${error.message || String(error)}`);
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "settingsUpdated") {
    scheduleAlarm().then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === "runScanNow") {
    runScanCycleOnce()
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "startBackgroundScans") {
    startBackgroundScans()
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  return false;
});
