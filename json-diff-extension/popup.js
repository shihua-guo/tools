const dom = {
  beforeInput: document.getElementById("beforeInput"),
  afterInput: document.getElementById("afterInput"),
  beforeOutput: document.getElementById("beforeOutput"),
  afterOutput: document.getElementById("afterOutput"),
  message: document.getElementById("message"),
  summaryText: document.getElementById("summaryText"),
  addedCount: document.getElementById("addedCount"),
  removedCount: document.getElementById("removedCount"),
  changedCount: document.getElementById("changedCount"),
  sameCount: document.getElementById("sameCount"),
  changeList: document.getElementById("changeList"),
  compareBtn: document.getElementById("compareBtn"),
  clearBtn: document.getElementById("clearBtn"),
  sampleBtn: document.getElementById("sampleBtn")
};

const CHANGE_LABELS = {
  added: "新增",
  removed: "删除",
  changed: "修改"
};

function isPlainObject(value) {
  return Object.prototype.toString.call(value) === "[object Object]";
}

function stableSortJson(value) {
  if (Array.isArray(value)) {
    return value.map(stableSortJson);
  }
  if (!isPlainObject(value)) {
    return value;
  }

  return Object.keys(value)
    .sort((a, b) => a.localeCompare(b))
    .reduce((acc, key) => {
      acc[key] = stableSortJson(value[key]);
      return acc;
    }, {});
}

function pathToString(path) {
  if (path.length === 0) return "$";
  return path
    .map((part) => (typeof part === "number" ? `[${part}]` : `.${part}`))
    .join("")
    .replace(/^\./, "$.");
}

function deepEqual(a, b) {
  return JSON.stringify(stableSortJson(a)) === JSON.stringify(stableSortJson(b));
}

function compareJson(before, after, path = []) {
  if (deepEqual(before, after)) {
    return { changes: [], same: 1 };
  }

  if (Array.isArray(before) && Array.isArray(after)) {
    const max = Math.max(before.length, after.length);
    const result = { changes: [], same: 0 };
    for (let index = 0; index < max; index += 1) {
      if (index >= before.length) {
        result.changes.push({ type: "added", path: pathToString([...path, index]), before: undefined, after: after[index] });
      } else if (index >= after.length) {
        result.changes.push({ type: "removed", path: pathToString([...path, index]), before: before[index], after: undefined });
      } else {
        const child = compareJson(before[index], after[index], [...path, index]);
        result.changes.push(...child.changes);
        result.same += child.same;
      }
    }
    return result;
  }

  if (isPlainObject(before) && isPlainObject(after)) {
    const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).sort((a, b) => a.localeCompare(b));
    const result = { changes: [], same: 0 };
    for (const key of keys) {
      if (!Object.prototype.hasOwnProperty.call(before, key)) {
        result.changes.push({ type: "added", path: pathToString([...path, key]), before: undefined, after: after[key] });
      } else if (!Object.prototype.hasOwnProperty.call(after, key)) {
        result.changes.push({ type: "removed", path: pathToString([...path, key]), before: before[key], after: undefined });
      } else {
        const child = compareJson(before[key], after[key], [...path, key]);
        result.changes.push(...child.changes);
        result.same += child.same;
      }
    }
    return result;
  }

  return {
    changes: [{ type: "changed", path: pathToString(path), before, after }],
    same: 0
  };
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function classForLine(line, side, changes) {
  const trimmed = line.trim();
  const keyMatch = trimmed.match(/^"([^"]+)":/);
  if (!keyMatch) return "";

  const key = keyMatch[1];
  const match = changes.find((change) => change.path.endsWith(`.${key}`));
  if (!match) return "";
  if (side === "before" && match.type === "added") return "";
  if (side === "after" && match.type === "removed") return "";
  return match.type;
}

function renderJson(target, value, side, changes) {
  const lines = JSON.stringify(stableSortJson(value), null, 2).split("\n");
  target.innerHTML = lines
    .map((line) => {
      const cls = classForLine(line, side, changes);
      return `<span class="line ${cls}">${escapeHtml(line) || " "}</span>`;
    })
    .join("");
}

function showMessage(text) {
  dom.message.textContent = text;
  dom.message.hidden = !text;
}

function renderSummary(result) {
  const counts = result.changes.reduce(
    (acc, change) => {
      acc[change.type] += 1;
      return acc;
    },
    { added: 0, removed: 0, changed: 0 }
  );

  dom.addedCount.textContent = `新增 ${counts.added}`;
  dom.removedCount.textContent = `删除 ${counts.removed}`;
  dom.changedCount.textContent = `修改 ${counts.changed}`;
  dom.sameCount.textContent = `未变 ${result.same}`;

  if (result.changes.length === 0) {
    dom.summaryText.textContent = "两个 JSON 排序后内容一致，没有字段变化。";
    dom.changeList.textContent = "暂无变化。";
    dom.changeList.className = "change-list empty";
    return;
  }

  dom.summaryText.textContent = `共发现 ${result.changes.length} 处变化：新增 ${counts.added} 处，删除 ${counts.removed} 处，修改 ${counts.changed} 处。`;
  dom.changeList.className = "change-list";
  dom.changeList.innerHTML = result.changes
    .map((change) => {
      return `<div class="change-row"><span class="path">${escapeHtml(change.path)}</span><span class="badge ${change.type}">${CHANGE_LABELS[change.type]}</span></div>`;
    })
    .join("");
}

function parseInput(input, label) {
  const raw = input.value.trim();
  if (!raw) throw new Error(`请填写${label}`);
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`${label} 不是合法 JSON：${error.message}`);
  }
}

function compare() {
  try {
    showMessage("");
    const before = parseInput(dom.beforeInput, "修改前 JSON");
    const after = parseInput(dom.afterInput, "修改后 JSON");
    const result = compareJson(before, after);
    renderJson(dom.beforeOutput, before, "before", result.changes);
    renderJson(dom.afterOutput, after, "after", result.changes);
    renderSummary(result);
  } catch (error) {
    showMessage(error.message || String(error));
  }
}

function clearAll() {
  dom.beforeInput.value = "";
  dom.afterInput.value = "";
  dom.beforeOutput.textContent = "";
  dom.afterOutput.textContent = "";
  showMessage("");
  renderSummary({ changes: [], same: 0 });
}

function loadSample() {
  dom.beforeInput.value = JSON.stringify(
    { name: "订单服务", enabled: true, limits: { qps: 100, regions: ["cn", "us"] }, owner: "team-a" },
    null,
    2
  );
  dom.afterInput.value = JSON.stringify(
    { enabled: false, limits: { qps: 120, regions: ["cn", "eu"] }, name: "订单服务", version: 2 },
    null,
    2
  );
  compare();
}

dom.compareBtn.addEventListener("click", compare);
dom.clearBtn.addEventListener("click", clearAll);
dom.sampleBtn.addEventListener("click", loadSample);
