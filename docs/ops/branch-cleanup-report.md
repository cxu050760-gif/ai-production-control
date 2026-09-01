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
