const DEFAULTS = {
  daemonUrl: "http://127.0.0.1:8765",
  sharedSecret: "",
  trackedUser: "shihua-guo",
  repos: ["shihua-guo/tools"],
  scanIntervalMinutes: 2,
  enabled: false
};

const SCAN_ALARM = "issueBridgeScan";

async function getSettings() {
  const raw = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...raw };
}

async function setLog(message) {
  const current = await chrome.storage.local.get({ logs: [] });
  const logs = [...current.logs, `${new Date().toISOString()} ${message}`].slice(-100);
  await chrome.storage.local.set({ logs });
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

function firstText(doc, selectors) {
  for (const selector of selectors) {
    const el = doc.querySelector(selector);
    if (el && el.textContent.trim()) return el.textContent.trim();
  }
  return "";
}

function collectLabels(doc) {
  const labels = new Set();
  doc.querySelectorAll("a[href*='/labels/'], span[data-view-component='true'][title]").forEach((el) => {
    const text = el.textContent.trim();
    if (text) labels.add(text);
  });
  return [...labels];
}

function parseIssueDocument(repo, number, url, html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const title = firstText(doc, [
    "bdi.js-issue-title",
    "[data-testid='issue-title']",
    ".gh-header-title .js-issue-title",
    ".js-issue-title"
  ]);

  const timelineComments = [...doc.querySelectorAll(".js-comment-container, .timeline-comment-group")];
  const comments = [];
  for (const node of timelineComments) {
    const authorLogin = firstText(node, ["a.author", ".author", "[data-testid='comment-author']"]);
    const body = firstText(node, [
      "[data-testid='comment-body']",
      ".comment-body",
      ".edit-comment-hide .js-comment-body",
      ".js-comment-body"
    ]);
    const timeEl = node.querySelector("relative-time, time-ago, local-time");
    const linkEl = node.querySelector("a[href*='issuecomment-']");
    const createdAt = timeEl?.getAttribute("datetime") || "";
    const commentUrl = linkEl?.href || "";
    const commentId = (commentUrl.match(/issuecomment-(\d+)/) || [])[1] || node.id || `${repo}#${number}:${comments.length + 1}`;
    if (authorLogin || body) {
      comments.push({
        id: commentId,
        author_login: authorLogin,
        body,
        created_at: createdAt,
        url: commentUrl
      });
    }
  }

  const issueAuthor = comments[0]?.author_login || firstText(doc, ["a.author", ".author"]);
  const issueBody = comments[0]?.body || "";
  const createdAt = comments[0]?.created_at || doc.querySelector("relative-time, time-ago, local-time")?.getAttribute("datetime") || "";
  const updatedAt = [...doc.querySelectorAll("relative-time, time-ago, local-time")].pop()?.getAttribute("datetime") || createdAt;

  return {
    issue_key: `${repo}#${number}`,
    repo,
    number,
    url,
    title,
    body: issueBody,
    author_login: issueAuthor,
    labels: collectLabels(doc),
    state: html.includes("State: open") || html.includes("Open") ? "open" : "open",
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

function findCommentForm(doc) {
  return (
    doc.querySelector("form.js-new-comment-form") ||
    doc.querySelector("form[action*='/issues/'][action*='/comments']")
  );
}

function extractCommentFields(form) {
  const bodyField = form.querySelector("textarea[name]");
  if (!bodyField) throw new Error("Comment textarea not found");
  const fields = new URLSearchParams();
  form.querySelectorAll("input[name]").forEach((input) => {
    if (input.type === "submit") return;
    fields.set(input.name, input.value || "");
  });
  return {
    action: new URL(form.getAttribute("action"), "https://github.com").toString(),
    bodyFieldName: bodyField.getAttribute("name"),
    fields
  };
}

async function postComment(item) {
  const html = await fetchHtml(item.issue_url);
  if (html.includes(`<!-- ${item.comment_marker} -->`)) {
    return { status: "already_exists", commentUrl: item.issue_url };
  }
  const doc = new DOMParser().parseFromString(html, "text/html");
  const form = findCommentForm(doc);
  if (!form) throw new Error("Comment form not found");
  const { action, bodyFieldName, fields } = extractCommentFields(form);
  fields.set(bodyFieldName, item.comment_body);
  const res = await fetch(action, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: fields.toString()
  });
  if (!res.ok) {
    throw new Error(`Comment POST failed: HTTP ${res.status}`);
  }
  const verifyHtml = await fetchHtml(item.issue_url);
  if (!verifyHtml.includes(`<!-- ${item.comment_marker} -->`)) {
    throw new Error("Comment posted but marker verification failed");
  }
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

async function scheduleAlarm() {
  const settings = await getSettings();
  await chrome.alarms.clear(SCAN_ALARM);
  if (!settings.enabled) return;
  await chrome.alarms.create(SCAN_ALARM, {
    periodInMinutes: Math.max(1, Number(settings.scanIntervalMinutes || 2))
  });
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
    const result = await runScanCycle();
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
    runScanCycle()
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  return false;
});
