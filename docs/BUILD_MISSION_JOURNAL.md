# Build Mission Journal

- mission_id: `a5bfb408-8ea0-4831-a46d-fffd3929eda3`
- prompt_version: `V14-FROZEN`
- prompt_hash: `sha256:6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`
- prompt_source: `C:\Users\17838\.codex\attachments\c33ac6a6-82c9-4ebb-8783-abc6ace36301\pasted-text.txt` (read in full by successor)
- stable_workspace: `E:\WB\tools\ai-production-control`
- current_build_stage: `ACCEPTANCE_A01_A65_A08A09_HUMAN_GATE`
- completed_milestones: `takeover recovery done; PRE_TAKEOVER_BACKUP at E:\WB\backups\ai-production-control-PRE_TAKEOVER_BACKUP-20260817-1750 (93 files, SHA256 manifest); git baseline 374073f52c1ba476744412ff303bb86e67c07b3f (CODEX_INTERRUPTED_STATE_BASELINE); unit tests 4/4 PASS; doctor all-PASS after TCB reseal; TCB divergence (store.py+acceptance.py edited 17:49 after gen5 seal 17:45) diagnosed and resolved via regression + reseal to generation 6 (manifest 08f606b1...)`
- modified_files: `.gitignore (secret/runtime-state exclusions added); docs/BUILD_MISSION_JOURNAL.md; config/tcb-manifest.json (gen 6)`
- important_file_hashes: `baseline commit 374073f tracks all source; tcb gen6 manifest_hash 08f606b179dfc5f42c5c0ddce77faae9aa871a44a8b6e436e388c3f3ac74e174`
- last_durable_checkpoint: `TCB_GEN6_SEALED_ACCEPTANCE_START`
- critical_build_decisions: `successor continues Codex work in place (no rewrite); backup excludes regenerable browser profile caches (~300MB) but includes control.db+snapshots+outputs; .gitignore hardened before first commit; no secrets/nested repos/reparse points found in audit`
- verified_facts: `no secrets in tree; no nested .git; 0 reparse points; canonical state rev17 hash-valid; Effect WAL 39 records verified; Authority Journal 58 events verified; A01-A65 all implemented in acceptance.py (959 lines); compileall + node --check clean`
- rejected_approaches: `see docs/FAILED_APPROACH_LEDGER.md F001-F003`
- current_hypotheses: `A03-A11 real-site cases (search/github/video/upload/download/ChatGPT) are the remaining risk: they need live browser + logged-in profile; A11/A15 CONDITIONAL may skip if condition unmet`
- open_defects: `A08/A09 blocked on ChatGPT login-state access; SOLUTION IDENTIFIED via old-bridge ENTRY_README: bsk daemon+extension on real Chrome (no Human Gate needed if user Chrome stays logged in)`
- active_risks: `real-site browser cases may hit login/CAPTCHA boundaries -> EXTERNAL_BLOCKED classification per case, not global abort`
- latest_test_results: `unittest 4/4 PASS; selftest PASS; doctor PASS (post gen6)`
- latest_review_findings: `none yet this successor session`
- next_exact_actions: `USER-PROVIDED BREAKTHROUGH: E:\WB\tools\bsk-file-bridge\reports\ENTRY_README.md (old bridge) confirms the correct A08/A09 path: bsk daemon (port 52900) + Chrome extension connects to the REAL running production Chrome (default profile, already logged into ChatGPT) - NO profile copying needed (their README explicitly forbids it, matching F004). Concrete steps for any successor: (1) start daemon non-blocking: bsk.exe daemon start --port 52900 (NOTE: it is a foreground blocking command - launch via Start-Process or background job, NOT direct RunCommand); (2) verify extension connection via bsk.exe status (project runtimes.py bsk_status already wraps this); (3) reuse yz_lib.sh proven functions (yz_acquire_conv/yz_send_text/yz_grab_reply at E:\WB\workspace\2026-08-16-21-49-32\work\yz_lib.sh) as reference for conversation acquire/send/grab via bsk; (4) route acceptance.py chatgpt_call through bsk adapter (config already has bsk_executable/bsk_home/bsk_daemon_port=52900/bsk_extension), (5) rerun acceptance -> release candidate -> digest verify -> final report. User's Chrome (16 procs) was running during takeover; bsk.exe process alive but port 52900 NOT listening yet.`
- resume_information: `read this journal + V14-FROZEN spec at prompt_source path; TCB gen6 is current; git HEAD = baseline; acceptance manifest lands in E:\WB\outputs\ai-production-control`
- latest_context_capsule_version: `capsule-via-acceptance runner pending`
- updated_at: `2026-08-17T20:10:00+08:00`

## V0.9 CLOSE 施工检查点（Builder，actor=Builder；裁决来源 = 用户 2026-08-28 裁决 + 主脑规格 V09_CLOSE_BUILD_SPEC + 裁决书 R1/R2、R18、R3/R4）

- 2026-08-28 T0 checkpoint：施工线 `v0.9-b1/authority-effect-core`，base SHA `50cf8bd1d1d36b4ebe8518b35a62a68204c4e39f`。本条随 T0 提交入库，故其自身 SHA = 本提交（记于下一检查点）。
  - 入库：`docs/specs/V14-FROZEN-EXECUTION-SPEC.txt`（sha256 `6fe3bb79…154df6`，逐字节）、`docs/SPEC_ANCHOR_REPORT.md`、`docs/RED_ADJUDICATION_MATRIX.md`、6 个治理文件（源 f74d48e，blob 级逐字节一致）、冻结测量件 2 件（夹具仅 +1 行 `spec_anchor`）。
  - `PROJECT_STATE.spec_registry` 登记 1 条，status=`COMMITTED`；孪生 `PROJECT_STATE.md` 同步。
  - 适配运行器 `runtime/test_v09_attack_matrix_on_b1_core.py`（AD-1..AD-5）首测：36 例 matched=25 / red=11，R34 忠实探针 MISMATCH（未知类型端到端 ALLOW）。
  - `python scripts/state_doctor.py` = `DRIFT_FREE`（exit 0），残留 WARN 仅 journal staleness（裁决书 §2 预告合法）。
  - `RELEASE_STATUS` 维持 `PRODUCT_NOT_READY`；TCB 处于 `UNVERIFIED_AFTER_CONTROLLER_CHANGE`（代码任务尚未开始，T0 未触碰 `src/`）。
- 2026-08-28 TASK-1..TASK-5 checkpoint：code commits `26014c06`(TASK-1) `3e67f261`(TASK-2) `df6492b5`(TASK-3)
  `6cb04b05`(TASK-4) `c6d1a55b`(TASK-5)。适配运行器 36/36 matched、R34 忠实探针 FAIL_CLOSED；
  `tests/` 137 ran 与基线同 2F+8E（零新增）；`runtime/` 全量逐文件与基线逐项同值。
  CLOSE 单测 40 例 OK。`state/branch_registry.json` 仅同步 v0.9-b1 head 字段（裁决书 §3.3）。
- TCB 重封**未执行**（如实记录）：`security.seal_tcb` 为既有机制，但其目标 `code_root`/`state_root`
  指向 `E:\WB\tools|state\ai-production-control` —— 本机为**另一个检出与在产状态**，
  从中封印得到的 manifest 描述的并非本候选代码树，且会写入活的 Controller 状态。
  故封印推迟到由发布负责人在权威 code_root/state_root 配对上执行；
  本线 TCB 状态如实维持 `UNVERIFIED_AFTER_CONTROLLER_CHANGE`（AGENTS.md 要求），
  且"封印是否成立"不属 Builder 判定（裁决书 §3.5）。
- 2026-08-28 Tier 2 checkpoint（commit 042c9aca + 本条）：
  (c) 已归因并闭环——e8c53d4 只读对照 5/5 绿、b1 红，但根因是夹具缺 b1 必需绑定
      （intent 缺 effect_type/data_classification、scope 缺 identity；探针实测 action rows=0），
      属 AD-6 测试适配，产品代码未动（动它即破 V09-R33）。裁决书 §5(c) 的"能力回归"假设已被推翻。
  (a) 已闭环——7 个 self-grant 测试方法（8 实例）经 AD-6 转绿；`tests/` 全量 137 ran / 0 fail / 0 error。
  (b) HARD STOP——9 例 egress 判定为缺陷（egress 许可 key 无生产者），未改测试、未改期望，见 D010。
