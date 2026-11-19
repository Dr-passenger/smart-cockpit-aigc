from __future__ import annotations

import hashlib
from pathlib import Path
import socket
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from download_models import inspect_files, model_files
from launch import assert_port_free


class DeploymentTests(unittest.TestCase):
    def test_manifest_deduplicates_shared_encoder(self):
        files = model_files()
        self.assertEqual(len(files), 7)
        self.assertEqual(sum(item["size_bytes"] for item in files), 94_646_241_490)
        self.assertEqual(sum(item["folder"] == "text_encoders" for item in files), 1)

    def test_ref2va_and_fl2va_choose_distinct_video_weights(self):
        video = model_files("video")
        reference = model_files("ref2va")
        self.assertEqual(len(video), 4)
        self.assertEqual(len(reference), 4)
        self.assertEqual(sum(item["size_bytes"] for item in reference), 51_528_041_760)
        self.assertEqual([item["filename"] for item in video if item["folder"] == "diffusion_models"], ["minimax_h3_fl2va_pruned_int8_convrot.safetensors"])
        self.assertEqual([item["filename"] for item in reference if item["folder"] == "diffusion_models"], ["minimax_h3_ref2va_pruned_int8_convrot.safetensors"])
        shared_video = {item["filename"] for item in video if item["folder"] != "diffusion_models"}
        shared_reference = {item["filename"] for item in reference if item["folder"] != "diffusion_models"}
        self.assertEqual(shared_video, shared_reference)

    def test_same_size_corruption_is_rejected_by_full_integrity_check(self):
        original, corrupted = b"valid weights", b"wrong weights"
        self.assertEqual(len(original), len(corrupted))
        with tempfile.TemporaryDirectory(prefix="H3 Chinese path 中文 ") as directory:
            root = Path(directory)
            target = root / "vae/example.safetensors"
            target.parent.mkdir()
            target.write_bytes(corrupted)
            entry = {"folder": "vae", "filename": target.name, "size_bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
            self.assertEqual(inspect_files([entry], root), [])
            self.assertTrue(inspect_files([entry], root, full_hash=True)[0].startswith("SHA256 MISMATCH"))
            target.write_bytes(original)
            self.assertEqual(inspect_files([entry], root, full_hash=True), [])

    def test_missing_and_truncated_models_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = {"folder": "vae", "filename": "test", "size_bytes": 100}
            self.assertTrue(inspect_files([entry], root)[0].startswith("MISSING"))
            (root / "vae").mkdir()
            (root / "vae/test").write_bytes(b"truncated")
            self.assertTrue(inspect_files([entry], root)[0].startswith("SIZE MISMATCH"))

    def test_port_conflict_does_not_close_existing_service(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
            owner.bind(("127.0.0.1", 0))
            owner.listen(1)
            port = owner.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                assert_port_free(port)
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass


if __name__ == "__main__":
    unittest.main()
