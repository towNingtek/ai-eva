"""#244：AI-Eva 接手過場頁先畫完整再轉頁（手機曾截到只畫左半邊）。"""
import re

import pytest

from app.i18n.strings import STRINGS
from app.surfaces.sso import render_handoff_page

NEXT = "/sso/handoff?token=abc&go=1"


def _script(page: str) -> str:
    m = re.search(r"<script>(.*?)</script>", page, re.S)
    assert m, page
    return m.group(1)


def test_redirect_runs_inside_two_nested_raf_callbacks():
    page = render_handoff_page("zh", NEXT)
    assert "<script>location.replace(" not in page
    js = _script(page)
    # 轉頁只在 go() 裡，go 是第二層 requestAnimationFrame 的回呼
    assert js.count("location.replace(") == 1
    m = re.search(r"function go\(\)\{(.*?)\}\n", js, re.S)
    assert m and "location.replace(u)" in m.group(1)
    assert "requestAnimationFrame(function(){requestAnimationFrame(go);})" in js
    # 頂層沒有直接呼叫 go()／location.replace
    top = js.replace(m.group(0), "")
    assert "location.replace" not in top
    assert not re.search(r"(?<![\w(])go\(\)", top.replace("function go()", ""))


def test_next_url_is_json_escaped_in_script():
    page = render_handoff_page("en", "/x?a=</script><b>")
    js = _script(page)
    assert "</script>" not in js and "\\u003c/script>" in js


def test_html_element_has_background():
    page = render_handoff_page("zh", NEXT)
    m = re.search(r"<html\b[^>]*>", page)
    assert m and re.search(r'style="[^"]*background', m.group(0)), m and m.group(0)
    css = re.search(r"<style>(.*?)</style>", page, re.S).group(1)
    assert re.search(r"(^|\n)html\{[^}]*background", css)


def test_noscript_meta_refresh_kept():
    page = render_handoff_page("zh", NEXT)
    assert '<noscript><meta http-equiv="refresh" content="0;url=/sso/handoff?token=abc&amp;go=1"></noscript>' in page


@pytest.mark.parametrize("lang,loc", [("zh", "zh-TW"), ("en", "en-US"), ("ja", "ja"), ("ko", "ko")])
def test_four_lang_text(lang, loc):
    page = render_handoff_page(lang, NEXT)
    assert STRINGS["handoff.loading"][lang] in page
    assert f'<html lang="{loc}"' in page
