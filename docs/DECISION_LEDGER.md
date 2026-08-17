# Decision Ledger

## D001 — Stable placement

- decision: Place the Controller under `E:\WB\tools`, with separate `E:\WB\state` and `E:\WB\outputs` roots.
- reason: It is a reusable WorkBuddy-adjacent production tool, not a fourth workspace hierarchy or a timestamped build directory.
- evidence: Target paths were absent before creation; the existing three-layer workspace contract assigns WorkBuddy tooling to `E:\WB`.
- status: ACTIVE

## D002 — Controller runtime

- decision: Use Python 3.12 standard-library SQLite for the authoritative Controller and Node 20 plus pinned `playwright-core` only for the browser adapter.
- reason: SQLite supplies transactional durability and append-oriented journals without a server; the installed Python and Node versions are verified. Playwright supplies mature browser semantics without adding an Agent framework.
- evidence: Python 3.12.10, Node 20.18.1, npm 10.8.2; `playwright-core@1.62.1` requires Node >=20.
- status: ACTIVE

## D003 — Browser collision resolution

- decision: PRIMARY=`Playwright/CDP` with a dedicated persistent profile; FALLBACK=`BrowserSkill bsk 0.1.10` for authenticated/profile-aware operations and its verified upload extension.
- reason: Playwright gives broad navigation/input/tab/download/media coverage; BrowserSkill preserves existing logged-in-browser and upload assets. Chrome DevTools MCP is an agent-facing MCP/debug surface rather than the embedded Controller library, and browser-use adds an LLM Agent layer that this Controller already owns.
- evidence: local BrowserSkill 0.1.10 binary and extension 0.1.5 hashes recorded in inventory; its current daemon had zero connected browsers at inventory time, so it cannot be the sole backend.
- status: ACTIVE

## D004 — Existing Bridge reuse boundary

- decision: Do not replace or modify `ChatGPT_Codex_Bridge`; reuse its acceptance-gating and bounded-artifact lessons, while the new Controller remains a separate local runtime.
- reason: The Bridge is an 18-tool restricted MCP bridge with its own public contract and live-tunnel acceptance boundary, not a general effect/authority Controller.
- status: ACTIVE

