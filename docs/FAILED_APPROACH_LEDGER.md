# Failed Approach Ledger

## F001 — Depend on Windows Computer Use as the primary browser backend

- why_failed: Current environment evidence supports discovery/screenshots but not reliable unattended input confirmation or recovery.
- component/version: bundled computer-use 26.721.41059 with a previously diagnosed helper-version mismatch.
- do_not_retry_unless: component versions change and a dedicated input/recovery regression passes.
- status: REJECTED

## F002 — Make the existing ChatGPT-Codex Bridge the new Controller

- why_failed: Its contract intentionally excludes arbitrary shell/path/model/network control and its live tunnel was not current-verified; changing it would violate its preserved architecture boundary.
- do_not_retry_unless: the Bridge owner explicitly changes its public scope.
- status: REJECTED

## F003 — Make BrowserSkill the only browser backend

- why_failed: The current dev daemon initially had zero connected browsers and the existing fork explicitly lacks general download support.
- do_not_retry_unless: download support and a live connected-browser doctor are verified.
- status: REJECTED_AS_SOLE_BACKEND

## F004 — Refresh automation-profile ChatGPT login by copying production browser cookies

- why_failed: Chrome v20 app-bound encryption binds cookie decryption to the originating browser install/profile context; cookies copied from production Chrome (or Edge) into the CFT/automation profile are silently undecryptable. Verified empirically twice on 2026-08-17: copied fresh prod session-token cookies (created 2026-08-17T10:21Z, valid to 2026-11-15) into browser-auth-profile-v2 and launched with CFT chrome AND with real installed chrome.exe — both showed AUTH_EXPIRED (login_visible=true, composer_count=0). CFT-run on the copy discarded all v20 cookies and rewrote 11 v10 cookies.
- component/version: Chrome stable (all cookies v20 app-bound), chrome-for-testing bundled with bsk-file-bridge.
- do_not_retry_unless: Chrome changes app-bound encryption semantics, or an in-place login in the automation browser itself is performed (Human Gate), or BrowserSkill attaches to the real logged-in production browser.
- status: REJECTED (login-state reuse must happen inside the automation browser itself; legitimate Human Gate per V14 §105)
