#!/usr/bin/env bash
# bsk shim(2026-09-01):DeepSeek 会话的 upload 选择器改写层
# 只处理一种情况:upload --session <ds会话> --selector '#upload-files'
#   → 改写为 yz_acquire_conv 动态发现的 DeepSeek 回形针选择器(/tmp/yz_ds_clip_<sid>.txt)
# 其余一切调用原样透传真实 bsk.exe。由 yz_lib.sh 的 DEV 指向本文件生效。
REAL="/e/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe"
if [ "${1:-}" = "upload" ]; then
  sid=""; sel=""
  args=("$@")
  n=${#args[@]}
  for ((i=0; i<n; i++)); do
    a="${args[$i]}"
    case "$a" in
      --session)    [ $((i+1)) -lt $n ] && sid="${args[$((i+1))]}" ;;
      --session=*)  sid="${a#--session=}" ;;
      --selector)   [ $((i+1)) -lt $n ] && sel="${args[$((i+1))]}" ;;
      --selector=*) sel="${a#--selector=}" ;;
    esac
  done
  if [ "$sel" = "#upload-files" ] && [ -n "$sid" ]; then
    h=$(tr -d '\r\n' < "/tmp/yz_sid_host_${sid}.txt" 2>/dev/null)
    if [ "$h" = "ds" ]; then
      clip=$(tr -d '\r\n' < "/tmp/yz_ds_clip_${sid}.txt" 2>/dev/null)
      if [ -n "$clip" ]; then
        out=()
        for ((i=0; i<n; i++)); do
          a="${args[$i]}"
          if [ "$a" = "--selector" ] && [ $((i+1)) -lt $n ]; then
            out+=("--selector" "$clip"); i=$((i+1))
          elif [[ "$a" == --selector=* ]]; then
            out+=("--selector=$clip")
          else
            out+=("$a")
          fi
        done
        exec "$REAL" "${out[@]}"
      fi
    fi
  fi
fi
exec "$REAL" "$@"
