# Development Tasks

## Completed MVP

- [x] Create standalone project directory `github-issue-bridge`
- [x] Add Python daemon package and entry point
- [x] Add JSON config example
- [x] Implement daemon endpoints:
  - `GET /v1/health`
  - `POST /v1/issues/sync`
  - `GET /v1/outbox`
  - `POST /v1/outbox/ack`
- [x] Implement persistent issue state and outbox storage
- [x] Implement single-worker queue
- [x] Implement Claude runner skeleton with session resume support
- [x] Implement confirmation-token flow for destructive overwrite requests
- [x] Add Chrome/Edge MV3 extension skeleton
- [x] Implement extension scan cycle:
  - fetch GitHub search pages
  - fetch issue detail pages
  - sync issues to daemon
  - poll daemon outbox
  - post comments back to GitHub

## Next Tasks

- [ ] Harden GitHub HTML selectors against more page variants
- [ ] Add extension-side log viewer in popup
- [ ] Add daemon-side richer audit logs per issue
- [ ] Add retry backoff metadata for outbox failures
- [ ] Add unit tests for marker calculation and confirmation-token flow
- [ ] Add a helper script contract for zip-download repo refresh
- [ ] Add repo-specific hooks and policy controls
- [ ] Add support for label/close actions if later needed

## Verification Done

- [x] Python syntax check with `py_compile`
- [x] Extension JS syntax check with `node --check`
- [x] Local daemon boot test and `GET /v1/health`
