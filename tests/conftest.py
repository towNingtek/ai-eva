"""全測試共用設定。"""
import importlib
import warnings


def _preimport_quietly(module: str, category: type, message: str) -> None:
    """在只針對單一第三方警告的 catch_warnings 內先 import 模組。

    第三方套件在 import 時發出、我們改不到原始碼的 DeprecationWarning，
    會讓 `pytest -W error::DeprecationWarning` 在收集階段就失敗。模組只會
    import 一次，先在這裡安靜地載入，之後測試再 import 就不會再發警告。
    範圍限定在這一次 import、這個類別與訊息；不影響專案自己的警告，
    也不碰 RuntimeWarning。
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=message, category=category)
        try:
            importlib.import_module(module)
        except ImportError:
            pass


def _third_party_import_warnings() -> None:
    # 舊版 starlette 的 testclient 在 import 時讀 anyio.abc.BlockingPortal
    # （新版 anyio 已棄用此別名；新版 starlette 已改掉）。
    _preimport_quietly(
        "starlette.testclient",
        DeprecationWarning,
        r"The anyio\.abc\.BlockingPortal alias is deprecated",
    )
    try:
        from pydantic.warnings import PydanticDeprecatedSince20
    except ImportError:
        return
    # chainlit → literalai → traceloop：traceloop 的 RegistryObjectBaseModel
    # 仍用 class-based `config`（Pydantic V2 已棄用）。
    _preimport_quietly(
        "traceloop.sdk.prompts.model",
        PydanticDeprecatedSince20,
        r"Support for class-based `config` is deprecated",
    )


_third_party_import_warnings()


def _testclient_per_request_cookies_as_header() -> None:
    """把 TestClient 的單次請求 cookies= 改成同義的 Cookie 標頭。

    httpx 0.24+ 已棄用 `client.get(..., cookies={...})`（單次請求 cookies 是否
    寫回 client 語意不明），會發 DeprecationWarning。不改寫測試、不過濾警告，
    而是改用 httpx 建議的等價做法：把 client 既有 cookie 與這次的 cookies 合併，
    依 URL 算出 Cookie 標頭後隨這次請求送出，不寫回 client 的 cookie jar
    （與原本單次 cookies 的行為相同）。呼叫端自己帶了 Cookie 標頭時不動。
    """
    try:
        from starlette import testclient
    except ImportError:
        return
    # 用 starlette 自己綁定的 httpx 模組（有些環境不是頂層 httpx），型別才一致。
    httpx = testclient.httpx
    TestClient = testclient.TestClient
    if getattr(TestClient.request, "_eva_cookie_header", False):
        return
    original = TestClient.request

    def request(self, method, url, *args, cookies=None, headers=None, **kwargs):
        if cookies:
            merged_headers = httpx.Headers(headers)
            if "cookie" not in merged_headers:
                jar = httpx.Cookies(self.cookies)
                jar.update(cookies)
                probe = httpx.Request(method, self._merge_url(url))
                jar.set_cookie_header(probe)
                if "cookie" in probe.headers:
                    merged_headers["cookie"] = probe.headers["cookie"]
            headers, cookies = merged_headers, None
        return original(self, method, url, *args, cookies=cookies, headers=headers, **kwargs)

    request._eva_cookie_header = True
    TestClient.request = request


_testclient_per_request_cookies_as_header()


def pytest_addoption(parser):
    # pytest.ini 設了 asyncio_default_fixture_loop_scope（給 pytest-asyncio 用）。
    # 環境沒裝 pytest-asyncio 時，這個鍵沒人註冊會出 PytestConfigWarning，
    # 在這裡補註冊；有裝時由 plugin 自己註冊，不能重複。
    try:
        import pytest_asyncio  # noqa: F401
    except ImportError:
        parser.addini(
            "asyncio_default_fixture_loop_scope",
            "pytest-asyncio 預設 fixture loop scope（未安裝 pytest-asyncio 時僅佔位）",
        )
