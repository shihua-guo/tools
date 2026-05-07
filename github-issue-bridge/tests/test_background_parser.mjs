import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

function loadParser() {
  const code = fs.readFileSync(new URL("../extension/background.js", import.meta.url), "utf8");
  const noop = () => {};
  const sandbox = {
    console,
    URL,
    setTimeout,
    clearTimeout,
    chrome: {
      storage: { local: { get: async () => ({}), set: async () => ({}) } },
      alarms: { create: async () => {}, clear: async () => {}, onAlarm: { addListener: noop } },
      runtime: {
        onInstalled: { addListener: noop },
        onStartup: { addListener: noop },
        onMessage: { addListener: noop }
      },
      action: { setBadgeText: noop, setBadgeBackgroundColor: noop }
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox.parseIssueDocument;
}

test("parseIssueDocument reads issue body and comments from embedded issue data", () => {
  const parseIssueDocument = loadParser();
  const embeddedData = {
    payload: {
      preloadedQueries: [
        {
          result: {
            data: {
              repository: {
                owner: { login: "shihua-guo" },
                name: "tools",
                issue: {
                  number: 7,
                  url: "https://github.com/shihua-guo/tools/issues/7",
                  title: "[hw] parser regression",
                  body: "issue body from embedded data",
                  state: "OPEN",
                  createdAt: "2026-05-07T00:00:00Z",
                  updatedAt: "2026-05-07T00:05:00Z",
                  author: { login: "shihua-guo" },
                  labels: {
                    edges: [
                      { node: { name: "bug" } },
                      { node: { name: "bridge" } }
                    ]
                  },
                  frontTimelineItems: {
                    edges: [
                      {
                        node: {
                          __typename: "IssueComment",
                          id: "comment-1",
                          author: { login: "shihua-guo" },
                          body: "first follow-up",
                          createdAt: "2026-05-07T00:01:00Z",
                          url: "https://github.com/shihua-guo/tools/issues/7#issuecomment-1"
                        }
                      },
                      {
                        node: {
                          __typename: "CrossReferencedEvent",
                          id: "xref-1",
                          createdAt: "2026-05-07T00:02:00Z"
                        }
                      }
                    ]
                  },
                  backTimelineItems: {
                    edges: [
                      {
                        node: {
                          __typename: "IssueComment",
                          id: "comment-2",
                          author: { login: "bridge-bot" },
                          body: "[AI]\nassistant reply",
                          createdAt: "2026-05-07T00:03:00Z",
                          url: "https://github.com/shihua-guo/tools/issues/7#issuecomment-2"
                        }
                      }
                    ]
                  }
                }
              }
            }
          }
        }
      ]
    }
  };

  const html = `<script type="application/json" data-target="react-app.embeddedData">${JSON.stringify(embeddedData)}</script>`;
  const parsed = parseIssueDocument("shihua-guo/tools", 7, "https://github.com/shihua-guo/tools/issues/7", html);

  assert.equal(parsed.title, "[hw] parser regression");
  assert.equal(parsed.body, "issue body from embedded data");
  assert.equal(parsed.author_login, "shihua-guo");
  assert.deepEqual(Array.from(parsed.labels), ["bug", "bridge"]);
  assert.equal(parsed.state, "open");
  assert.equal(parsed.comments.length, 2);
  assert.deepEqual(Array.from(parsed.comments, (item) => item.id), ["comment-1", "comment-2"]);
  assert.deepEqual(Array.from(parsed.comments, (item) => item.author_login), ["shihua-guo", "bridge-bot"]);
  assert.equal(parsed.comments[0].body, "first follow-up");
  assert.equal(parsed.comments[1].body, "[AI]\nassistant reply");
});
