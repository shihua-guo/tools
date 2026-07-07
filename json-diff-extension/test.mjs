import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const source = fs.readFileSync(new URL("./popup.js", import.meta.url), "utf8");
const sandbox = {
  document: {
    getElementById() {
      return {
        addEventListener() {},
        className: "",
        hidden: false,
        textContent: "",
        value: "",
        innerHTML: ""
      };
    }
  }
};

vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const before = { b: 2, a: { y: true, x: 1 }, arr: ["cn"] };
const after = { a: { x: 2, z: 3 }, b: 2, arr: ["cn", "us"] };
const sorted = sandbox.stableSortJson(before);
assert.equal(JSON.stringify(Object.keys(sorted)), JSON.stringify(["a", "arr", "b"]));
assert.equal(JSON.stringify(Object.keys(sorted.a)), JSON.stringify(["x", "y"]));

const result = sandbox.compareJson(before, after);
assert.equal(result.same, 2);
assert.equal(
  JSON.stringify(result.changes.map((change) => `${change.type}:${change.path}`)),
  JSON.stringify(["changed:$.a.x", "removed:$.a.y", "added:$.a.z", "added:$.arr[1]"])
);

console.log("json-diff-extension tests passed");
