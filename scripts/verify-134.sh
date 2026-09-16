#!/usr/bin/env bash
# ai-eva#134 過渡版專案媒合 —— 驗收判準自動執行器（PR #135）
#
# 用法（在 repo 根目錄）：
#   bash scripts/verify-134.sh            # 自動：能 import 就直接跑，不能就開 .venv-134 裝依賴
#   bash scripts/verify-134.sh --venv     # 強制用 .venv-134（不污染系統 python）
#   bash scripts/verify-134.sh --system   # 強制用現在的 python，不建 venv
#   bash scripts/verify-134.sh --docker   # 用 Dockerfile 建臨時 image 跑（環境最乾淨）
#
# 產出：/tmp/verify-134-output.md —— 直接整份貼回 issue #134 即可。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="${VERIFY134_OUT:-/tmp/verify-134-output.md}"
LOG="${VERIFY134_LOG:-/tmp/verify-134-raw.log}"
MODE=auto
[ $# -gt 0 ] && MODE="${1#--}"

: > "$LOG"

# ---------- docker 模式：轉手丟進容器再跑同一支腳本 ----------
if [ "$MODE" = docker ]; then
  command -v docker >/dev/null || { echo "✗ 找不到 docker"; exit 1; }
  echo "→ 建 image（用 repo 的 Dockerfile，已有 layer cache 會很快）..."
  docker build -t ai-eva-verify134 "$ROOT" || exit 1
  mkdir -p /tmp/verify134
  docker run --rm -v "$ROOT":/src -v /tmp/verify134:/out -w /src \
    -e PYTHONPATH=/src -e VERIFY134_OUT=/out/verify-134-output.md -e VERIFY134_LOG=/out/verify-134-raw.log \
    ai-eva-verify134 bash -c "pip install -q pytest && bash scripts/verify-134.sh --system"
  rc=$?
  cp -f /tmp/verify134/verify-134-output.md "$OUT" 2>/dev/null && echo "報告已複製到 $OUT"
  exit $rc
fi

# ---------- 選 python ----------
PY=""
pick_python() {
  for c in python3 python; do command -v "$c" >/dev/null && { PY="$c"; return; }; done
}
pick_python
[ -n "$PY" ] || { echo "✗ 找不到 python3。請先安裝 Python 3.11+，或改用：bash scripts/verify-134.sh --docker"; exit 1; }

deps_ok() { PYTHONPATH="$ROOT" "$PY" -c "import chainlit, langchain_core, pytest" >/dev/null 2>&1; }

if [ "$MODE" = venv ] || { [ "$MODE" = auto ] && ! deps_ok; }; then
  VENV="$ROOT/.venv-134"
  if [ ! -x "$VENV/bin/python" ]; then
    echo "→ 依賴不齊，建立 $VENV 並安裝 requirements.txt + pytest（約 1-3 分鐘，只做一次）..."
    "$PY" -m venv "$VENV" || { echo "✗ venv 建立失敗；請改用 --docker"; exit 1; }
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r requirements.txt pytest || { echo "✗ pip install 失敗；請改用 --docker"; exit 1; }
  fi
  PY="$VENV/bin/python"
fi

export PYTHONPATH="$ROOT"
if ! PYTHONPATH="$ROOT" "$PY" -c "import chainlit, langchain_core, pytest" 2>/dev/null; then
  echo "✗ 目前環境缺依賴（chainlit / langchain_core / pytest）。請改跑：bash scripts/verify-134.sh --venv 或 --docker"
  exit 1
fi

# ---------- 收集判準結果 ----------
declare -a ROWS
PASS=0; FAIL=0; SKIP=0
record() { # #  結果  說明
  ROWS+=("| $1 | $2 | $3 |")
  case "$2" in ✅*) PASS=$((PASS+1));; ⏭️*) SKIP=$((SKIP+1));; *) FAIL=$((FAIL+1));; esac
}
block() { printf '\n----- %s -----\n' "$1" >> "$LOG"; }

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
PY_VER=$("$PY" -c 'import sys;print(sys.version.split()[0])')

echo "→ repo $GIT_BRANCH @ $GIT_SHA / python $PY_VER"
echo "→ 開始跑判準..."

# 判準 1
block "判準 1 discover"
C1=$("$PY" -c "from app.apps._registry import discover; print('project_match' in discover())" 2>>"$LOG")
echo "判準1 輸出: $C1" >> "$LOG"
[ "$C1" = "True" ] && record 1 "✅ PASS" "\`discover()\` 回 \`True\`" \
                   || record 1 "❌ FAIL" "預期 \`True\`，實得 \`${C1:-<無輸出，見 raw log>}\`"

# 判準 2
block "判準 2 get_by_id"
C2=$("$PY" -c "from app.apps._registry import get_by_id as g; a=g('project_match'); print(a.label, a.id)" 2>>"$LOG")
echo "判準2 輸出: $C2" >> "$LOG"
[ "$C2" = "專案媒合 project_match" ] && record 2 "✅ PASS" "輸出 \`$C2\`" \
                                    || record 2 "❌ FAIL" "預期 \`專案媒合 project_match\`，實得 \`${C2:-<無輸出>}\`"

# 判準 3
block "判準 3 取料兩段"
C3=$(grep -c 'list_my_projects\|get_project_info' app/apps/project_match/handler.py 2>>"$LOG" || true)
echo "判準3 輸出: $C3" >> "$LOG"
[ "${C3:-0}" -ge 2 ] && record 3 "✅ PASS" "grep -c = \`$C3\`（≥2）" \
                     || record 3 "❌ FAIL" "grep -c = \`${C3:-0}\`，預期 ≥2"

# 判準 4
block "判準 4 無 LLMTwins"
C4=$(grep -c 'LLMTwins\|VITE_API_LLMTWINS\|stable.4impact.cc' app/apps/project_match/handler.py 2>>"$LOG" || true)
echo "判準4 輸出: $C4" >> "$LOG"
[ "${C4:-1}" -eq 0 ] && record 4 "✅ PASS" "grep -c = \`0\`，沒回頭接 LLMTwins" \
                     || record 4 "❌ FAIL" "grep -c = \`$C4\`，預期 \`0\`"

# 判準 5/6/7/8 —— pytest
block "判準 5/6/7/8 pytest"
PYTEST_OUT=$("$PY" -m pytest tests/test_project_match.py -v 2>&1)
printf '%s\n' "$PYTEST_OUT" >> "$LOG"
PYTEST_TAIL=$(printf '%s\n' "$PYTEST_OUT" | grep -E 'PASSED|FAILED|ERROR|error|passed|failed|no tests ran' | tail -n 15)

t_pass() { printf '%s\n' "$PYTEST_OUT" | grep -q "$1 PASSED"; }
declare -A CASE=(
  [5]="test_exactly_two_distinct_project_names"
  [6]="test_four_analysis_aspects"
  [7]="test_single_project_refuses_without_calling_llm"
  [8]="test_no_extra_project_info_fetch"
)
declare -A DESC=(
  [5]="intent 恰好出現 2 個不同專案名稱"
  [6]="四個分析面向齊全"
  [7]="不足 2 筆 → 明確訊息且不打 LLM"
  [8]="get_project_info 呼叫次數 == 專案池大小"
)
for n in 5 6 7 8; do
  if t_pass "${CASE[$n]}"; then
    record "$n" "✅ PASS" "\`${CASE[$n]}\` PASSED —— ${DESC[$n]}"
  else
    record "$n" "❌ FAIL" "\`${CASE[$n]}\` 未通過 —— ${DESC[$n]}（見下方 pytest 輸出）"
  fi
done

# 判準 9 —— sechome enabled_apps（需要 DB，連不到就誠實標 SKIP）
block "判準 9 enabled_apps"
TIMEOUT=""; command -v timeout >/dev/null && TIMEOUT="timeout 25"
C9=$($TIMEOUT "$PY" - <<'PYEOF' 2>>"$LOG"
import asyncio
try:
    from app.projects import registry as r
    print("RESULT:", asyncio.run(r.get_enabled_apps("sechome")))
except Exception as e:
    print("UNAVAILABLE:", type(e).__name__, e)
PYEOF
)
echo "判準9 輸出: $C9" >> "$LOG"
case "$C9" in
  "RESULT: None")
    record 9 "✅ PASS" "sechome \`enabled_apps\` = \`None\`（未設 = 全開），媒合入口會出現" ;;
  RESULT:*project_match*)
    record 9 "✅ PASS" "sechome 白名單含 project_match：\`${C9#RESULT: }\`" ;;
  RESULT:*)
    record 9 "❌ FAIL" "sechome 白名單 = \`${C9#RESULT: }\` —— **不含 project_match，部署後選單會靜默不出現**，需先 \`set_enabled_apps\` 補上" ;;
  *)
    record 9 "⏭️ SKIP" "此環境連不到 DB（\`${C9#UNAVAILABLE: }\`）—— 部署前須在目標環境補跑" ;;
esac

# ---------- 產出報告 ----------
{
  echo "## 判準實測結果（PR #135）"
  echo
  echo "- 環境：python \`$PY_VER\`，branch \`$GIT_BRANCH\` @ \`$GIT_SHA\`"
  echo "- 執行方式：\`bash scripts/verify-134.sh\`（任何人可重跑）"
  echo "- 統計：**PASS $PASS / FAIL $FAIL / SKIP $SKIP**"
  echo
  echo "| # | 結果 | 實測 |"
  echo "|---|------|------|"
  printf '%s\n' "${ROWS[@]}"
  echo
  echo "### pytest 輸出"
  echo
  echo '```'
  printf '%s\n' "$PYTEST_TAIL"
  echo '```'
  echo
  if [ "$FAIL" -eq 0 ] && [ "$SKIP" -eq 0 ]; then
    echo "→ 判準全數成立，可 merge #135 並進 \`main → beta\` 部署。"
  elif [ "$FAIL" -eq 0 ]; then
    echo "→ 程式碼判準（1-8）全過；judgment 9 未能在此環境驗證，**部署前必須在目標環境補跑**，否則媒合入口可能靜默不出現。"
  else
    echo "→ 有判準未過，**不得關票**。完整 log：\`/tmp/verify-134-raw.log\`"
  fi
} > "$OUT"

cat "$OUT"
echo
echo "================================================"
echo "報告已存到 $OUT （整份貼回 #134 即可）"
echo "完整原始 log：$LOG"
[ "$FAIL" -eq 0 ]
