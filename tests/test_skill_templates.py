"""Integration checks for bundled templates and the existing local engine graph."""
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.schemas import GenerationRequest
from runtime.workflow import build_prompt


BASE = Path(__file__).resolve().parents[1]


class SkillTemplateIntegrationTests(unittest.TestCase):
    def test_template_assets_are_served_by_the_local_app(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(base_dir=BASE, data_dir=Path(directory) / "data",
                                comfy_dir=Path(directory) / "engine")
            with TestClient(create_app(settings, engine=object())) as client:
                catalog = client.get("/skill-templates.json")
                self.assertEqual(catalog.status_code, 200)
                self.assertEqual(len(catalog.json()["templates"]), 9)
                core = client.get("/template-core.js")
                self.assertEqual(core.status_code, 200)
                self.assertIn("H3TemplateCore", core.text)
                home = client.get("/")
                self.assertIn("template-core.js", home.text)
                self.assertIn("Skill 模板库", home.text)
                self.assertIn("connect-src 'self'", home.headers["content-security-policy"])

    def test_every_shot_routes_to_the_existing_local_model_graph(self):
        catalog = json.loads((BASE / "web" / "skill-templates.json").read_text(encoding="utf-8"))
        modes = {"text-image": ("image", "t2i"), "image-image": ("image", "edit"),
                 "text-video": ("video", "t2v"), "image-video": ("video", "i2v"),
                 "reference-video": ("video", "ref2va")}
        for template in catalog["templates"]:
            for shot in template["shots"]:
                with self.subTest(template=template["id"], shot=shot["id"]):
                    model, mode = modes[shot["preset"]]
                    references = mode in {"edit", "i2v", "ref2va"}
                    data = dict(model=model, mode=mode, prompt="template integration fixture",
                                **shot["settings"])
                    if mode == "ref2va":
                        data["reference_asset_ids"] = ["a" * 32]
                    elif references:
                        data["reference_asset_id"] = "a" * 32
                    request = GenerationRequest(**data).model_dump()
                    request["seed"] = 7
                    graph = build_prompt(request, reference_filenames=["fixture.png"] if references else [])
                    expected = ("MiniMaxH3ImageConditioning" if model == "image" else
                                "MiniMaxH3ReferenceToVideo" if mode == "ref2va" else
                                "MiniMaxH3ImageToVideo")
                    self.assertEqual(graph["4"]["class_type"], expected)
                    self.assertTrue(all("http" not in str(node["inputs"]) for node in graph.values()))


if __name__ == "__main__":
    unittest.main()
