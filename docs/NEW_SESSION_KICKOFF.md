# 新会话接手启动指令（给任何新 AI，配合三份文件使用）

## 按顺序读这三份
1. 唯一正式规格 V14-FROZEN：
   `C:\Users\17838\.codex\attachments\c33ac6a6-82c9-4ebb-8783-abc6ace36301\pasted-text.txt`
2. 交接报告（含能力矩阵审计、死路清单、12 步关键路径）：
   `E:\WB\tools\ai-production-control\docs\SUCCESSOR_HANDOFF_REPORT.md`
3. 任务日志：
   `E:\WB\tools\ai-production-control\docs\BUILD_MISSION_JOURNAL.md`

## 铁律
- 这是断点续建，不是新项目。禁止重做/重设计/新建 V15+。
  以磁盘真实状态为准：`git log` 应见 0b6d1b3 及更早 7 个 commit。
- 动任何代码前先跑 `.\ai-control.cmd doctor` 和 `selftest`，确认基线全绿。
- **核心目标 = 通用浏览器全自动化（所有网页）。ChatGPT 只是高难度样本，
  不是目标本身。** 禁止把"接通 ChatGPT"当成任务终点。

## 工作优先级（详见交接报告 §4.0.5 / §4.1）
1. 补富编辑器能力缺口（ProseMirror 类，实验室现用普通 div 顶替）
2. bsk 通道接入（daemon 后台启动！前台跑会挂死会话）
3. ChatGPT 作为高难度站点 #1 验证（A08/A09 真实 PASS，A18 真实主脑重跑）
4. 真实站点稳定性：连续 ≥5 轮全通过 + 断连恢复 + 慢响应
5. 独立 Brain 终审 → 修复 → 复审
6. 全量回归 → Release Candidate → 四 digest 一致 → §134 最终报告

## 防放水规则
- 实现与验收判定不得同源（不许自写自评）
- A18 必须真实 ChatGPT 主脑；fallback 顶替不算 PASS
- 已证伪路径 F001-F004 见交接报告 §5，不要重试

## 过程纪律
- 每完成一步：更新 BUILD_MISSION_JOURNAL.md + git commit
- 遇真实外部边界（登录/CAPTCHA/2FA）才找用户，其余自行继续
