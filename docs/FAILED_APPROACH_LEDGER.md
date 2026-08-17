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

