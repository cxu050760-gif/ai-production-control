#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# yz_ds_lib.sh — DeepSeek 网页端独立驱动(2026-09-01)
# 由 runtime.py 按 r_url host 选择:chat.deepseek.com 的 RUN 专用本库,
# 与 ChatGPT 的 yz_lib.sh 完全独立、接口同名,互不影响。
#
# 附件通道 = PR #123 chooser 事务(点击回形针→拦截文件选择器→注入),
# 回形针选择器为 CSS module 哈希类(每次 DeepSeek 构建会变,不可写死),
# 由 yz_acquire_conv 每会话动态发现并落盘,bsk_shim.sh 据此改写
# upload 的 '#upload-files' 占位选择器。ChatGPT 路径永不加载本库。
# ---------------------------------------------------------------------------
set -u
export BSK_HOME="E:/WB/tools/bsk-file-bridge/bsk-home"
DEV="/e/WB/workspace/2026-08-16-21-49-32/work/bsk_shim.sh"
YZ_DEV_REAL="E:/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe"
COMPOSER='textarea'
ASSISTANT='.ds-assistant-message-main-content'
FILEINPUT='#upload-files'   # 占位:shim 按 /tmp/yz_ds_clip_<sid>.txt 动态改写
YZ_SID=""

# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
yz_new_task_id() {
  printf 'WB_%s_%05d%05d' "$(date +%Y%m%d_%H%M%S)" "$((RANDOM % 100000))" "$((RANDOM % 100000))"
}

# DeepSeek composer 容器文本(textarea 向上找含≥2按钮的容器,再上提一级以包住附件芯片行;
# 2026-09-01 实测层级:L1=模式键行,L2=芯片+模式键,L5 起窜入消息区,故取 L2)
yz_composer_text() {
  "$DEV" evaluate --session "$1" "(()=>{const ta=document.querySelector('textarea');if(!ta)return '';let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}if(!el)return '';const card=el.parentElement||el;return card.innerText||'';})()" 2>/dev/null
}

# 生成态:最后一条 assistant 长度双采样,变化=GEN
# (思考期采样双 -1 报 IDLE 可接受:发送等待以 marker 为主判据,不依赖此函数)
yz_gen_state() {
  local sid="$1" JS l1 l2
  JS="(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content');return n.length?(n[n.length-1].innerText||'').length:-1;})()"
  l1=$("$DEV" evaluate --session "$sid" "$JS" 2>/dev/null | tr -d '\r\n')
  sleep 1
  l2=$("$DEV" evaluate --session "$sid" "$JS" 2>/dev/null | tr -d '\r\n')
  if [ -n "$l1" ] && [ "$l1" != "$l2" ]; then echo GEN; else echo IDLE; fi
}

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
# 发送内部件
# ---------------------------------------------------------------------------
yz_ds_assistant_count() {
  "$DEV" evaluate --session "$1" "document.querySelectorAll('.ds-assistant-message-main-content').length" 2>/dev/null | tr -d '\r\n'
}

yz_ds_reply_has_marker() {
  local sid="$1" marker="$2"
  local r; r=$("$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content'); if(!n.length) return 'NO'; return (n[n.length-1].innerText||'').includes('$marker')?'YES':'NO';})()" 2>/dev/null | tr -d '\r\n')
  [ "$r" = "YES" ]
}

# 填充:原生 setter + input 事件(普通 textarea,非 ProseMirror)
yz_ds_fill_react() {
  local sid="$1" text="$2"
  local PY="C:/Users/17838/.workbuddy/binaries/python/versions/3.13.12/python.exe"
  local jtext; jtext=$(printf '%s' "$text" | "$PY" -c "import json,sys; print(json.dumps(sys.stdin.buffer.read().decode('utf-8')))" 2>/dev/null)
  "$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return 'no-ta';const S=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;ta.focus();S.call(ta,$jtext);ta.dispatchEvent(new Event('input',{bubbles:true}));return 'set';})()" 2>/dev/null
  sleep 1
}

# 发送:composer 容器内 ds-button--primary JS click;textarea 清空=已提交
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

# ---------------------------------------------------------------------------
# 文本发送(与 ChatGPT 同一 task_id / ===CHATGPT_DONE=== marker 协议)
# ---------------------------------------------------------------------------
yz_send_text() {
  local sid="$1" text="$2" timeout="${3:-300}"
  local task_id; task_id=$(yz_new_task_id)
  YZ_TASK_ID="$task_id"
  local tag="[WB_TASK:${task_id}]"
  local full="${tag} ${text} 最后一行必须严格单独输出：===CHATGPT_DONE:${task_id}==="
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
  # 回复等待:marker 主判据 + 长度稳定 25s 容错
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

# ---------------------------------------------------------------------------
# 回复抓取:最后一条 assistant 正文直取(操作按钮在容器外,无需剔除)
# ---------------------------------------------------------------------------
yz_recv_last() {
  local sid="$1" out="$2"
  YZ_SID="$sid"
  "$DEV" evaluate --session "$sid" "(()=>{const n=document.querySelectorAll('.ds-assistant-message-main-content');if(!n.length)return 'REPLY_PARSE_ERROR';const t=(n[n.length-1].innerText||'').trim();return t.length?t:'REPLY_PARSE_ERROR';})()" 2>/dev/null > "$out"
}

# ---------------------------------------------------------------------------
# 会话获取/复用
# ---------------------------------------------------------------------------
yz_acquire_conv() {
  local conv_url="$1"
  local conv_id; conv_id=$(echo "$conv_url" | grep -oE '/a/chat/s/[A-Za-z0-9-]+' | sed 's|/a/chat/s/||')
  [ -z "$conv_id" ] && conv_id="unknown"
  local mapfile="/tmp/yz_conv_sid_ds_${conv_id}.txt"
  local sid=""
  if [ -f "$mapfile" ]; then
    sid=$(tr -d '\r\n' < "$mapfile" 2>/dev/null)
    if [ -n "$sid" ] && "$DEV" session list 2>/dev/null | grep -qE "^${sid}[[:space:]]"; then
      local url; url=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
      # 复用须再验页面 IDLE(2026-08-18 用户授权+R 裁决):卡 GEN 时不复用,走新建
      if [ "$url" = "$conv_url" ] && [ "$(yz_gen_state "$sid")" = "IDLE" ]; then
        echo "ds" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
        echo "$sid"; return 0
      fi
    fi
  fi
  # session start 偶发挂死(后台/无 TTY 环境,2026-09-01):超时 45s + 一次重试
  sid=$(timeout 45 "$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
  [ -z "$sid" ] && sid=$(timeout 45 "$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
  [ -z "$sid" ] && { echo ""; return 1; }
  "$DEV" navigate "$conv_url" --session "$sid" >/dev/null 2>&1
  sleep 6   # DeepSeek 加载快
  echo "$sid" > "$mapfile"
  echo "ds" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
  # 动态发现回形针选择器(CSS module 哈希类,构建会变,不可写死)
  local clip; clip=$("$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return '';let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}if(!el)return '';const clip=[...el.querySelectorAll('div[role=button]')].find(b=>String(b.className).includes('ds-button--capsule'));if(!clip)return '';const h=[...clip.classList].find(c=>/^[0-9a-f]{8}$/.test(c));return h?'.'+h:'';})()" 2>/dev/null | tr -d '\r\n')
  [ -n "$clip" ] && echo "$clip" > "/tmp/yz_ds_clip_${sid}.txt"
  echo "$sid"; return 0
}
