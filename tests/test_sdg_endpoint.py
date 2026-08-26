import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.surfaces import sdg


class Request:
    def __init__(self, data=None, token=""):
        self.headers = {"x-sdg-service-token": token}
        self.data = data or {"project": {"name": "test project"}}

    async def json(self):
        return self.data


class SdgEndpointTests(TestCase):
    def setUp(self):
        self.token = "test-service-token"
        self.previous = sdg._SERVICE_TOKEN
        sdg._SERVICE_TOKEN = self.token

    def tearDown(self):
        sdg._SERVICE_TOKEN = self.previous

    def test_requires_service_token(self):
        with self.assertRaises(HTTPException) as error:
            sdg._check_service_token(Request(token="wrong"))
        self.assertEqual(error.exception.status_code, 403)

    def test_requires_project_name(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(sdg.generate_sdg_endpoint(Request({"project": {}}, self.token)))
        self.assertEqual(error.exception.status_code, 400)

    def test_returns_generated_sdgs_without_persisting(self):
        with patch.object(sdg, "generate_sdg", new=AsyncMock(return_value={"1": "impact"})) as generate:
            result = asyncio.run(sdg.generate_sdg_endpoint(Request(token=self.token)))

        self.assertEqual(result, {"project_sdgs": {"1": "impact"}})
        generate.assert_awaited_once()

    def test_filters_invalid_and_excessive_results(self):
        with patch.object(
            sdg, "generate_sdg", new=AsyncMock(return_value={"0": "bad", "18": "bad", "1": "ok"})
        ):
            result = asyncio.run(sdg.generate_sdg_endpoint(Request(token=self.token)))
        self.assertEqual(result, {"project_sdgs": {"1": "ok"}})
