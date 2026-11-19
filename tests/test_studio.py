"""CPU-only integration checks. The fake engine never claims GPU inference works."""
import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.comfy_client import ComfyClient, EngineError
from backend.config import Settings
from backend.jobs import JobManager
from backend.main import create_app
from backend.schemas import GenerationRequest
from runtime.workflow import build_prompt, required_nodes, video_frame_count

PNG = b"\x89PNG\r\n\x1a\n" + b"test-fixture"


class FakeEngine:
    def __init__(self):
        self.submitted = []
        self.cancelled = []
        self.freed = 0
        self.complete = threading.Event()
        self.error = False

    def system_stats(self):
        return {"devices": []}

    def object_info(self, node):
        return {node: {"input": {}}}

    def submit(self, prompt, client_id):
        self.submitted.append(prompt)
        return client_id

    def history(self, prompt_id):
        if not self.complete.is_set():
            return None
        if self.error:
            return {"status": {"status_str": "error", "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]]}}
        return {"status": {"completed": True, "status_str": "success"},
                "outputs": {"8": {"images": [{"filename": "result.png", "type": "output"}]}}}

    def cancel(self, prompt_id):
        self.cancelled.append(prompt_id)

    def download_output(self, item, target):
        target.write_bytes(PNG)

    def upload_image(self, path):
        return path.name

    def free(self):
        self.freed += 1


def wait_status(manager, job_id, statuses):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job["status"] in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Timed out: {manager.get(job_id)}")


class WorkflowTests(unittest.TestCase):
    def test_cancel_is_atomic_and_never_uses_a_global_interrupt(self):
        engine = ComfyClient("http://127.0.0.1:8188")
        calls = []
        engine._request = lambda method, path, **kw: calls.append((method, path, kw))
        engine.cancel("specific-prompt")
        self.assertEqual(calls, [("POST", "/queue", {"json": {"delete": ["specific-prompt"]}}),
                                 ("POST", "/interrupt", {"json": {"prompt_id": "specific-prompt"}})])

    def test_all_four_workflows_have_valid_links_and_offline_nodes(self):
        for model in ("image", "video"):
            for reference in (None, "upload.png"):
                graph = build_prompt({"model": model, "prompt": "a red flower", "seed": 7}, reference)
                self.assertEqual(set(required_nodes(model, bool(reference))), {n["class_type"] for n in graph.values()})
                for node in graph.values():
                    for value in node["inputs"].values():
                        if isinstance(value, list):
                            self.assertIn(value[0], graph)
                self.assertTrue(all("http" not in str(n["inputs"]) for n in graph.values()))
                if model == "video":
                    self.assertEqual(graph["14"]["inputs"]["format.codec"], "h264")
                    self.assertEqual(graph["13"]["inputs"]["audio"], ["12", 0])
                elif reference:
                    self.assertEqual(graph["4"]["inputs"]["images.image_1"], ["20", 0])

    def test_frame_alignment_is_reportable_and_never_shorter_than_requested(self):
        defaults = GenerationRequest(model="video", prompt="a moving flower")
        self.assertEqual((defaults.width, defaults.height, defaults.steps), (512, 512, 20))
        for seconds in range(4, 16):
            frames = video_frame_count(seconds)
            self.assertEqual(frames % 17, 5)
            self.assertGreaterEqual(frames, seconds * 24)
        self.assertEqual(video_frame_count(4), 107)

    def test_unsupported_requests_fail_before_loading_weights(self):
        for fields in ({"steps": 5}, {"width": 1001}, {"mode": "i2v"}):
            with self.assertRaises(ValueError):
                build_prompt({"model": "image", "prompt": "test", **fields})
        with self.assertRaises(ValueError):
            build_prompt({"model": "image", "prompt": "test"}, "../secret.png")
        for value in ("https://api.example.com", "http://192.168.1.1:8188", "http://user:pass@localhost:8188"):
            with self.assertRaises(ValueError):
                Settings(comfy_url=value)

    def test_ref2va_uses_a_distinct_checkpoint_and_ordered_reference_slots(self):
        graph = build_prompt({"model": "video", "mode": "ref2va", "prompt": "<Picture 1> and <Picture 2> in a cockpit", "seed": 7},
                             reference_filenames=["first.png", "second.png"])
        self.assertEqual(graph["4"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertIn("ref2va", graph["1"]["inputs"]["unet_name"])
        self.assertNotIn("first_frame", graph["4"]["inputs"])
        self.assertEqual(graph["4"]["inputs"]["ref_images.ref_image_0"], ["20", 0])
        self.assertEqual(graph["4"]["inputs"]["ref_images.ref_image_1"], ["21", 0])
        self.assertEqual(graph["20"]["inputs"]["image"], "first.png")
        self.assertEqual(graph["21"]["inputs"]["image"], "second.png")
        self.assertIn("MiniMaxH3ReferenceToVideo", required_nodes("video", True, mode="ref2va"))

    def test_ref2va_request_validation_requires_one_to_nine_images(self):
        with self.assertRaises(ValueError):
            GenerationRequest(model="video", mode="ref2va", prompt="test")
        with self.assertRaises(ValueError):
            GenerationRequest(model="video", mode="ref2va", prompt="test", reference_asset_ids=[f"{i:032x}" for i in range(10)])
        request = GenerationRequest(model="video", mode="ref2va", prompt="test",
                                    reference_asset_ids=["a" * 32, "b" * 32])
        self.assertEqual(request.reference_asset_ids, ["a" * 32, "b" * 32])


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(base_dir=root, data_dir=root / "data", comfy_dir=root / "engine")
        (root / "runtime").mkdir()
        (root / "runtime" / "models.json").write_text(json.dumps({"models": [
            {"id": m, "name": m, "files": [{"filename": "fixture.bin", "folder": "vae", "size_bytes": 3}]}
            for m in ("image", "video", "ref2va")]}), encoding="utf-8")
        target = root / "engine" / "models" / "vae"
        target.mkdir(parents=True)
        (target / "fixture.bin").write_bytes(b"123")
        self.engine = FakeEngine()
        self.managers = []

    def tearDown(self):
        for manager in self.managers:
            manager.stop()
        self.temp.cleanup()

    def manager(self):
        manager = JobManager(self.settings, self.engine, poll_interval=0.01)
        self.managers.append(manager)
        return manager

    def test_queue_serializes_and_persists_successful_output_and_seed(self):
        manager = self.manager()
        one = manager.submit(GenerationRequest(model="image", prompt="one"))
        two = manager.submit(GenerationRequest(model="image", prompt="two"))
        manager.start()
        wait_status(manager, one["id"], {"running"})
        self.assertEqual(manager.get(two["id"])["status"], "queued")
        self.engine.complete.set()
        result = wait_status(manager, two["id"], {"succeeded"})
        self.assertGreaterEqual(result["request"]["seed"], 0)
        self.assertTrue(result["outputs"][0]["url"].startswith("/outputs/"))
        self.assertEqual(len(self.engine.submitted), 2)
        saved = json.loads((self.settings.data_dir / "jobs" / f"{two['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "succeeded")
        self.assertEqual((self.settings.data_dir / "outputs" / two["id"] / "01.png").read_bytes(), PNG)

    def test_cancel_queued_job_never_submits_and_running_job_is_interrupted(self):
        manager = self.manager()
        queued = manager.submit(GenerationRequest(model="image", prompt="cancel"))
        manager.cancel(queued["id"])
        running = manager.submit(GenerationRequest(model="image", prompt="run"))
        manager.start()
        deadline = time.monotonic() + 4
        while not manager.get(running["id"]).get("engine_prompt_id") and time.monotonic() < deadline:
            time.sleep(0.01)
        manager.cancel(running["id"])
        self.assertEqual(manager.get(running["id"])["status"], "cancelled")
        self.assertEqual(len(self.engine.submitted), 1)
        self.assertIn(running["id"], self.engine.cancelled)

    def test_oom_is_a_failed_job_and_survives_service_restart(self):
        self.engine.error = True
        self.engine.complete.set()
        manager = self.manager()
        job = manager.submit(GenerationRequest(model="image", prompt="fail"))
        manager.start()
        result = wait_status(manager, job["id"], {"failed"})
        self.assertIn("显存或内存不足", result["error"])
        manager.stop()
        restarted = self.manager()
        self.assertEqual(restarted.get(job["id"])["status"], "failed")

    def test_interrupted_history_is_not_requeued_after_restart(self):
        manager = self.manager()
        job = manager.submit(GenerationRequest(model="image", prompt="interrupted"))
        restarted = self.manager()
        self.assertEqual(restarted.get(job["id"])["status"], "failed")

    def test_restart_cancels_orphaned_engine_prompt_before_new_jobs(self):
        manager = self.manager()
        job = manager.submit(GenerationRequest(model="image", prompt="interrupted"))
        manager._update(job["id"], status="running", engine_prompt_id="old-prompt")
        restarted = self.manager()
        restarted.start()
        deadline = time.monotonic() + 4
        while "old-prompt" not in self.engine.cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn("old-prompt", self.engine.cancelled)

    def test_video_output_in_core_images_history_is_preserved_as_video(self):
        manager = self.manager()
        outputs = manager._save_outputs("fixture-job", {"14": {"images": [
            {"filename": "clip.mp4", "subfolder": "MiniMax-H3-Studio", "type": "output"}], "animated": [True]}})
        self.assertEqual(outputs[0]["kind"], "video")
        self.assertTrue(outputs[0]["url"].endswith("01.mp4"))

    def test_failed_cancel_is_not_reported_as_confirmed_and_can_recover(self):
        manager = self.manager()
        job = manager.submit(GenerationRequest(model="image", prompt="cancel during disconnect"))
        manager._update(job["id"], status="running", engine_prompt_id="lost-prompt")
        original_cancel = self.engine.cancel

        def disconnected(prompt_id):
            raise EngineError("connection lost")

        self.engine.cancel = disconnected
        result = manager.cancel(job["id"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cancel_pending"])
        self.assertIn("取消尚未确认", result["message"])
        self.engine.cancel = original_cancel
        manager._cleanup_pending()
        recovered = manager.get(job["id"])
        self.assertEqual(recovered["status"], "cancelled")
        self.assertFalse(recovered["cancel_pending"])

    def test_http_validation_upload_origin_and_missing_models(self):
        app = create_app(self.settings, self.engine)
        with TestClient(app) as client:
            self.assertTrue(client.get("/api/health").json()["offline"])
            self.assertIsNone(client.get("/api/system").json()["gpu"])
            self.assertEqual(client.post("/api/jobs", json={"model": "image", "prompt": "x", "backend": "api"}).status_code, 422)
            self.assertEqual(client.post("/api/jobs", json={"model": "image", "prompt": "x", "steps": 8}).status_code, 422)
            self.assertEqual(client.post("/api/jobs", headers={"Origin": "https://example.com"}, json={"model": "image", "prompt": "x"}).status_code, 403)
            self.assertEqual(client.get("/api/health", headers={"Host": "evil.example"}).status_code, 400)
            self.assertEqual(client.post("/api/assets", files={"file": ("file.html", b"<html>bad</html>")}).status_code, 415)
            upload = client.post("/api/assets", files={"file": ("../image.png", PNG, "image/png")})
            self.assertEqual(upload.status_code, 201)
            asset = upload.json()
            self.assertEqual(client.get(asset["url"]).content, PNG)
            self.assertEqual(client.get(f"/assets/{asset['id']}.json").status_code, 404)
            (self.settings.comfy_dir / "models" / "vae" / "fixture.bin").unlink()
            fail = client.post("/api/jobs", json={"model": "image", "prompt": "x"})
            self.assertEqual(fail.status_code, 503)
            self.assertIn("fixture.bin", fail.json()["detail"])
            self.assertEqual(client.get("/api/jobs/unknown").status_code, 404)

    def test_ref2va_http_uploads_are_submitted_in_order(self):
        self.engine.complete.set()
        app = create_app(self.settings, self.engine)
        with TestClient(app) as client:
            refs = [client.post("/api/assets", files={"file": (name, PNG, "image/png")}).json()
                    for name in ("character.png", "cockpit.png")]
            response = client.post("/api/jobs", json={"model": "video", "mode": "ref2va",
                "prompt": "<Picture 1> sits in the cockpit from <Picture 2>",
                "reference_asset_ids": [asset["id"] for asset in refs]})
            self.assertEqual(response.status_code, 201)
            result = wait_status(app.state.manager, response.json()["id"], {"succeeded", "failed"})
            self.assertEqual(result["status"], "succeeded")
            graph = self.engine.submitted[-1]
            self.assertEqual(graph["4"]["class_type"], "MiniMaxH3ReferenceToVideo")
            for index, asset in enumerate(refs):
                self.assertEqual(graph[str(20 + index)]["inputs"]["image"], asset["url"].rsplit("/", 1)[-1])

    def test_ref2va_preflight_checks_reference_checkpoint_not_fl2va(self):
        manifest_path = self.settings.base_dir / "runtime" / "models.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["models"][2]["files"][0]["filename"] = "reference-only.bin"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        manager = self.manager()
        manager.preflight(GenerationRequest(model="video", prompt="text video"))
        with self.assertRaisesRegex(EngineError, "reference-only.bin"):
            manager.preflight(GenerationRequest(model="video", mode="ref2va", prompt="ref video", reference_asset_ids=["a" * 32]))


if __name__ == "__main__":
    unittest.main()
