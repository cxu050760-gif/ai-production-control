# Data Egress Policy

Classifications: `PUBLIC`, `INTERNAL`, `PRIVATE_LOCAL`, `SENSITIVE`, `SECRET`, `UNKNOWN`.

- `UNKNOWN` is treated as `PRIVATE_LOCAL`.
- Derived summaries, snippets, screenshots, DOM, logs, traces, capsules, prompts, evidence, and archives inherit their source classification unless explicitly reclassified by policy.
- `SECRET` never enters ordinary Brain prompts, browser evidence, capsules, logs, or screenshots.
- Egress is destination-, provider-, purpose-, Goal Contract-, and authorization-specific. Permission for one provider does not authorize another.
- Browser-profile credentials are consumed only by the Browser Runtime. Workers receive references, not cookies or tokens.
- Local full capsules and externally redacted capsules are distinct artifacts.

