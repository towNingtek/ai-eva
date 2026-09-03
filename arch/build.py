#!/usr/bin/env python3
"""Render ai-eva architecture graph from .codeboarding/analysis.json to a static HTML (Mermaid).

Data is the committed CodeBoarding baseline. Output is a JSON-backed Mermaid
directed graph inside the generated HTML so the Cloudflare Pages static site can
render it client-side without any runtime or upstream web.
"""
import json
import os
import sys
import html as html_mod

MIMETYPE = '"text/html"'

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>ai-eva 架構圖</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  body { font-family: -apple-system, system-ui, "Segoe UI", "Noto Sans TC", sans-serif; margin: 0; padding: 24px; background: #0f1117; color: #e6e6e6; }
  header h1 { margin: 0 0 4px; font-size: 22px; }
  header .meta { color: #9aa0aa; font-size: 13px; margin-bottom: 20px; }
  #graph { background: #171a21; border-radius: 10px; padding: 16px; overflow: auto; }
  #graph svg { max-width: none; }
  .legend { margin-top: 12px; font-size: 12px; color: #9aa0aa; }
  code { background: #22252d; padding: 2px 6px; border-radius: 4px; }
</style>
</head>
<body>
<header>
  <h1>ai-eva 架構圖</h1>
  <div class="meta">來源：.codeboarding/analysis.json（CodeBoarding sync，免費 tier）</div>
</header>
<div class="legend">節點 = component；邊 = 關聯（含 call / message / runtime 依賴）。只展示，無互動下鑽。</div>
<div id="graph" class="mermaid">
__MERMAID__
</div>
<script>mermaid.initialize({ startOnLoad: true, theme: 'dark' });</script>
</body>
</html>
"""

NODE_ORIENTATION = "LR"


def build_mermaid(d: dict) -> str:
    rels = d.get("components_relations", [])
    lines = ["flowchart LR"]
    seen = {}
    node_map = {}
    seq = 0

    def node_id(name: str) -> str:
        nonlocal seq
        if name in node_map:
            return node_map[name]
        nid = re_id(f"N{seq}")
        seq += 1
        node_map[name] = nid
        lines.append(f'    {nid}["{esc(name)}"]')
        return nid

    for r in rels:
        s = r.get("src_name") or ""
        t = r.get("dst_name") or ""
        if not s or not t or s == t:
            continue
        sid = node_id(s)
        tid = node_id(t)
        rel = (r.get("relation") or "related").strip()
        lines.append(f'    {sid} -->|"{esc(rel)}"| {tid}')
    if len(lines) == 1:
        lines.append("    Empty[無元件]")
    return "\n".join(lines)


def esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace('"', '&quot;').replace("\n", " ")).strip()


def re_id(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in s)[:40]


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    analysis_path = os.path.join(repo_root, ".codeboarding", "analysis.json")
    out_path = os.path.join(repo_root, "arch", "index.html")
    if not os.path.exists(analysis_path):
        print(f"analysis.json not found: {analysis_path}", file=sys.stderr)
        return 1
    with open(analysis_path) as f:
        data = json.load(f)
    mermaid = build_mermaid(data)
    html = TEMPLATE.replace("__MERMAID__", mermaid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    r = len(data.get("components_relations", []))
    names = set()
    for rl in data.get("components_relations", []):
        names.add(rl.get("src_name"))
        names.add(rl.get("dst_name"))
    names.discard(None)
    print(f"wrote {out_path}: {len(names)} nodes, {r} relations")
    return 0


if __name__ == "__main__":
    sys.exit(main())