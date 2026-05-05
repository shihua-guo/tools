# GitHub Issue Bridge

GitHub Issue Bridge runs on a local machine that can access GitHub only through a logged-in browser.

It consists of:

- a local Python daemon that manages issue state, queues, Claude sessions, and outbound replies
- a Chrome/Edge extension that fetches GitHub issue pages with browser credentials and posts comments back

## Current scope

- scans open issues authored or commented on by `tracked_user`
- only treats `tracked_user` non-`[AI]` content as user input
- maintains a per-issue Claude session
- queues a single local worker
- writes `[AI]` comments back through the extension
- supports confirmation tokens for destructive overwrite requests

## Layout

```text
github-issue-bridge/
  extension/           # Chrome/Edge MV3 extension
  src/issue_bridge/    # local daemon
  issue-bridge.example.json
```

## Local daemon quickstart

1. Create a config file:

```bash
cp issue-bridge.example.json issue-bridge.json
```

2. Adjust:

- `shared_secret`
- `repos`
- `repo_paths`
- `claude.bin`

3. Start the daemon:

```bash
PYTHONPATH=src python -m issue_bridge.main --config ./issue-bridge.json
```

4. Health check:

```bash
curl http://127.0.0.1:8765/v1/health
```

## Extension quickstart

1. Open `chrome://extensions` or `edge://extensions`
2. Enable Developer Mode
3. Load `github-issue-bridge/extension`
4. Open the popup and set:
- daemon URL
- shared secret
- repo list
- scan interval

## Endpoints

- `GET /v1/health`
- `POST /v1/issues/sync`
- `GET /v1/outbox`
- `POST /v1/outbox/ack`

## Notes

- The daemon is stdlib-only.
- The extension does not use the GitHub API; it fetches GitHub HTML through the browser session.
- The daemon serializes all work to avoid collisions in the same local checkout.
