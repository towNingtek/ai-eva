#!/usr/bin/env bash
# One command for every lab check. Usage (from the repo root on GCP):
#   tests/lab/run-all-checks.sh            # local checks (data, replies, graph, animation keep, two-plan same, law)
#   tests/lab/run-all-checks.sh --live     # + live site end-to-end (needs ~/.tangle-lab/password)
#   tests/lab/run-all-checks.sh --full     # + every 3/4-plan set for --multi (330 sets, slow)
# Exit 0 only if every check passed. Last line: "ALL CHECKS PASSED <n>" or "FAILED <k>/<n>: <names>".
# Rule (2026-11-15): before every deploy, this must pass. Animations may change, never disappear.
set -u
cd "$(dirname "$0")/../.."
export PATH="$HOME/.nvm/versions/node/v20.19.0/bin:$PATH"
export NODE_PATH="${NODE_PATH:-/home/yillkid/workspace/swarm/hives/town-intelligent/e2e/node_modules}"
LIVE=0; FULL=0; for a in "$@"; do [ "$a" = --live ] && LIVE=1; [ "$a" = --full ] && FULL=1; done
LOG=/tmp/lab-checks-$(date +%Y%m%d-%H%M%S).log; : > "$LOG"
PASS=0; FAIL=0; FAILED=()
run() { local name="$1"; shift; local t0=$(date +%s)
  if "$@" >>"$LOG" 2>&1; then PASS=$((PASS+1)); printf 'ok   %-34s %4ss\n' "$name" $(( $(date +%s)-t0 ))
  else FAIL=$((FAIL+1)); FAILED+=("$name"); printf 'FAIL %-34s %4ss  (see %s)\n' "$name" $(( $(date +%s)-t0 )) "$LOG"; fi; }
echo "log: $LOG"
# ── data and rules ──
run "standard yaml"            python3 tools/match_standard_check.py
run "law data"                 python3 tools/kv_law_check.py
run "law data self-test"       python3 tools/kv_law_check.py --self-test
run "match data"               python3 tools/kv_match_check.py
run "match data self-test"     python3 tools/kv_match_check.py --self-test
run "replies (law + match)"    python3 app/lab/kv_reply_check.py
run "replies self-test"        python3 app/lab/kv_reply_check.py --self-test
# ── old effects must not disappear ──
run "animation keep (16)"      timeout 600 node tests/lab/animation-keep.check.js
# Two-plan view must be byte-identical to the graph code of TWO_PLAN_REF (before multi-plan work), using today's data.
# Only the graph program is taken from the ref, so an intended data change does not count as a difference.
TWO_PLAN_REF="${TWO_PLAN_REF:-1aa9a20}"
BASE=/tmp/lab-two-plan-base; rm -rf "$BASE"; mkdir -p "$BASE"; cp -r public/tangle "$BASE/"
git show "$TWO_PLAN_REF:public/tangle/tangle-match.html" > "$BASE/tangle/tangle-match.html"
git show "$TWO_PLAN_REF:public/tangle/yunlin-frame.js"  > "$BASE/tangle/yunlin-frame.js"
run "two-plan view unchanged (vs $TWO_PLAN_REF)" timeout 1800 node tests/lab/two-plan-same.cjs "$BASE" "$PWD/public"
# ── law graph ──
for f in --domain --select --supplement --ring --motion --flow --pulse --focus --hygiene --no-overlap --focus-layout; do
  run "law $f" timeout 900 node tests/lab/law-domain-view.check.js $f; done
# ── match graph ──
for f in --keys --routes --need-look --flow --pulse --peer --third --status --pair --pair-peer --planet --multi-focus --multi-pair --hygiene --no-overlap; do
  run "match $f" timeout 1200 node tests/lab/match-b1b8.check.js $f; done
if [ $FULL = 1 ]; then run "match --multi (all 330 sets)" timeout 7200 node tests/lab/match-b1b8.check.js --multi --all
else run "match --multi (30-set sample)" timeout 1200 node tests/lab/match-b1b8.check.js --multi; fi
# ── live site (real mouse) ──
if [ $LIVE = 1 ]; then
  export LAB_URL=https://eva-tangle-lab.4impact.cc LAB_PASS="$(cat ~/.tangle-lab/password)"
  for t in lab-D lab-C lab-B lab-3a lab-2a lab-2b lab-AE; do run "live $t" timeout 600 node tests/lab/$t.e2e.js; done
  run "live overlay regression" bash -c 'cd /home/yillkid/workspace/swarm/hives/town-intelligent/e2e && unset NODE_OPTIONS && cp '"$PWD"'/tests/lab/overlay-regression.e2e.js ./_reg.js && U=$LAB_URL PW=$LAB_PASS timeout 400 node _reg.js; r=$?; rm -f _reg.js; exit $r'
fi
N=$((PASS+FAIL))
if [ $FAIL = 0 ]; then echo "ALL CHECKS PASSED $N"; exit 0; fi
echo "FAILED $FAIL/$N: ${FAILED[*]}"; exit 1
