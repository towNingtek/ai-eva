#!/usr/bin/env python3
"""Render the ai-eva architecture graph from .codeboarding/analysis.json.

Nodes are real source files (clickable through to GitHub); the LLM-generated
component names become group titles instead of graph nodes, so the picture is
anchored to things that exist in the repository.
"""
import json
import os
import re
import sys

REPO = os.environ.get("ARCH_REPO", "towNingtek/ai-eva")
BRANCH = os.environ.get("ARCH_BRANCH", "main")

SAFE_PATH = re.compile(r"^[A-Za-z0-9._/\-]+$")

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>ai-eva 架構圖</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  body { font-family: -apple-system, system-ui, "Segoe UI", "Noto Sans TC", sans-serif;
         margin: 0; padding: 24px 24px 64px; background: #0f1117; color: #e6e6e6; }
  header h1 { margin: 0 0 4px; font-size: 22px; }
  header .meta { color: #9aa0aa; font-size: 13px; }
  .hint { color: #9aa0aa; font-size: 12px; margin: 14px 0 10px; }
  #graph { background: #171a21; border-radius: 10px; padding: 16px; overflow: auto; }
  #graph svg { max-width: none; }
  #graph .node.clickable rect, #graph .node.clickable polygon { cursor: pointer; }
  h2 { font-size: 16px; margin: 32px 0 8px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #262a33; vertical-align: top; }
  th { color: #9aa0aa; font-weight: 600; }
  td.files { white-space: nowrap; }
  a { color: #7cc4ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  code { background: #22252d; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>ai-eva 架構圖</h1>
  <div class="meta">來源：<code>.codeboarding/analysis.json</code>（CodeBoarding sync）· 分支 <code>__BRANCH__</code></div>
</header>
<div class="hint">方框 = 實際程式檔案，點一下開 GitHub。外框 = CodeBoarding 歸納的元件分組。箭頭 = 檔案之間的實際呼叫關係。</div>
<div id="graph" class="mermaid">
__MERMAID__
</div>

<h2>元件分組</h2>
<table>
<thead><tr><th>元件</th><th>說明</th><th class="files">檔案</th></tr></thead>
<tbody>
__COMPONENTS__
</tbody>
</table>

<h2>系統概述</h2>
<p style="font-size:13px;line-height:1.7;color:#c3c8d2;max-width:900px">__DESCRIPTION__</p>

<script>
mermaid.initialize({ startOnLoad: true, theme: 'dark', securityLevel: 'loose',
                     flowchart: { curve: 'basis', useMaxWidth: false } });
</script>
</body>
</html>
"""


def esc_label(s: str) -> str:
    """Mermaid-safe label text: no quotes, backslashes, pipes or raw angle brackets."""
    for bad in ('\\', '"', '<', '>', '|', '`'):
        s = s.replace(bad, "'" if bad == '"' else " ")
    return " ".join(s.split()).strip()


def esc_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def file_ref(entity: dict):
    """(path, start_line) from a key_entities entry."""
    path = entity.get("reference_file")
    if not path or not SAFE_PATH.match(path):
        return None, None
    return path, entity.get("reference_start_line")


def collect(data: dict):
    """Return (groups, file_lines, edges).

    groups:     ordered list of {name, description, files}
    file_lines: path -> first known line number
    edges:      {(src_path, dst_path): set(target function names)}
    """
    groups = []
    owner = {}
    file_lines = {}

    def claim(component, files_out):
        for ent in component.get("key_entities") or []:
            path, line = file_ref(ent)
            if not path:
                continue
            if path not in file_lines and line:
                file_lines[path] = line
            files_out.add(path)

    for comp in data.get("components", []):
        files = set()
        claim(comp, files)
        for sub in comp.get("components") or []:
            claim(sub, files)
        name = comp.get("name") or f"component {comp.get('component_id')}"
        groups.append({
            "name": name,
            "description": (comp.get("description") or "").strip(),
            "files": files,
        })
        for path in files:
            owner.setdefault(path, name)

    edges = {}
    for rel in data.get("components_relations", []):
        for edge in (rel.get("all_edges") or []) + (rel.get("key_edges") or []):
            src = (edge.get("source") or "").split("|")
            dst = (edge.get("target") or "").split("|")
            if len(src) < 1 or len(dst) < 1:
                continue
            s_path, d_path = src[0], dst[0]
            if not (SAFE_PATH.match(s_path or "") and SAFE_PATH.match(d_path or "")):
                continue
            if s_path == d_path:
                continue
            fn = dst[1].rsplit(".", 1)[-1] if len(dst) > 1 else ""
            edges.setdefault((s_path, d_path), set())
            if fn:
                edges[(s_path, d_path)].add(fn)

    # files that only show up as call endpoints still belong on the diagram
    extra = set()
    for s_path, d_path in edges:
        for path in (s_path, d_path):
            if path not in owner:
                extra.add(path)
    if extra:
        groups.append({"name": "其他檔案", "description": "分析有呼叫關係、但未被歸入上述元件的檔案。",
                       "files": extra})
        for path in extra:
            owner[path] = "其他檔案"

    return groups, file_lines, edges


def build_mermaid(groups, file_lines, edges) -> str:
    ids = {}
    lines = ["flowchart LR"]
    clicks = []

    for gi, group in enumerate(groups):
        if not group["files"]:
            continue
        lines.append(f'    subgraph G{gi}["{esc_label(group["name"])}"]')
        lines.append("    direction TB")
        for path in sorted(group["files"]):
            nid = f"F{len(ids)}"
            ids[path] = nid
            label = os.path.basename(path)
            folder = os.path.dirname(path)
            text = esc_label(label)
            if folder:
                text += "<br/>" + esc_label(folder)
            lines.append(f'        {nid}["{text}"]')
            line_no = file_lines.get(path)
            anchor = f"#L{line_no}" if line_no else ""
            url = f"https://github.com/{REPO}/blob/{BRANCH}/{path}{anchor}"
            clicks.append(f'    click {nid} href "{url}" "{esc_label(path)}"')
        lines.append("    end")

    for (s_path, d_path), fns in sorted(edges.items()):
        s_id, d_id = ids.get(s_path), ids.get(d_path)
        if not s_id or not d_id:
            continue
        names = sorted(fns)
        if not names:
            label = ""
        elif len(names) == 1:
            label = names[0]
        else:
            label = f"{names[0]} +{len(names) - 1}"
        if label:
            lines.append(f'    {s_id} -->|"{esc_label(label)}"| {d_id}')
        else:
            lines.append(f"    {s_id} --> {d_id}")

    lines.extend(clicks)
    if len(lines) == 1:
        lines.append("    Empty[無資料]")
    return "\n".join(lines)


def build_component_rows(groups) -> str:
    rows = []
    for group in groups:
        if not group["files"]:
            continue
        links = "<br>".join(
            f'<a href="https://github.com/{REPO}/blob/{BRANCH}/{p}"><code>{esc_html(p)}</code></a>'
            for p in sorted(group["files"])
        )
        rows.append(
            "<tr><td>{}</td><td>{}</td><td class=\"files\">{}</td></tr>".format(
                esc_html(group["name"]), esc_html(group["description"]), links
            )
        )
    return "\n".join(rows)


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    analysis_path = os.path.join(repo_root, ".codeboarding", "analysis.json")
    out_path = os.path.join(repo_root, "arch", "index.html")
    if not os.path.exists(analysis_path):
        print(f"analysis.json not found: {analysis_path}", file=sys.stderr)
        return 1
    with open(analysis_path) as fh:
        data = json.load(fh)

    groups, file_lines, edges = collect(data)
    html = (TEMPLATE
            .replace("__MERMAID__", build_mermaid(groups, file_lines, edges))
            .replace("__COMPONENTS__", build_component_rows(groups))
            .replace("__DESCRIPTION__", esc_html((data.get("description") or "").strip()))
            .replace("__BRANCH__", esc_html(BRANCH)))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write(html)

    n_files = sum(len(g["files"]) for g in groups)
    print(f"wrote {out_path}: {n_files} files, {len(edges)} edges, {len(groups)} groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
