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
#
# 三模式(2026-09-01 侦察结论):
#   新对话页(homepage)有三个模式胶囊:快速模式/专家模式/识图模式,
#   选中态 = 容器上独有的 CSS module class(哈希不可写死,用"独有 token"判定);
#   模式绑定会话,中途不可切换(顶栏 tooltip "如需切换模式，请开启新对话");
#   会话页顶栏标签文本 = 当前模式名。
#   因此模式在 acquire/reattach 阶段强制:不匹配 → 导航到新对话页选模式 →
#   本次发送会产生新会话 URL → yz_ds_finalize_new_conv 落盘并由
#   runtime.py 按 RUNTIME_NEW_URL 重定向 RUN。
# ---------------------------------------------------------------------------
set -u
export BSK_HOME="E:/WB/tools/bsk-file-bridge/bsk-home"
DEV="/e/WB/workspace/2026-08-16-21-49-32/work/bsk_shim.sh"
YZ_DEV_REAL="E:/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe"
COMPOSER='textarea'
ASSISTANT='.ds-assistant-message-main-content'
FILEINPUT='#upload-files'   # 占位:shim 按 /tmp/yz_ds_clip_<sid>.txt 动态改写
YZ_SID=""

DS_MODE_LABEL_fast='快速模式'
DS_MODE_LABEL_expert='专家模式'
DS_MODE_LABEL_vision='识图模式'

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

# 单文件附件注入(含一次重试): chooser 拦截在模式选择后偶发未就绪(2026-09-01 T2
# 实测:脚本紧跟模式选择即上传报 "upload trigger did not activate an input[type=file]",
# 页面稳定后手动重试即成功),失败等 3s 重发现选择器再试一次。
yz_ds_upload_once() {
  local sid="$1" file="$2"
  local up i rc
  for i in 1 2; do
    yz_ds_discover_clip "$sid"
    up=$("$DEV" upload --session "$sid" --selector "$FILEINPUT" --file "$file" 2>&1)
    rc=$?
    [ "$rc" -eq 0 ] && { printf '%s' "$up"; return 0; }
    [ "$i" = "1" ] && sleep 3
  done
  printf '%s' "$up"; return 1
}

# 附件就绪检测(2026-09-01 T2 实测双形态):
#   文件类附件 = composer 文本芯片(含文件名);
#   识图模式图片附件 = composer 卡内 blob:/data: 缩略图,无文件名文本。
# 任一形态出现即算 ATTACHED。接口与 yz_lib.sh 同名同参,模板零改动。
yz_wait_attachment() {
  local sid="$1" kw="$2" t="$3"
  local dl=$(( $(date +%s) + t ))
  while [ "$(date +%s)" -lt "$dl" ]; do
    if echo "$(yz_composer_text "$sid")" | grep -q "$kw"; then
      echo "ATTACHED"; return 0
    fi
    local n; n=$("$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return 0;let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}if(!el)return 0;const card=el.parentElement||el;return [...card.querySelectorAll('img')].filter(im=>{const s=String(im.src||'');return s.startsWith('blob:')||s.startsWith('data:');}).length;})()" 2>/dev/null | tr -d '\r\n')
    case "$n" in ''|*[!0-9]*) n=0;; esac
    [ "$n" -gt 0 ] && { echo "ATTACHED"; return 0; }
    sleep 0.8
  done
  echo "ATTACHMENT_NOT_READY"; return 1
}

# ---------------------------------------------------------------------------
# 三模式:读取当前页模式 / 选择模式 / 确保模式 / 新会话 URL 收尾
# ---------------------------------------------------------------------------

# 当前页模式 → fast|expert|vision|unknown
# 1) 新对话页:三个模式胶囊容器(=精确文本 span 的 parent.parent)中
#    拥有"其余两个都没有的 class token"者即选中态;
# 2) 会话页:顶栏精确文本(快速模式/专家模式/识图模式)取最上方可见者。
yz_ds_page_mode() {
  local sid="$1"
  "$DEV" evaluate --session "$sid" "(()=>{const M={'快速模式':'fast','专家模式':'expert','识图模式':'vision'};const L=Object.keys(M);const sp=L.map(t=>{const s=[...document.querySelectorAll('span,div')].find(e=>e.childElementCount===0&&(e.innerText||'').trim()===t);if(!s)return null;const o=s.parentElement&&s.parentElement.parentElement;return o?{t:t,cls:String(o.className)}:null;});const pills=sp.filter(Boolean);if(pills.length===3){const cnt={};pills.forEach(p=>String(p.cls).split(/\\s+/).forEach(c=>{if(c)cnt[c]=(cnt[c]||0)+1;}));for(const p of pills){const u=String(p.cls).split(/\\s+/).find(c=>cnt[c]===1);if(u)return M[p.t]||'unknown';}}const cand=[...document.querySelectorAll('span,div')].filter(e=>e.childElementCount===0&&L.includes((e.innerText||'').trim())&&e.getBoundingClientRect().width>5).sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);if(cand.length)return M[(cand[0].innerText||'').trim()]||'unknown';return 'unknown';})()" 2>/dev/null | tr -d '\r\n'
}

# 在新对话页点击指定模式胶囊并校验选中态(点两次容错)
yz_ds_select_mode() {
  local sid="$1" mode="$2"
  local lv="DS_MODE_LABEL_${mode}"
  local label="${!lv:-}"
  [ -z "$label" ] && return 1
  local i
  for i in 1 2; do
    "$DEV" evaluate --session "$sid" "(()=>{const label='$label';const s=[...document.querySelectorAll('span,div')].find(e=>e.childElementCount===0&&(e.innerText||'').trim()===label);if(!s)return 'NO_PILL';const o=s.parentElement&&s.parentElement.parentElement;if(!o)return 'NO_OUTER';o.click();return 'CLICKED';})()" >/dev/null 2>&1
    sleep 1.5
    [ "$(yz_ds_page_mode "$sid")" = "$mode" ] && return 0
  done
  # 容器点击无效时兜底点文本节点本身(事件可能绑在内层)
  "$DEV" evaluate --session "$sid" "(()=>{const label='$label';const s=[...document.querySelectorAll('span,div')].find(e=>e.childElementCount===0&&(e.innerText||'').trim()===label);if(!s)return 'NO_PILL';s.click();return 'CLICKED';})()" >/dev/null 2>&1
  sleep 1.5
  [ "$(yz_ds_page_mode "$sid")" = "$mode" ] && return 0
  return 1
}

# 确保会话模式 == 请求模式;不匹配 → 原地导航新对话页选模式并落 flag 文件。
# 输出 OK|SWITCHED(rc0) / FAIL(rc1)。mode 为空一律 OK。
# 页面模式读不出(unknown)时保守放行 OK,避免把健康会话反复拆毁。
yz_ds_ensure_mode() {
  local sid="$1" mode="$2"
  [ -z "$mode" ] && { echo "OK"; return 0; }
  # 模式路径下本会话可能缺回形针选择器文件(如老 mapfile 指来的会话):顺手补发现
  [ -f "/tmp/yz_ds_clip_${sid}.txt" ] || yz_ds_discover_clip "$sid"
  local pm; pm=$(yz_ds_page_mode "$sid")
  # 空串(evaluate 瞬时失败)与 unknown 同等保守放行,避免拆掉健康会话
  if [ "$pm" = "$mode" ] || [ -z "$pm" ] || [ "$pm" = "unknown" ]; then echo "OK"; return 0; fi
  "$DEV" navigate "https://chat.deepseek.com/" --session "$sid" >/dev/null 2>&1
  sleep 3
  if yz_ds_select_mode "$sid" "$mode"; then
    echo "$mode" > "/tmp/yz_ds_newconv_${sid}.txt" 2>/dev/null
    echo "SWITCHED"; return 0
  fi
  echo "FAIL"; return 1
}

# 发送成功后收尾:若本会话带新对话 flag 且 URL 已变为 /a/chat/s/<newid>,
# 落盘新会话 mapfile、清旧 mapfile 与 flag,echo 新 r_url;否则 echo ""。
yz_ds_finalize_new_conv() {
  local sid="$1" old_rurl="$2"
  local flag="/tmp/yz_ds_newconv_${sid}.txt"
  [ -f "$flag" ] || { echo ""; return 0; }
  local nu; nu=$("$DEV" evaluate --session "$sid" "location.href" 2>/dev/null | tr -d '\r\n')
  case "$nu" in
    https://chat.deepseek.com/a/chat/s/[A-Za-z0-9-]*)
      local ncid; ncid=$(printf %s "$nu" | grep -oE '/a/chat/s/[A-Za-z0-9-]+' | sed 's|/a/chat/s/||')
      printf '%s' "$sid" > "/tmp/yz_conv_sid_ds_${ncid}.txt" 2>/dev/null
      local ocid; ocid=$(printf %s "$old_rurl" | grep -oE '/a/chat/s/[A-Za-z0-9-]+' | sed 's|/a/chat/s/||')
      [ -n "$ocid" ] && [ "$ocid" != "$ncid" ] && rm -f "/tmp/yz_conv_sid_ds_${ocid}.txt" 2>/dev/null
      rm -f "$flag" 2>/dev/null
      echo "$nu"
      ;;
    *) echo "" ;;
  esac
}

# 回形针选择器动态发现(CSS module 哈希类,构建会变,不可写死)。
# 关键(2026-09-01 T2 实测): 哈希随 composer 形态/模式页变化(expert首页=db183363,
# vision首页=f02f0e25),因此每次上传前都要重发现;先删旧文件防陈旧哈希残留。
yz_ds_discover_clip() {
  local sid="$1"
  rm -f "/tmp/yz_ds_clip_${sid}.txt" 2>/dev/null
  local clip; clip=$("$DEV" evaluate --session "$sid" "(()=>{const ta=document.querySelector('textarea');if(!ta)return '';let el=ta;for(let i=0;i<6&&el;i++){el=el.parentElement;if(el&&el.querySelectorAll('div[role=button],button').length>=2)break;}if(!el)return '';const clip=[...el.querySelectorAll('div[role=button]')].find(b=>String(b.className).includes('ds-button--capsule'));if(!clip)return '';const h=[...clip.classList].find(c=>/^[0-9a-f]{6,16}$/.test(c));return h?'.'+h:'';})()" 2>/dev/null | tr -d '\r\n')
  [ -n "$clip" ] && echo "$clip" > "/tmp/yz_ds_clip_${sid}.txt"
  return 0
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
# 用法: yz_acquire_conv <conv_url> [fast|expert|vision]
#   mode 为空 → 行为与旧版完全一致(只按 URL/IDLE 复用);
#   mode 给定 → 复用前校验页面模式,不匹配则原地转新对话页选模式并落 flag,
#               本次发送后由 yz_ds_finalize_new_conv 产出新会话 URL。
# ---------------------------------------------------------------------------
yz_acquire_conv() {
  local conv_url="$1" mode="${2:-}"
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
        local ens="OK"
        [ -n "$mode" ] && ens=$(yz_ds_ensure_mode "$sid" "$mode")
        if [ "$ens" != "FAIL" ]; then
          echo "ds" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
          echo "$sid"; return 0
        fi
      fi
    fi
  fi
  # 模式请求路径:复用/新建会话 → 新对话页选模式 → 落 flag(发送后收尾产出新 URL)
  if [ -n "$mode" ]; then
    if [ -z "$sid" ] || ! "$DEV" session list 2>/dev/null | grep -qE "^${sid}[[:space:]]"; then
      sid=$(timeout 45 "$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
      [ -z "$sid" ] && sid=$(timeout 45 "$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
      [ -z "$sid" ] && { echo ""; return 1; }
    fi
    "$DEV" navigate "https://chat.deepseek.com/" --session "$sid" >/dev/null 2>&1
    sleep 5
    if ! yz_ds_select_mode "$sid" "$mode"; then echo ""; return 1; fi
    echo "$mode" > "/tmp/yz_ds_newconv_${sid}.txt" 2>/dev/null
    echo "ds" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
    echo "$sid" > "$mapfile" 2>/dev/null
    yz_ds_discover_clip "$sid"
    echo "$sid"; return 0
  fi
  # 旧版路径:session start 偶发挂死(后台/无 TTY 环境,2026-09-01):超时 45s + 一次重试
  sid=$(timeout 45 "$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
  [ -z "$sid" ] && sid=$(timeout 45 "$DEV" session start 2>&1 | tr -d '\r' | grep -oE '^[a-z]{4}$' | head -1)
  [ -z "$sid" ] && { echo ""; return 1; }
  "$DEV" navigate "$conv_url" --session "$sid" >/dev/null 2>&1
  sleep 6   # DeepSeek 加载快
  echo "$sid" > "$mapfile"
  echo "ds" > "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null
  yz_ds_discover_clip "$sid"
  echo "$sid"; return 0
}
