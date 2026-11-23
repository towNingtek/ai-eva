"""前端靜態檔的版本參數：依檔案內容產生短雜湊（#240）。

CDN（Cloudflare）依完整網址快取；版本參數寫死（例 `?v=live-match`）時檔案內容改了網址不變，
部署後瀏覽器仍拿到舊檔。改用內容雜湊：內容一變網址就變，一定拿到新版。不需改 CDN 設定或關快取。
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
LENGTH = 10


def content_hash(path: Path | str) -> str:
    """檔案內容的 sha256 前 10 碼；檔案不存在時回傳 "missing"（不讓啟動失敗）。"""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return "missing"
    return hashlib.sha256(data).hexdigest()[:LENGTH]


@lru_cache(maxsize=None)
def cached_hash(path: str) -> str:
    """同 content_hash，但每個檔案只算一次（啟動後檔案不會再變）。"""
    return content_hash(path)


def public_hash(rel: str) -> str:
    """public/ 底下某檔（相對路徑，例 "workspace/match-task.js"）的內容雜湊，快取。"""
    return cached_hash(str(PUBLIC / rel))


def custom_js_url() -> str:
    """法規／媒合工作區用的 custom_js：overlay 本身帶內容雜湊（v），
    並以 c 告訴 overlay 用 custom.js 的內容雜湊去載 custom.js。"""
    return (f"/public/tangle-lab-overlay.js?v={public_hash('tangle-lab-overlay.js')}"
            f"&c={public_hash('custom.js')}")
