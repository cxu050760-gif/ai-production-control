# Status

- Mission: provider-independent AI production system controlled by durable canonical state and evidence.
- Current stage: `v1.1-blackbox` hardening on branch `hardening/p0-gates-20260831`.
- Single source of truth: `PROJECT_STATE.json` (validated by `scripts/state_doctor.py`); `PROJECT_STATE.md` is a frozen historical snapshot of the V1.0 close (2026-08-30) and no longer updated.
- North star: real L3 closed loop ACHIEVED — RUN-20260831-120044-0e45 completed with a real independent R review PASS.
- BLK-2 resolved: 8 real GOAL runs all PASS.
- Known issue: 2 wiring tests fail due to lease pollution; fix in progress under GATE-3.
- Official Runtime Entry: `E:\WB\tools\ai-production-control\runtime\run.cmd` (unchanged).
