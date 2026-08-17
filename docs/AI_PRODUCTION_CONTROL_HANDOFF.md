# AI Production Control Handoff

Start with `NEW_WORKER_START_HERE.md` for a Worker, or `README.md` for an operator. The Controller source is under `src/aicontrol`; state and evidence are outside the code tree. `config/production.json` is the production routing/configuration source. `doctor`, `selftest`, and the A01-A65 acceptance manifest are the current evidence boundaries. Do not treat historical BrowserSkill/Bridge reports as current runtime acceptance without re-running their live checks.

