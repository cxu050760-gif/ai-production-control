# 废弃分支清点报告（2026-09-01）

> 只报告，不删除。本报告供审查/裁决后由授权方决定是否清理。
> 数据来源：`git log master..<branch>`、`git diff master...<branch> --stat`（2026-09-01 于生产仓实测）。

## 汇总表

| 分支 | 独有提交数 | 相对 master 落后提交数 | 合并基（merge-base） | 结论 |
|---|---|---|---|---|
| `origin/tmp-unused` | 0 | 111 | `da6ab1e`（master 的祖先） | **可安全删除** |
| `origin/tmp-unused2` | 0 | 111 | `da6ab1e`（master 的祖先） | **可安全删除** |
| `origin/tmp-v09-ignore` | 4 | 97 | `e8c53d4a`（master 的祖先） | **需人工确认** |

---

## 1. origin/tmp-unused

- 指向：`da6ab1e5ebd671914d5b964a9b6ae51d10a80da8`（2026-08-27 22:06:06 +0800，`test(v0.8/b3): add evidence self-tests`）
- `git log master..origin/tmp-unused`：**无独有提交**（空）
- `git rev-list --left-right --count master...origin/tmp-unused`：`111 0`（master 领先 111，分支领先 0）
- `git merge-base master origin/tmp-unused` = `da6ab1e`，且 `git merge-base --is-ancestor da6ab1e master` 为真 → 该分支是 master 的祖先
- `git diff master...origin/tmp-unused --stat`：空（无差异）
- **结论：可安全删除**。该分支无任何 master 上不存在的提交，删除不丢失任何内容。

## 2. origin/tmp-unused2

- 指向：`da6ab1e5ebd671914d5b964a9b6ae51d10a80da8`（与 `tmp-unused` 完全相同）
- `git log master..origin/tmp-unused2`：**无独有提交**（空）
- `git rev-list --left-right --count master...origin/tmp-unused2`：`111 0`
- `git merge-base master origin/tmp-unused2` = `da6ab1e`，且是 master 的祖先
- `git diff master...origin/tmp-unused2 --stat`：空
- **结论：可安全删除**。与 `tmp-unused` 指向同一提交，内容完全被 master 覆盖，删除不丢失任何内容。

## 3. origin/tmp-v09-ignore

- 指向：`f9ffbb3f398726636c58001a2b838dfd97fe0a2f`（2026-08-28 11:56:00 +0800）
- 合并基：`e8c53d4a2d6d6ce1d57a34472170c01577e15d6c`（`v0.8-integrate/adapter-final-4`，master 的祖先）
- 独有提交（`git log master..origin/tmp-v09-ignore`，按时间升序）：

| 哈希 | 时间 | 提交说明 |
|---|---|---|
| `14578be` | 2026-08-28 11:45:24 +0800 | ci(v0.9): bootstrap formal B2 replay verification |
| `692df25` | 2026-08-28 11:53:52 +0800 | ci(v0.9): correct B2 RED source gate |
| `41b6984` | 2026-08-28 11:55:05 +0800 | ci(v0.9): export validated B2 formal source bundle |
| `f9ffbb3` | 2026-08-28 11:56:00 +0800 | ci(v0.9): bind speculative replay source for export |

- `git diff master...origin/tmp-v09-ignore --stat`：仅 1 个文件
  - `.github/workflows/v09-authority-effect-verify.yml`（+215）
- **结论：需人工确认**。该分支含 4 个独有提交，唯一差异是新增了一个 CI workflow 文件（`.github/workflows/v09-authority-effect-verify.yml`，215 行）。该 workflow 未被 master 采用。删除前需确认：
  1. 该 B2 正式 replay 验证 workflow 是否仍有保留价值（是否会被重新启用）；
  2. 若确认弃用，则可安全删除；若未来可能复用，建议保留或归档。

---

## 附注

- 本报告仅做清点与结论建议，**未执行任何删除**。
- 任何删除动作须在审查（Reviewer）裁决后由授权方执行，遵守"禁止破坏性操作"纪律。
- 相关待裁决项已登记：`PROJECT_STATE.json` open_questions Q6。


---

## 阶段 D 执行记录（2026-09-01，合并后主线 merge/hardening-20260901@76f2188 为基准）

### 本地分支删除（已执行）
对 `git branch --merged merge/hardening-20260901` 确认完全合入的本地分支执行 `git branch -d`。已删除 7 个：

| 分支 | 原 head | 说明 |
|---|---|---|
| docs/state-sync-20260901 | a33b6d4 | 上一轮状态同步分支，已 fast-forward 合入 master |
| v0.6-b/ec-failclosed | 7e25ddf | 已合入主线 |
| v0.6-c/telemetry-replay2 | 9d94dd4 | 已合入主线 |
| v0.6-c/telemetry-replay3 | fd99281 | 已合入主线 |
| v0.6-int/relay-merge | fd99281 | 已合入主线 |
| v0.7-c/c-correction-1 | cad2977 | 已合入主线 |
| v0.7-sb/strategic-brain-1 | 576756a | 已合入主线 |

### 本地分支保留（因 worktree 占用，无法删除）
以下 5 个分支确认 merged 但被 `E:/WB/temp/` 下的 git worktree 占用（`git branch -d` 拒绝），**保留并需人工先移除 worktree 再删除**：
- review-result-return（worktree E:/WB/temp/review_result_return/worktree）
- slice-c/goal-contract-lite-v2（E:/WB/temp/slice_c_v2/worktree）
- slice-i/effect-safety-lite（E:/WB/temp/slice_i/worktree）
- transport-recovery-lite（E:/WB/temp/transport_recovery_lite/worktree）
- v0.7-sr/strategic-reuse-1（E:/WB/temp/slice_j2/worktree）

### 本地分支保留（未合入）
以下分支 `git branch --no-merged merge/hardening-20260901` 确认有未合入提交，**保留并在报告中说明**：
- slice-j2/send-guard、slice-v0.6/ec-lite、v0.5-b/pass-invalidation、v0.5-c/evidence-registry、v0.5-c/evidence-registry-replay1、v0.5-int/relay-merge、v0.6-c/telemetry-replay、v0.7-int/relay-merge

### 保留的安全/主干分支
- master、merge/hardening-20260901（当前）、backup/master-pre-hardening-merge（合并前备份指针）

### 远端分支（计划）
任务书授权远端删除仅限 origin/tmp-* 三个：
- origin/tmp-unused、origin/tmp-unused2：**已确认 merged（master 祖先 da6ab1e，无独有提交）→ 计划删除**
- origin/tmp-v09-ignore：**未合入（4 个独有提交，workflow 文件）→ 保留，需人工确认**

### branch_registry 对齐（已更新）
- 删除 7 个已删分支条目；master head → 76f2188；hardening/p0-gates-20260831 → ARCHIVE（head cce2ca6）；v1.1-blackbox → ARCHIVE；追加 merge/hardening-20260901（TRUNK_CANDIDATE）、backup/master-pre-hardening-merge（ARCHIVE）。

> 本执行记录遵循任务书纪律：仅删 `--merged` 确认完全合入的分支；未合入一律保留；远端删除仅限 tmp-unused/tmp-unused2（tmp-v09-ignore 保留待裁决）。


---

## 处置记录（2026-09-01 终局收尾）

**origin/tmp-v09-ignore 已删除**（用户授权，终局微任务）：
- 前置核验：本报告第 3 节已记录其 4 个独有提交（f9ffbb3/41b6984/692df25/14578be，v0.9 时代猜测性 CI workflow）；主线已由其他路径合并，验证方式已被矩阵 v4 取代。
- 执行：本地无该分支（仅有远端跟踪，无需 git branch -D）；远端 `git push origin --delete tmp-v09-ignore` → 输出 `- [deleted] tmp-v09-ignore`；`git fetch origin --prune` 后 origin/tmp-* 清空。
- 至此 origin/tmp-unused、origin/tmp-unused2、origin/tmp-v09-ignore 三个废弃分支全部删除完毕（前两个在阶段 D 删除，本次删除最后一个）。
- branch_registry 中 tmp-v09-ignore 条目同步移除。
