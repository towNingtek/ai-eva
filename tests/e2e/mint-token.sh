#!/usr/bin/env bash
# 簽一張 CMS → AI-Eva 的 SSO handoff token（RS256，TTL 10 分鐘）。
#
# E2E 需要一個「從 CMS 進來」的登入態才點得到工具選單。正式流程是使用者在 CMS 按
# 「進 AI Eva」，這裡直接用 dev CMS 的簽章金鑰簽一張等價的 token。
#
# 用法：./mint-token.sh > .auth/token.txt
#   CMS_CONTAINER  dev CMS 容器名（預設 mt-dev-backend）
#   CMS_USER_ID    要模擬的使用者 id（預設 227 = 測試計畫的 owner）
#   CMS_TENANT     tenant_id（預設 dev；用 yunlin 會讓 ai-eva 去 yunlin-beta 拿 manifest）
set -euo pipefail
CONTAINER="${CMS_CONTAINER:-mt-dev-backend}"
USER_ID="${CMS_USER_ID:-227}"
TENANT="${CMS_TENANT:-dev}"
docker exec -w /server/backend "$CONTAINER" python -c "
import django; django.setup()
from django.contrib.auth.models import User
from accounts.services.sso_keys import sign_handoff
print(str(sign_handoff(User.objects.get(id=${USER_ID}), '${TENANT}')), end='')
"
