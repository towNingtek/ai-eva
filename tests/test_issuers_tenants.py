"""issuer registry：租戶 → CMS host 路由（ai-eva#188 南投；比照 ntidipc／newtaipei-city）。"""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.auth import issuers


def _resp(body):
    r = MagicMock()
    r.json.return_value = body
    r.raise_for_status.return_value = None
    return r


class TenantCmsBaseUrlTests(TestCase):
    def test_nantou_registered_on_dev_issuer(self):
        m = issuers.ISSUERS["tplanet-cms"]["tenant_cms_base_url"]
        self.assertEqual(m.get("nantou-gov"), "https://nantou-gov.sechome.cc")

    def test_nantou_not_on_stable_issuer(self):
        # 正式站路由待 tplanet-multi-tenant#482，不在本卡
        m = issuers.ISSUERS["tplanet-cms-stable"].get("tenant_cms_base_url", {})
        self.assertNotIn("nantou-gov", m)

    def test_nantou_manifest_hits_tenant_host(self):
        with patch.object(issuers.httpx, "get", return_value=_resp({"data": {"tools": []}})) as g:
            out = issuers.fetch_manifest("tplanet-cms", "tok", tenant_id="nantou-gov")
        self.assertEqual(g.call_args.args[0], "https://nantou-gov.sechome.cc/api/tools/manifest")
        self.assertEqual(g.call_args.kwargs["headers"], {"Authorization": "Bearer tok"})
        self.assertEqual(out, {"tools": []})

    def test_nantou_refresh_hits_tenant_host(self):
        with patch.object(issuers.httpx, "post", return_value=_resp({"data": {"tools": []}})) as p:
            issuers.refresh_manifest("tplanet-cms", "rt", tenant_id="nantou-gov")
        self.assertEqual(p.call_args.args[0],
                         "https://nantou-gov.sechome.cc/api/accounts/tools/refresh")

    def test_unlisted_tenant_uses_issuer_default(self):
        dev = issuers.ISSUERS["tplanet-cms"]
        with patch.object(issuers.httpx, "get", return_value=_resp({})) as g:
            issuers.fetch_manifest("tplanet-cms", "tok", tenant_id="some-other-tenant")
        self.assertEqual(g.call_args.args[0], dev["manifest_url"])
        with patch.object(issuers.httpx, "post", return_value=_resp({})) as p:
            issuers.refresh_manifest("tplanet-cms", "rt", tenant_id="some-other-tenant")
        self.assertEqual(p.call_args.args[0], dev["refresh_url"])

    def test_existing_tenants_unchanged(self):
        m = issuers.ISSUERS["tplanet-cms"]["tenant_cms_base_url"]
        self.assertEqual(m["yunlin"], "https://yunlin-beta.4impact.cc")
        self.assertEqual(m["ntidipc"], "https://ntidipc.sechome.cc")
        self.assertEqual(m["newtaipei-city"], "https://newtaipei-city.sechome.cc")
