# AI Production Control Plane working rules

- Treat `src/aicontrol`, `ai-control.cmd`, `scripts`, `config/production.json`, and `package-lock.json` as Controller TCB.
- Do not place credentials, cookies, tokens, authentication headers, or browser-profile contents in prompts, logs, evidence, or commits.
- Workers may write only their task workspace and proposal/result files. They must not write Controller state, journals, policy, acceptance, or release records.
- All production external writes go through Controller authorization, logical-effect reservation, Effect WAL, and the Effect Gate.
- Use structured process execution (`executable` plus `argv`) with `shell=False` semantics.
- Preserve the separate state and output roots declared in `config/production.json`.
- Never edit `E:\WB\tools\bsk-file-bridge` or `E:\AI_Projects\ChatGPT_Codex_Bridge` from this project; they are adapters/reuse assets only.
- A changed TCB is `UNVERIFIED_AFTER_CONTROLLER_CHANGE` until the complete required regression is rerun and a new TCB manifest is sealed.

