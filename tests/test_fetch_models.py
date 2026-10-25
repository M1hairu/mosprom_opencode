"""scripts/fetch_models.py (#354): which release files the walk can show."""

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("fetch_models", ROOT / "scripts/fetch_models.py")
fetch_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_models)


def glb(head: dict) -> bytes:
    body = json.dumps(head).encode()
    body += b" " * (-len(body) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(body)) + struct.pack("<I4s", len(body), b"JSON") + body


class GlbExtensionsTest(unittest.TestCase):
    def check(self, data: bytes) -> set[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.glb"
            path.write_bytes(data)
            return fetch_models.glb_extensions(path)

    def test_plain_model_has_no_required_extensions(self):
        self.assertEqual(self.check(glb({"asset": {"version": "2.0"}})), set())

    def test_draco_model_is_reported(self):
        found = self.check(glb({"asset": {"version": "2.0"}, "extensionsRequired": ["KHR_draco_mesh_compression"]}))
        self.assertTrue(found & fetch_models.UNSUPPORTED)

    def test_not_a_glb_is_refused(self):
        with self.assertRaises(ValueError):
            self.check(b'{"asset": {}}' + b" " * 20)

    def test_models_in_repo_load_without_decoders(self):
        index = json.loads(fetch_models.INDEX.read_text(encoding="utf-8"))
        # An entry is a file name or {file, scale} for a v5 model in metres (#396).
        for name in {e if isinstance(e, str) else e["file"] for e in index.values()}:
            with self.subTest(name=name):
                self.assertEqual(fetch_models.glb_extensions(fetch_models.MODELS_DIR / name) & fetch_models.UNSUPPORTED, set())


if __name__ == "__main__":
    unittest.main()
