from __future__ import annotations

import unittest

from app.tools.developer.md2 import md2_hex
from app.tools.developer.service import DeveloperInputError, DeveloperService


class DeveloperServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DeveloperService()

    def test_hash_vectors(self) -> None:
        self.assertEqual(md2_hex(b""), "8350e5a3e24c153df2275c9f80692773")
        self.assertEqual(self.service.digest("md2", "abc"), "da853b0d3f88d99b30283a69e6ded6bb")
        self.assertEqual(
            self.service.digest("sha256", "abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_text_codecs_round_trip(self) -> None:
        text = "Привет / world?"
        self.assertEqual(self.service.urldecode(self.service.urlencode(text)), text)
        self.assertEqual(self.service.base64decode(self.service.base64encode(text)), text)

    def test_color_inputs(self) -> None:
        self.assertEqual(self.service.color("#abc").hex, "#AABBCC")
        self.assertEqual(self.service.color("1, 2, 3").hex, "#010203")
        with self.assertRaises(DeveloperInputError):
            self.service.color("300 2 3")

    def test_unix_timestamp(self) -> None:
        result = self.service.unix_time("0")
        self.assertEqual(result.timestamp, 0)
        self.assertEqual(result.utc.isoformat(), "1970-01-01T00:00:00+00:00")

    def test_qr_round_trip(self) -> None:
        image = self.service.qr_generate("QR: Привет")
        self.assertEqual(self.service.qr_decode(image), "QR: Привет")


if __name__ == "__main__":
    unittest.main()
