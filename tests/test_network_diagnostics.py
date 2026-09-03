from __future__ import annotations

import unittest

import httpx

from app.tools.network.providers.diagnostics import SystemDiagnosticsProvider
from app.tools.network.validators import require_http_url


class NetworkValidatorTests(unittest.TestCase):
    def test_http_url_normalization(self) -> None:
        self.assertEqual(require_http_url("example.com/path?q=1"), "https://example.com/path?q=1")
        self.assertEqual(require_http_url("http://пример.рф"), "http://xn--e1afmkfd.xn--p1ai/")


class HttpDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_reads_headers_without_body(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                204,
                headers={"server": "test", "content-length": "123"},
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await SystemDiagnosticsProvider(client).check_http("https://example.com/")

        self.assertEqual(result.status_code, 204)
        self.assertEqual(result.server, "test")
        self.assertEqual(result.content_length, 123)
        self.assertTrue(result.reachable)


if __name__ == "__main__":
    unittest.main()
