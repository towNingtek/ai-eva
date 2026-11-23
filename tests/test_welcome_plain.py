"""ai-eva#233：AI 秘書開場不列程式名。

開場（welcome.sso）只講白話功能，四語渲染後不得出現任何 manifest 工具的程式名，
也不得出現底線連接的英文識別字（dashboard_sdg_data 這類）。工具清單在下方按鈕。
"""
import re

import pytest

from app.i18n import t
from app.i18n.strings import STRINGS

LANGS = ("zh", "en", "ja", "ko")

# CMS manifest 會給的 13 個工具（程式名）
MANIFEST_TOOLS = (
    "dashboard_sdg_data",
    "dashboard_chart_query",
    "chart_export",
    "create_project",
    "list_my_projects",
    "get_project_info",
    "get_sroi",
    "get_sroi_template",
    "save_sroi",
    "save_sdg",
    "generate_sdg",
    "estimate_and_save_sroi",
    "generate_and_save_sdg",
)
_IDENT = re.compile(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+")


def _render(lang: str) -> str:
    # 照 main.py 舊呼叫方式一併給 tools=：模板若還留 {tools} 佔位符就會把程式名渲染出來。
    return t("welcome.sso", lang=lang, who="u@example.com", tools=", ".join(MANIFEST_TOOLS))


def test_manifest_has_13_tools():
    assert len(set(MANIFEST_TOOLS)) == 13


@pytest.mark.parametrize("lang", LANGS)
def test_welcome_sso_has_no_tool_names(lang):
    text = _render(lang)
    assert "u@example.com" in text
    for name in MANIFEST_TOOLS:
        assert name not in text, f"welcome.sso[{lang}] 含工具程式名 {name}"


@pytest.mark.parametrize("lang", LANGS)
def test_welcome_sso_has_no_underscore_identifiers(lang):
    # 電子郵件（who）可能含底線，先拿掉再掃
    text = _render(lang).replace("u@example.com", "")
    assert not _IDENT.findall(text), _IDENT.findall(text)


@pytest.mark.parametrize("lang", LANGS)
def test_welcome_sso_template_has_no_tools_placeholder(lang):
    assert "{tools}" not in STRINGS["welcome.sso"][lang]


def test_old_tools_line_removed():
    src = open("app/i18n/strings.py", encoding="utf-8").read()
    assert "我可以幫你查：{tools}" not in src


def test_main_does_not_pass_tool_names_to_welcome():
    src = open("app/main.py", encoding="utf-8").read()
    i = src.index('t("welcome.sso"')
    call = src[i:src.index(")", src.index(")", i) + 1) + 1]
    assert "tools=" not in call, call


@pytest.mark.parametrize("lang", LANGS)
def test_handoff_loading_text_four_langs(lang):
    text = STRINGS["handoff.loading"][lang]
    assert text and "AI" in text
