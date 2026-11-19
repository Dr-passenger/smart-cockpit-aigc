from __future__ import annotations

import json
from pathlib import Path

import httpx


class EngineError(RuntimeError):
    pass


class ComfyClient:
    """Talk only to the dedicated local ComfyUI instance; never to a cloud API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _request(self, method, path, **kwargs):
        try:
            with httpx.Client(base_url=self.base_url, timeout=30, trust_env=False) as client:
                response = client.request(method, path, **kwargs)
            if response.is_error:
                detail = response.text[:1800]
                raise EngineError(f"本地 ComfyUI 返回 HTTP {response.status_code}: {detail}")
            return response
        except httpx.RequestError as exc:
            raise EngineError("无法连接本机 ComfyUI 引擎，请用 start.bat 启动，检查 data/logs/engine.log") from exc

    def system_stats(self):
        return self._request("GET", "/system_stats").json()

    def object_info(self, node: str):
        return self._request("GET", f"/object_info/{node}").json()

    def upload_image(self, path: Path):
        with path.open("rb") as stream:
            data = self._request("POST", "/upload/image", files={"image": (path.name, stream)},
                                 data={"type": "input", "overwrite": "true"}).json()
        name = data.get("name", "")
        subfolder = data.get("subfolder", "")
        if not name or Path(name).name != name or ".." in Path(subfolder).parts:
            raise EngineError("引擎返回的参考图名称无效")
        return f"{subfolder}/{name}" if subfolder else name

    def submit(self, prompt: dict, client_id: str):
        data = self._request("POST", "/prompt", json={"prompt": prompt, "client_id": client_id}).json()
        if data.get("node_errors") or not data.get("prompt_id"):
            raise EngineError("节点校验失败: " + json.dumps(data, ensure_ascii=False)[:3000])
        return data["prompt_id"]

    def history(self, prompt_id):
        return self._request("GET", f"/history/{prompt_id}").json().get(prompt_id)

    def queue(self):
        return self._request("GET", "/queue").json()

    def cancel(self, prompt_id):
        # The locked core accepts prompt_id for an atomic targeted interrupt.
        # A queue check followed by an empty interrupt has a race with other jobs.
        self._request("POST", "/queue", json={"delete": [prompt_id]})
        self._request("POST", "/interrupt", json={"prompt_id": prompt_id})

    def download_output(self, item: dict, target: Path):
        filename = item.get("filename", "")
        if not filename or Path(filename).name != filename:
            raise EngineError("引擎输出文件名无效")
        params = {"filename": filename, "subfolder": item.get("subfolder", ""),
                  "type": item.get("type", "output")}
        # Streaming avoids keeping a full video in the Studio process's RAM.
        try:
            with httpx.Client(base_url=self.base_url, timeout=120, trust_env=False) as client:
                with client.stream("GET", "/view", params=params) as response:
                    response.raise_for_status()
                    with target.open("wb") as stream:
                        for chunk in response.iter_bytes(1024 * 1024):
                            stream.write(chunk)
        except httpx.HTTPError as exc:
            target.unlink(missing_ok=True)
            raise EngineError("无法读取本地引擎的输出文件") from exc

    def free(self):
        self._request("POST", "/free", json={"unload_models": True, "free_memory": True})
