#!/usr/bin/env bash
# YZ ChatGPT 桥接消费端辅助库（仅调用 dev bsk，不重新开发文件桥）
# 修复版：严格状态机 + SEND_OK 验证 + 回复过滤 + Conversation 持久化
export BSK_HOME="E:/WB/tools/bsk-file-bridge/bsk-home"
# DEV 指向 shim：对 DeepSeek 会话的 upload(#upload-files) 动态改写选择器，其余透传真实 bsk
DEV="/e/WB/workspace/2026-08-16-21-49-32/work/bsk_shim.sh"
YZ_DEV_REAL="E:/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe"
COMPOSER='#prompt-textarea'
FILEINPUT='#upload-files'
SENDBTN='button[data-testid="send-button"]'
ASSISTANT='div[data-message-author-role="assistant"]'
USERMSG='div[data-message-author-role="user"]'
YZ_CONV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/YZ_WRITER_URL.txt"

# 本轮发送前后 assistant 数量（供 yz_recv_last 定位本轮新增）
YZ_ASSISTANT_BEFORE=0
# 当前 session（卡尾帧重 attach 后由 yz_recv_last 更新；调用方据此切换后续操作的 SID）
YZ_SID=""
# 当前任务唯一 ID（每次发送自动生成；回复以 ===CHATGPT_DONE:<YZ_TASK_ID>=== 结束）
YZ_TASK_ID=""
# 最近一次等待期间是否见过 stop-button（诊断用，不作为 DONE 门槛）
YZ_STOP_SEEN=0
# 最近一次等待是否进入过 SLOW_WAIT（NORMAL_WAIT 后仍未 marker，诊断用）
YZ_SLOW_WAIT=0

# ---------------------------------------------------------------------------
# 低层：DOM 读取
# ---------------------------------------------------------------------------
yz_composer_text() {
  if [ "$(yz_sid_host "$1")" = "ds" ]; then yz_ds_composer_text "$1"; return; fi
  "$DEV" evaluate --session "$1" "(()=>{const el=document.querySelector('#composer-background')||document.querySelector('form');return el?el.innerText:'';})()" 2>/dev/null
}

# 检测 prompt-textarea 是否清空（消息已发出的标志；form 含固定 UI 文本不可作判据）
yz_prompt_empty() {
  local t; t=$("$DEV" evaluate --session "$1" "(()=>{const p=document.querySelector('#prompt-textarea'); return p?((p.innerText||'').trim().length):-1;})()" 2>/dev/null | tr -d '\r\n')
  [ "$t" = "0" ] && return 0 || return 1
}

# 等页面就绪（prompt-textarea 存在即可；空输入框时 send-button 可能是语音按钮，不能作就绪判据）
yz_wait_page_ready() {
  local sid="$1"
  local dl=$(( $(date +%s) + 25 ))
  while [ "$(date +%s)" -lt "$dl" ]; do
    local st; st=$("$DEV" evaluate --session "$sid" "(()=>{const p=document.querySelector('#prompt-textarea'); return p?'READY':'NOT_READY';})()" 2>/dev/null | tr -d '\r\n')
    if [ "$st" = "READY" ]; then sleep 2; return 0; fi
    sleep 1
  done
  return 1
}

# 用原生 focus() 聚焦 composer（不用 click，避免 bsk 的 user-interrupt）
yz_focus_composer() {
  local sid="$1"
  "$DEV" evaluate --session "$sid" "(()=>{const p=document.querySelector('#prompt-textarea'); if(p){p.focus(); return 'focused';} return 'none';})()" 2>/dev/null | tr -d '\r\n'
}

yz_gen_state() {
  if [ "$(yz_sid_host "$1")" = "ds" ]; then yz_ds_gen_state "$1"; return; fi
  "$DEV" evaluate --session "$1" "document.querySelector('[data-testid=stop-button]')?'GEN':'IDLE'" 2>/dev/null
}

yz_user_count() {
  "$DEV" evaluate --session "$1" "document.querySelectorAll('$USERMSG').length" 2>/dev/null | tr -d '\r\n'
}

yz_assistant_count() {
  "$DEV" evaluate --session "$1" "document.querySelectorAll('$ASSISTANT').length" 2>/dev/null | tr -d '\r\n'
}

# 等 user message 数量增加（React 异步渲染有延迟），最多 10 秒；返回新数量或空
yz_wait_user_add() {
  local sid="$1" before="$2"
  local ua="" dl=$(( $(date +%s) + 10 ))
  while [ "$(date +%s)" -lt "$dl" ]; do
    ua=$(yz_user_count "$sid")
    if [ -n "$ua" ] && [ "$ua" -gt "$before" ]; then echo "$ua"; return 0; fi
    sleep 0.5
  done
  echo ""; return 1
}

# 最后一条 assistant 正文长度（0 表示空）
yz_reply_len() {
  "$DEV" evaluate --session "$1" "(()=>{const n=document.querySelectorAll('$ASSISTANT'); return n.length? (n[n.length-1].innerText||'').length : 0;})()" 2>/dev/null | tr -d '\r\n'
}

# 生成唯一 task_id：WB_时间戳_随机10位
yz_new_task_id() {
  printf 'WB_%s_%05d%05d' "$(date +%Y%m%d_%H%M%S)" "$((RANDOM % 100000))" "$((RANDOM % 100000))"
}

# 最后一条 assistant 是否含指定 completion marker（精确匹配，防旧 marker 误判）
yz_reply_has_marker() {
  local sid="$1" marker="$2"
  local r; r=$("$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('$ASSISTANT'); if(!n.length) return 'NO'; return (n[n.length-1].innerText||'').includes('$marker')?'YES':'NO';})()" 2>/dev/null | tr -d '\r\n')
  [ "$r" = "YES" ]
}

# 最新 user turn 是否含当前 task 控制标记 [WB_TASK:<task_id>]（发送成功的真源，不依赖 user 总数量）
yz_user_turn_has_task() {
  local sid="$1" task_id="$2"
  local tag="[WB_TASK:${task_id}]"
  local r; r=$("$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('$USERMSG'); if(!n.length) return 'NO'; return (n[n.length-1].innerText||'').includes('$tag')?'YES':'NO';})()" 2>/dev/null | tr -d '\r\n')
  [ "$r" = "YES" ]
}

# ---------------------------------------------------------------------------
# 附件等待
# ---------------------------------------------------------------------------
yz_wait_attachment() {
  local sid="$1" kw="$2" t="$3"
  local dl=$(( $(date +%s) + t ))
  while [ "$(date +%s)" -lt "$dl" ]; do
    if echo "$(yz_composer_text "$sid")" | grep -q "$kw"; then
      echo "ATTACHED"; return 0
    fi
    sleep 0.8
  done
  echo "ATTACHMENT_NOT_READY"; return 1
}

# ---------------------------------------------------------------------------
# DeepSeek 适配层（2026-09-01）：host 自适应分发，ChatGPT 路径零改动
#   约定：SID→host 映射由 yz_acquire_conv 落盘 /tmp/yz_sid_host_<sid>.txt；
#   DeepSeek 回形针选择器由 yz_acquire_conv 动态发现并落盘
#   /tmp/yz_ds_clip_<sid>.txt（bsk_shim.sh 读此文件改写 upload 的 --selector）。
# ---------------------------------------------------------------------------
yz_host_of_url() {
  case "$1" in *deepseek.com*) echo ds ;; *) echo gpt ;; esac
}

yz_sid_host() {
  local sid="$1" h=""
  [ -n "$sid" ] && h=$(tr -d '\r\n' < "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null)
  if [ -z "$h" ] && [ -n "$sid" ]; then
    local u; u=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
    h=$(yz_host_of_url "$u")
    echo "$h" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
  fi
  echo "${h:-gpt}"
}

# DeepSeek composer 容器文本（textarea 向上找含≥2按钮的容器，含附件芯片文案）
yz_ds_composer_text() {
  "$DEV" evaluate --session "$1" "(()=>{const ta=document.querySelector('textarea');if(!ta)return '';let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}return el?el.innerText:'';})()" 2>/dev/null
}

# DeepSeek 生成态：最后一条 assistant 长度双采样，变化=GEN（思考期双 -1 报 IDLE 可接受，
# acquire 复用检查与 marker 主判据均不受影响）
yz_ds_gen_state() {
  local sid="$1" JS l1 l2
  JS="(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content');return n.length?(n[n.length-1].innerText||'').length:-1;})()"
  l1=$("$DEV" evaluate --session "$sid" "$JS" 2>/dev/null | tr -d '\r\n')
  sleep 1
  l2=$("$DEV" evaluate --session "$sid" "$JS" 2>/dev/null | tr -d '\r\n')
  if [ -n "$l1" ] && [ "$l1" != "$l2" ]; then echo GEN; else echo IDLE; fi
}

yz_ds_assistant_count() {
  "$DEV" evaluate --session "$1" "document.querySelectorAll('.ds-assistant-message-main-content').length" 2>/dev/null | tr -d '\r\n'
}

yz_ds_reply_has_marker() {
  local sid="$1" marker="$2"
  local r; r=$("$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content'); if(!n.length) return 'NO'; return (n[n.length-1].innerText||'').includes('$marker')?'YES':'NO';})()" 2>/dev/null | tr -d '\r\n')
  [ "$r" = "YES" ]
}

# DeepSeek 填充：原生 setter + input 事件（普通 textarea，非 ProseMirror）
yz_ds_fill_react() {
  local sid="$1" text="$2"
  local PY="C:/Users/17838/.workbuddy/binaries/python/versions/3.13.12/python.exe"
  local jtext; jtext=$(printf '%s' "$text" | "$PY" -c "import json,sys; print(json.dumps(sys.stdin.buffer.read().decode('utf-8')))" 2>/dev/null)
  "$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return 'no-ta';const S=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;ta.focus();S.call(ta,$jtext);ta.dispatchEvent(new Event('input',{bubbles:true}));return 'set';})()" 2>/dev/null
  sleep 1
}

# DeepSeek 发送：composer 容器内 ds-button--primary JS click，textarea 清空=已提交
yz_ds_click_send() {
  local sid="$1" i dl
  for i in 1 2; do
    "$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return 'no-ta';let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}if(!el)return 'no-root';const b=[...el.querySelectorAll('div[role=button],button')].find(x=>String(x.className).includes('ds-button--primary'));if(!b)return 'no-btn';b.click();return 'CLICKED';})()" >/dev/null 2>&1
    dl=$(( $(date +%s) + 15 ))
    while [ "$(date +%s)" -lt "$dl" ]; do
      local v; v=$("$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');return ta?(ta.value||'').length:-1;})()" 2>/dev/null | tr -d '\r\n')
      [ "$v" = "0" ] && return 0
      sleep 0.5
    done
  done
  return 1
}

# DeepSeek 文本发送（与 ChatGPT 同一 task_id/marker 协议）
yz_ds_send_text() {
  local sid="$1" text="$2" timeout="${3:-300}"
  local task_id; task_id=$(yz_new_task_id)
  YZ_TASK_ID="$task_id"
  local tag="[WB_TASK:${task_id}]"
  local full="${tag} ${text} 最后一行必须严格单独输出：===CHATGPT_DONE:${task_id}==="
  local base; base=$(yz_ds_assistant_count "$sid")
  case "$base" in ''|*[!0-9]*) base=0;; esac
  local sent=NO i v
  for i in 1 2; do
    yz_ds_fill_react "$sid" "$full" >/dev/null 2>&1
    yz_ds_click_send "$sid" >/dev/null 2>&1
    local dl=$(( $(date +%s) + 15 ))
    while [ "$(date +%s)" -lt "$dl" ]; do
      v=$("$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');return ta?(ta.value||'').length:-1;})()" 2>/dev/null | tr -d '\r\n')
      if [ "$v" = "0" ]; then sent=YES; break; fi
      sleep 0.8
    done
    [ "$sent" = "YES" ] && break
  done
  if [ "$sent" != "YES" ]; then echo "SEND_FAILED"; return 1; fi
  # 回复等待：marker 主判据 + 长度稳定 25s 容错（DeepSeek 思考期无 assistant 文本不误判）
  local marker="===CHATGPT_DONE:${task_id}==="
  local start_ts hard_dl
start_ts=$(date +%s)
hard_dl=$(( start_ts + timeout ))
  local last_len="" stable_since=0 l
  while [ "$(date +%s)" -lt "$hard_dl" ]; do
    if yz_ds_reply_has_marker "$sid" "$marker"; then echo "DONE"; return 0; fi
    l=$("$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content');return n.length?(n[n.length-1].innerText||'').length:0;})()" 2>/dev/null | tr -d '\r\n')
    case "$l" in ''|*[!0-9]*) l=0;; esac
    if [ "$l" -gt 0 ]; then
      if [ "$l" != "$last_len" ]; then last_len="$l"; stable_since=$(date +%s)
      elif [ "$stable_since" -gt 0 ] && [ $(( $(date +%s) - stable_since )) -ge 25 ]; then
        echo "DONE_NO_MARKER"; return 0
      fi
    else
      last_len=""; stable_since=0
    fi
    if [ "$(date +%s)" -lt $(( start_ts + 90 )) ]; then sleep 1; else sleep 4; fi
  done
  echo "TIMEOUT"; return 1
}

# DeepSeek 回复抓取：最后一条 assistant 正文直取（操作按钮在容器外，无需剔除）
yz_ds_recv_last() {
  local sid="$1" out="$2"
  "$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content');if(!n.length)return 'REPLY_PARSE_ERROR';const t=(n[n.length-1].innerText||'').trim();return t.length?t:'REPLY_PARSE_ERROR';})()" 2>/dev/null > "$out"
}

# ---------------------------------------------------------------------------
# 核心：回复完成判定（marker 优先 + SLOW_WAIT）
#   最高优先级：最后一条 assistant 出现 ===CHATGPT_DONE:<task_id>=== 即 DONE
#   NORMAL_WAIT(normal秒)：高频轮询(0.8s)，期间没 marker 不判死
#   SLOW_WAIT：normal 秒后进入低频轮询(6s)，保持原 task/conversation，不重发不新建
#   HARD_TIMEOUT(hard秒)：从发送成功起总计超时才真正 TIMEOUT
#   stop-button 仅辅助，不作为 DONE 门槛
#   卡尾帧恢复（2026-08-17）：页面持续 IDLE 30s、本轮已有新回复、marker 仍不完整时，
#     复用抓取侧已验证的重 attach 能力（新 session + navigate 原 thread，禁止 reload、
#     禁止重发）做一次恢复读取；新页读到 marker 即 DONE 并更新 YZ_SID，
#     读不到则关闭恢复 session 继续原等待（只触发一次，正常流式生成中不会误触）。
#   DONE_NO_MARKER 容错（2026-08-18，用户授权+R 裁决）：恢复读取已尝试且失败后，
#     若本轮新回复存在、IDLE 持续 >=30s 且回复长度连续 >=20s 稳定，判定完成并输出
#     DONE_NO_MARKER（marker 仍为最高优先级；不重发、不改 SEND/CAPTURE）。
# ---------------------------------------------------------------------------
yz_wait_reply_done() {
  local sid="$1" normal="${2:-90}" hard="${3:-300}" task_id="$4" base_pre="${5:-}"
  local marker="===CHATGPT_DONE:${task_id}==="
  local stop_seen=0
  YZ_STOP_SEEN=0
  YZ_SLOW_WAIT=0
  local start_ts=$(date +%s)
  local hard_dl=$(( start_ts + hard ))
  local normal_dl=$(( start_ts + normal ))
  local idle_since=0 recovery_done=0 g cur_acount conv_url nsid rdl cur_len
  local last_len="" stable_since=0
  # assistant 基线：优先采用调用方在点击发送前采集的值（修复快回复被吞进基线的竞态，
  # 2026-08-18 用户授权+R 裁决）；调用方未传入时才回退到等待开始时采集（兼容旧调用）
  local base_acount="$base_pre"
  if [ -z "$base_acount" ]; then base_acount=$(yz_assistant_count "$sid"); fi
  case "$base_acount" in ''|*[!0-9]*) base_acount=0;; esac
  while [ "$(date +%s)" -lt "$hard_dl" ]; do
    # 最高优先级：检测到当前 task marker 立即 DONE（不要求见过 stop-button）
    if yz_reply_has_marker "$sid" "$marker"; then
      YZ_STOP_SEEN=$stop_seen
      echo "DONE"; return 0
    fi
    # stop-button 仅辅助（记录是否见过，供诊断，不作为 DONE 门槛）；同时累计 IDLE 时长
    g=$(yz_gen_state "$sid")
    if [ "$g" = "GEN" ]; then
      stop_seen=1
      idle_since=0
      last_len=""; stable_since=0
    else
      [ "$idle_since" -eq 0 ] && idle_since=$(date +%s)
      # 卡尾帧恢复读取触发条件（全部满足才触发，且只触发一次）：
      #   1) IDLE 持续 >=30s（正常慢回复处于 GEN 流式状态，不会误触）
      #   2) 本轮新回复已出现（count > 基线，排除发送后、生成启动前的空窗）
      #   3) marker 仍缺失（上面的 marker 检查未命中才会走到这里）
      if [ "$recovery_done" -eq 0 ] && [ $(( $(date +%s) - idle_since )) -ge 30 ]; then
        cur_acount=$(yz_assistant_count "$sid")
        case "$cur_acount" in ''|*[!0-9]*) cur_acount=-1;; esac
        if [ "$cur_acount" -gt "$base_acount" ]; then
          # 真正执行恢复读取才消耗"一次性"名额；条件未满足时后续 tick 继续复查
          recovery_done=1
          conv_url=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
          if [ -n "$conv_url" ] && [ "$conv_url" != "https://chatgpt.com/" ]; then
            nsid=$("$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
            if [ -n "$nsid" ]; then
              "$DEV" navigate "$conv_url" --session "$nsid" >/dev/null 2>&1
              yz_wait_page_ready "$nsid"
              rdl=$(( $(date +%s) + 15 ))
              while [ "$(date +%s)" -lt "$rdl" ]; do
                if yz_reply_has_marker "$nsid" "$marker"; then
                  YZ_SID="$nsid"
                  YZ_STOP_SEEN=$stop_seen
                  echo "DONE"; return 0
                fi
                sleep 1
              done
              "$DEV" session stop "$nsid" >/dev/null 2>&1 || true
            fi
          fi
          idle_since=0
        fi
      fi
      # DONE_NO_MARKER 容错完成路径（2026-08-18，用户授权+R 裁决）：
      #   前提=卡尾帧恢复读取已尝试过（recovery_done=1，即已给过 marker 一次额外的
      #   全新页面读取机会且失败）；其后同时满足：
      #   1) 本轮新回复存在（count > 基线）
      #   2) 恢复后 IDLE 持续 >=30s（idle_since 在恢复触发时已被清零重计）
      #   3) 回复长度 >0 且连续 >=20s 无变化（生成中长度必变，不会误判）
      #   满足即判定完成。marker 检查在每轮循环最前，优先级不变；不重发消息。
      if [ "$recovery_done" -eq 1 ]; then
        cur_acount=$(yz_assistant_count "$sid")
        case "$cur_acount" in ''|*[!0-9]*) cur_acount=-1;; esac
        if [ "$cur_acount" -gt "$base_acount" ]; then
          cur_len=$(yz_reply_len "$sid")
          case "$cur_len" in ''|*[!0-9]*) cur_len=-1;; esac
          if [ "$cur_len" -gt 0 ]; then
            if [ "$cur_len" != "$last_len" ]; then
              last_len="$cur_len"; stable_since=$(date +%s)
            elif [ "$stable_since" -gt 0 ] \
                 && [ $(( $(date +%s) - stable_since )) -ge 20 ] \
                 && [ $(( $(date +%s) - idle_since )) -ge 30 ]; then
              YZ_STOP_SEEN=$stop_seen
              echo "DONE_NO_MARKER"; return 0
            fi
          else
            last_len=""; stable_since=0
          fi
        fi
      fi
    fi
    # NORMAL_WAIT 高频，之后 SLOW_WAIT 低频（继续等原 marker，不重发）
    if [ "$(date +%s)" -lt "$normal_dl" ]; then
      sleep 0.8
    else
      YZ_SLOW_WAIT=1
      sleep 6
    fi
  done
  YZ_STOP_SEEN=$stop_seen
  echo "TIMEOUT"; return 1
}

# ---------------------------------------------------------------------------
# 发送：fill 后触发 React input/change，点击后验证 user message 数量增加
# ---------------------------------------------------------------------------
yz_fill_react() {
  local sid="$1" text="$2"
  local PY="C:/Users/17838/.workbuddy/binaries/python/versions/3.13.12/python.exe"
  # 等页面就绪（刷新/加载后 ProseMirror 需要初始化时间）
  yz_wait_page_ready "$sid"
  # JSON 编码 text，安全嵌入 JS 字符串（避免引号/换行/特殊字符破坏 JS）
  # 显式 sys.stdin.buffer.read().decode('utf-8')：不依赖 Windows/locale 默认编码
  # （本机 GBK 环境下 sys.stdin.read() 会把 UTF-8 中文/emoji 读成乱码，导致发送失败）
  local jtext; jtext=$(printf '%s' "$text" | "$PY" -c "import json,sys; print(json.dumps(sys.stdin.buffer.read().decode('utf-8')))" 2>/dev/null)
  # 用 execCommand insertText 触发 ProseMirror 的 beforeinput/input（比 fill 直接设 DOM 可靠，
  # fill 有时只改 DOM 不同步 ProseMirror，导致点击发送无效）
  "$DEV" evaluate --session "$sid" "(()=>{
    const p=document.querySelector('#prompt-textarea');
    if(!p) return 'no-prompt';
    p.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, $jtext);
    return 'inserted';
  })()" 2>/dev/null
  sleep 1.5
}

# 点击发送，返回 0 表示 prompt-textarea 已清空（消息已提交）
# 第1次 click 后轮询等 prompt 清空（最多15s），不因延迟清空立即重试 click（按钮可能已消失）
yz_click_send() {
  local sid="$1" i dl
  for i in 1 2; do
    "$DEV" click --session "$sid" "$SENDBTN" 2>&1
    dl=$(( $(date +%s) + 15 ))
    while [ "$(date +%s)" -lt "$dl" ]; do
      if yz_prompt_empty "$sid"; then return 0; fi
      sleep 0.5
    done
  done
  return 1
}

yz_send_text() {
  local sid="$1" text="$2" timeout="${3:-300}"
  if [ "$(yz_sid_host "$sid")" = "ds" ]; then yz_ds_send_text "$sid" "$text" "$timeout"; return; fi
  local task_id; task_id=$(yz_new_task_id)
  YZ_TASK_ID="$task_id"
  local tag="[WB_TASK:${task_id}]"
  local full="${tag} ${text} 最后一行必须严格单独输出：===CHATGPT_DONE:${task_id}==="
  # 点击发送前采集 assistant 基线（修复快回复被吞进基线的竞态），作为第5参数传入 wait
  local base_acount; base_acount=$(yz_assistant_count "$sid")
  case "$base_acount" in ''|*[!0-9]*) base_acount=0;; esac
  # 发送 + 用 user turn 的 [WB_TASK:task_id] 验证（不依赖 user 总数量）；失败则重新 fill 重试
  local sent=NO i
  for i in 1 2; do
    yz_fill_react "$sid" "$full" >/dev/null 2>&1
    # 提交用 JS 触发真实 send button：bsk 坐标点击可能被 browser-skill overlay 截走
    # （2026-08-17 实测：同一文本 bsk click 两次未提交，JS btn.click() 立即提交）
    "$DEV" evaluate --session "$sid" "(()=>{const b=document.querySelector('$SENDBTN'); if(b){b.click(); return 'CLICKED';} return 'NO_BTN';})()" >/dev/null 2>&1
    local dl=$(( $(date +%s) + 15 ))
    while [ "$(date +%s)" -lt "$dl" ]; do
      if yz_user_turn_has_task "$sid" "$task_id"; then sent=YES; break 2; fi
      sleep 0.8
    done
  done
  if [ "$sent" != "YES" ]; then echo "SEND_FAILED"; return 1; fi
  yz_wait_reply_done "$sid" 90 "$timeout" "$task_id" "$base_acount"
}

yz_send_file() {
  local sid="$1" file="$2" msg="$3" timeout="${4:-300}"
  local task_id; task_id=$(yz_new_task_id)
  YZ_TASK_ID="$task_id"
  "$DEV" upload --session "$sid" --selector "$FILEINPUT" --file "$file" 2>&1
  local leaf; leaf=$(basename "$file")
  local kw="${leaf%.*}"
  yz_wait_attachment "$sid" "$kw" 30 || return 1
  local tag="[WB_TASK:${task_id}]"
  local full="${tag} ${msg} 最后一行必须严格单独输出：===CHATGPT_DONE:${task_id}==="
  # 点击发送前采集 assistant 基线（修复快回复被吞进基线的竞态），作为第5参数传入 wait
  local base_acount; base_acount=$(yz_assistant_count "$sid")
  case "$base_acount" in ''|*[!0-9]*) base_acount=0;; esac
  local sent=NO i
  for i in 1 2; do
    yz_fill_react "$sid" "$full" >/dev/null 2>&1
    "$DEV" click --session "$sid" "$SENDBTN" >/dev/null 2>&1
    local dl=$(( $(date +%s) + 15 ))
    while [ "$(date +%s)" -lt "$dl" ]; do
      if yz_user_turn_has_task "$sid" "$task_id"; then sent=YES; break 2; fi
      sleep 0.8
    done
  done
  if [ "$sent" != "YES" ]; then echo "SEND_FAILED"; return 1; fi
  yz_wait_reply_done "$sid" 90 "$timeout" "$task_id" "$base_acount"
}

# ---------------------------------------------------------------------------
# 回复抓取：只提取 assistant 正文容器，排除 action bar UI 文本
#   做法：克隆 .markdown 后删除所有 <button>（编辑/复制/点赞等 UI 都是 button），
#         再取 innerText。正文里的"编辑"等文字是文本节点、不在 button 内，会保留；
#         action bar 的"编辑/复制"是 button 文本，会被删除。
# ---------------------------------------------------------------------------
yz_grab_reply() {
  local sid="$1" out="$2"
  "$DEV" evaluate --session "$sid" "(()=>{
    const n=document.querySelectorAll('$ASSISTANT');
    if(!n.length) return 'REPLY_PARSE_ERROR';
    for(let i=n.length-1;i>=0;i--){
      const md=n[i].querySelector('.markdown');
      if(!md) continue;
      const clone=md.cloneNode(true);
      clone.querySelectorAll('button').forEach(b=>b.remove());
      const holder=document.createElement('div');
      holder.style.cssText='position:absolute;left:-9999px;top:0;width:800px;';
      holder.appendChild(clone);
      document.body.appendChild(holder);
      const t=(clone.innerText||'').trim();
      document.body.removeChild(holder);
      if(t.length===0) continue;
      return t;
    }
    return 'REPLY_PARSE_ERROR';
  })()" 2>/dev/null > "$out"
}

# 抓取回复；若异常短（疑似卡尾帧），新 session 重新 attach 原 thread 重读一次
# 注意：不能 reload 当前 session——reload 后 ProseMirror 状态损坏，后续 fill 会失效；
# 正确做法是新 session + navigate 到 thread URL（全新加载，ProseMirror 正常），并更新 YZ_SID。
yz_recv_last() {
  local sid="$1" out="$2" minlen="${3:-50}"
  if [ "$(yz_sid_host "$sid")" = "ds" ]; then yz_ds_recv_last "$sid" "$out"; return; fi
  yz_grab_reply "$sid" "$out"
  local len; len=$(wc -c < "$out" 2>/dev/null | tr -d ' ')
  if [ "$len" -lt "$minlen" ]; then
    local url; url=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
    if [ -n "$url" ] && [ "$url" != "https://chatgpt.com/" ]; then
      local nsid; nsid=$("$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
      if [ -n "$nsid" ]; then
        "$DEV" navigate "$url" --session "$nsid" >/dev/null 2>&1
        yz_wait_page_ready "$nsid"
        yz_grab_reply "$nsid" "$out"
        YZ_SID="$nsid"
      fi
    fi
  fi
}

# ---------------------------------------------------------------------------
# Conversation 持久化与恢复（SID 死亡后仍回到原 Conversation）
# ---------------------------------------------------------------------------
yz_save_conv() {
  local sid="$1"
  local url; url=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
  echo "$url" > "$YZ_CONV_FILE"
  echo "$url"
}

yz_restore_conv() {
  local url; url=$(tr -d '\r\n' < "$YZ_CONV_FILE" 2>/dev/null)
  if [ -z "$url" ]; then echo "CONVERSATION_RECOVERY_FAILED"; return 1; fi
  local sid; sid=$("$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
  [ -z "$sid" ] && { echo "SESSION_LOST"; return 1; }
  "$DEV" navigate "$url" --session "$sid" 2>&1
  sleep 4
  local now; now=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
  if [ "$now" != "$url" ]; then
    echo "CONVERSATION_RECOVERY_FAILED"; return 1
  fi
  echo "$sid"
}

# ---------------------------------------------------------------------------
# Conversation tab 幂等管理：同一 conversation 只维护一个 canonical session+tab
# ---------------------------------------------------------------------------
# 获取/复用 conversation 的 session（映射文件持久化 session id，避免重复 session + tab）
yz_acquire_conv() {
  local conv_url="$1"
  local host; host=$(yz_host_of_url "$conv_url")
  local conv_id
  if [ "$host" = "ds" ]; then
    conv_id=$(echo "$conv_url" | grep -oE '/a/chat/s/[A-Za-z0-9-]+' | sed 's|/a/chat/s/||')
    [ -z "$conv_id" ] && conv_id="dsroot"
  else
    conv_id=$(echo "$conv_url" | grep -oE '/c/[A-Za-z0-9:-]+' | sed 's|/c/||')
  fi
  if [ "$host" = "ds" ]; then
    local mapfile="/tmp/yz_conv_sid_ds_${conv_id}.txt"
  else
    local mapfile="/tmp/yz_conv_sid_${conv_id}.txt"
  fi
  local sid=""
  if [ -f "$mapfile" ]; then
    sid=$(tr -d '\r\n' < "$mapfile" 2>/dev/null)
    if [ -n "$sid" ] && "$DEV" session list 2>/dev/null | grep -qE "^${sid}[[:space:]]"; then
      local url; url=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
      # 复用须再验页面 IDLE（2026-08-18 用户授权+R 裁决）：session 存活但页面卡 GEN
      # （如 hoil 故障）时 composer 不可用、发送必败；GEN 或状态读取失败(空)均不复用，
      # 落入下方新建 session 路径（不主动 stop 旧 session，交由 idle 回收）
      if [ "$url" = "$conv_url" ] && [ "$(yz_gen_state "$sid")" = "IDLE" ]; then
        echo "$host" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
        echo "$sid"; return 0
      fi
    fi
  fi
  sid=$("$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
  [ -z "$sid" ] && { echo ""; return 1; }
  "$DEV" navigate "$conv_url" --session "$sid" >/dev/null 2>&1
  if [ "$host" = "ds" ]; then sleep 6; else sleep 12; fi   # DeepSeek 加载快；ChatGPT 长历史需 10s+
  echo "$sid" > "$mapfile"
  echo "$host" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
  if [ "$host" = "ds" ]; then
    # 动态发现回形针选择器（CSS module 哈希类，构建会变，不能写死）
    local clip; clip=$("$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return '';let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}if(!el)return '';const clip=[...el.querySelectorAll('div[role=button]')].find(b=>String(b.className).includes('ds-button--capsule'));if(!clip)return '';const h=[...clip.classList].find(c=>/^[0-9a-f]{8}$/.test(c));return h?'.'+h:'';})()" 2>/dev/null | tr -d '\r\n')
    [ -n "$clip" ] && echo "$clip" > "/tmp/yz_ds_clip_${sid}.txt"
  fi
  echo "$sid"; return 0
}

# 去重当前 session 的 agent tab：同一 conversation 只保留一个 canonical；安全重复才关闭，否则报冲突
yz_dedup_conv_tabs() {
  local sid="$1" conv_url="$2"
  local conv_id; conv_id=$(echo "$conv_url" | grep -oE '/c/[A-Za-z0-9:-]+' | sed 's|/c/||')
  local PY="C:/Users/17838/.workbuddy/binaries/python/versions/3.13.12/python.exe"
  local tabs_json; tabs_json=$("$DEV" tab list --session "$sid" --json 2>/dev/null)
  local ids; ids=$(echo "$tabs_json" | "$PY" -c "
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
ids=[str(t['tab_id']) for t in d.get('tabs',[]) if t.get('scope')=='agent' and '$conv_id' in t.get('url','')]
print(' '.join(ids))
" 2>/dev/null)
  ids=$(echo "$ids" | tr -d '\r\n')
  local arr=($ids)
  local n=${#arr[@]}
  echo "matching_agent_tabs=$n"
  if [ "$n" -le 1 ]; then echo "canonical_ok"; return 0; fi
  local keep="${arr[0]}"
  local unsafe=NO
  local i tid state c g
  for ((i=1; i<n; i++)); do
    tid="${arr[$i]}"
    state=$("$DEV" evaluate --session "$sid" --tab-id "$tid" "(()=>{const p=document.querySelector('#prompt-textarea'); const c=(p?p.innerText||'':'').trim().length; const g=document.querySelector('[data-testid=stop-button]')?1:0; return c+'|'+g;})()" 2>/dev/null | tr -d '\r\n')
    c="${state%%|*}"; g="${state##*|}"
    if [ -z "$c" ] || [ "$c" != "0" ] || [ "$g" != "0" ]; then
      echo "DUPLICATE_TAB_CONFLICT tab=$tid composer=$c gen=$g"
      unsafe=YES; break
    fi
    "$DEV" tab close --session "$sid" "$tid" 2>&1 | head -1
  done
  if [ "$unsafe" = "YES" ]; then return 1; fi
  echo "dedup_done canonical=$keep"
  return 0
}
