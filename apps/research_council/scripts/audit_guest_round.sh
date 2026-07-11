#!/usr/bin/env bash
# 无头多智能体审计复核：将审查报告 + 反驳 + 修复摘要分发给 codex / qoder / grok
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/docs/audit_guest_responses"
TS="$(date -u +%Y%m%d-%H%M%S)"
ROUND_DIR="$OUT_DIR/round-$TS"
mkdir -p "$ROUND_DIR"

read_doc() {
  local f="$1"
  if [[ -f "$f" ]]; then
    cat "$f"
  else
    echo "(missing: $f)"
  fi
}

FIXES_SUMMARY="$(cat <<'EOF'
## 已落地修复摘要（2026-07-10）

- 账本：claim RESPOND 主线程合并写 + fcntl.flock
- save_state 原子写（lib/utils.py）
- CLI mock：stderr 警告 + --strict / COUNCIL_STRICT=1
- 并行轮全失败不推进 round
- Claim 晋升/RESPOND 校验收紧
- tmux argv 列表；meeting_id 正则校验
- cmd_init 从 config/guests.yaml.template 复制
- 投资报告从 state/metrics 动态汇编
- tests/run_tests.py 8 项通过；pyproject.toml；.qoder/ gitignore
- run-daily 需 --force-owner-continue 并写 daily_owner_override 审计
EOF
)"

build_prompt() {
  local role="$1"
  local audit="$2"
  local rebuttal="$3"
  local extra="$4"
  cat <<EOF
# Claimfold 审计复核 — 嘉宾 $role

你是 Claimfold 多模型会议的一名嘉宾。请**只读**审阅下列材料，不要执行仓库命令。

## 你的任务

1. 对「反驳文档」中**维持反驳**的条目：同意或提出反反驳（需证据）
2. 对「已修复」条目：评价修复是否充分，有无遗漏回归点
3. 给出修订后健康度（0–100）与 3 条最高优先级后续动作
4. 保持简洁，用中文，≤800 字

## 角色侧重

$extra

---

$FIXES_SUMMARY

---

## 原始审查报告

$audit

---

## Grok 反驳意见

$rebuttal

---

## 输出格式（必须遵守）

判断：
已确认事实：
合理推断：
反方视角：
建议：
是否需要下一轮：
EOF
}

QODER_AUDIT="$(read_doc "$ROOT/docs/AUDIT_REPORT.md")"
QODER_REBUTTAL="$(read_doc "$ROOT/docs/AUDIT_REBUTTAL_qoder.md")"
CODEX_AUDIT="$(read_doc "$ROOT/docs/AUDIT_REPORT_codex.md")"
CODEX_REBUTTAL="$(read_doc "$ROOT/docs/AUDIT_REBUTTAL_codex.md")"
META_EXTRA="你审的是 **Qoder 原始审计 + 对 Qoder 的反驳**。请站在原审计作者立场，也承认 Grok 反驳中合理部分。"

invoke_codex() {
  local prompt_file="$1"
  local out_file="$2"
  echo "→ codex ..."
  bash "$ROOT/scripts/run_codex_guest.sh" < "$prompt_file" > "$out_file" 2>"$out_file.err" || true
}

invoke_qoder() {
  local prompt_file="$1"
  local out_file="$2"
  echo "→ qoder ..."
  bash "$ROOT/scripts/run_qoder_guest.sh" < "$prompt_file" > "$out_file" 2>"$out_file.err" || true
}

invoke_grok() {
  local prompt_file="$1"
  local out_file="$2"
  echo "→ grok (laguna) ..."
  build_prompt "grok/laguna" "$QODER_AUDIT" "$CODEX_REBUTTAL" \
    "你是第三方仲裁。同时看到 Qoder 审计与 Codex 反驳文档。请裁决：P0 定级、健康度 42 vs 58、并行无交叉引用是否缺陷。" \
    > "$prompt_file"
  timeout 180 opencode run -m hermes-grok/grok-4.3 --auto < "$prompt_file" > "$out_file" 2>"$out_file.err" || true
  if [[ -s "$out_file" ]]; then
    python3 "$ROOT/scripts/dedupe_guest_output.py" < "$out_file" > "$out_file.dedup" && mv "$out_file.dedup" "$out_file"
  fi
}

# Build prompts to disk for audit trail
P_CODEX="$ROUND_DIR/prompt-codex.md"
P_QODER="$ROUND_DIR/prompt-qoder.md"
P_GROK="$ROUND_DIR/prompt-grok.md"

build_prompt "codex" "$CODEX_AUDIT" "$CODEX_REBUTTAL" \
  "你审的是 **Codex 原始审计 + 对 Codex 的反驳**。重点：Mock 污染是否仍 P1、run-daily owner 策略、全失败轮次。" \
  > "$P_CODEX"
build_prompt "qoder" "$QODER_AUDIT" "$QODER_REBUTTAL" "$META_EXTRA" > "$P_QODER"
build_prompt "grok/laguna" "$QODER_AUDIT" "$CODEX_REBUTTAL" \
  "你是第三方仲裁。同时看到 Qoder 审计与 Codex 反驳文档。请裁决：P0 定级、健康度 42 vs 58、并行无交叉引用是否缺陷。" \
  > "$P_GROK"

echo "=== audit guest round @ $TS ==="
echo "Output: $ROUND_DIR"

invoke_codex "$P_CODEX" "$ROUND_DIR/raw-codex.md" &
PID_C=$!
invoke_qoder "$P_QODER" "$ROUND_DIR/raw-qoder.md" &
PID_Q=$!
invoke_grok "$P_GROK" "$ROUND_DIR/raw-grok.md" &
PID_G=$!

wait $PID_C $PID_Q $PID_G

# Manifest
python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

rd = Path("$ROUND_DIR")
manifest = {
    "round": "$TS",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "guests": [],
}
for guest in ("codex", "qoder", "grok"):
    raw = rd / f"raw-{guest}.md"
    err = rd / f"raw-{guest}.md.err"
    entry = {
        "guest": guest,
        "prompt": str(rd / f"prompt-{guest}.md"),
        "raw": str(raw),
        "chars": len(raw.read_text(encoding="utf-8")) if raw.exists() else 0,
        "ok": raw.exists() and raw.stat().st_size > 80,
        "stderr": err.read_text(encoding="utf-8")[:500] if err.exists() else "",
    }
    manifest["guests"].append(entry)
(rd / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2))
PY

# Roll-up markdown
{
  echo "# 审计嘉宾复核 — round-$TS"
  echo ""
  echo "生成时间：$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  for g in codex qoder grok; do
    echo "## $g"
    echo ""
    if [[ -s "$ROUND_DIR/raw-$g.md" ]]; then
      cat "$ROUND_DIR/raw-$g.md"
    else
      echo "（无输出或失败，见 raw-$g.md.err）"
      [[ -f "$ROUND_DIR/raw-$g.md.err" ]] && echo '```' && cat "$ROUND_DIR/raw-$g.md.err" && echo '```'
    fi
    echo ""
  done
} > "$ROUND_DIR/rollup.md"

echo ""
echo "Done: $ROUND_DIR/rollup.md"