"""Serve actual synthetic media bytes, not just mock segment dictionaries."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from fixture_media import FixtureMediaServer


class FixtureMediaTests(unittest.TestCase):
    def test_http_download_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "fixtures"
            directory.mkdir()
            image = b"\x89PNG\r\n\x1a\n" + b"fixture-image"
            wav = b"RIFF\x00\x00\x00\x00WAVEfmt fixture-audio"
            mp4 = b"\x00\x00\x00\x18ftypisomfixture-video"
            for name, data in (("sample.png", image), ("sample.wav", wav), ("sample.mp4", mp4)):
                (directory / name).write_bytes(data)
            server = FixtureMediaServer(directory)
            server.start()
            try:
                for name, expected, mime in (
                    ("sample.png", image, "image/png"),
                    ("sample.wav", wav, "audio/x-wav"),
                    ("sample.mp4", mp4, "video/mp4"),
                ):
                    with urlopen(server.url(name), timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), expected)
                        self.assertEqual(response.headers["Content-Type"], mime)
                with self.assertRaises(ValueError):
                    server.url("../forbidden.txt")
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(f"http://127.0.0.1:{server.port}/fixtures/invalid/sample.png", timeout=3)
                self.assertEqual(ctx.exception.code, 404)
                # An actual filesystem symlink escaping the fixture directory
                # must not be exposed by the server.
                outside = Path(tmp) / "outside.txt"
                outside.write_text("hidden")
                (directory / "link.txt").symlink_to(outside)
                with self.assertRaises(ValueError):
                    server.url("link.txt")
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
