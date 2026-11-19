from __future__ import annotations

import copy
import json
import logging
import queue
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .comfy_client import ComfyClient, EngineError
from .config import Settings
from .schemas import GenerationRequest
from .system import model_inventory

log = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}


def now():
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self, settings: Settings, engine: ComfyClient, poll_interval=1.0):
        self.settings = settings
        self.engine = engine
        self.poll_interval = poll_interval
        self.jobs = {}
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.cancels = {}
        self.stopping = threading.Event()
        self.next_cleanup = 0.0
        self.thread = None
        settings.prepare()
        for path in (settings.data_dir / "jobs").glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["status"] not in TERMINAL:
                    if job.get("engine_prompt_id"):
                        job["cancel_pending"] = True
                    job.update(status="failed", message="上次服务退出，任务已中止；请重新提交", error="服务重启时恢复的未完成任务")
                    self._persist(job)
                self.jobs[job["id"]] = job
            except (ValueError, KeyError, OSError):
                log.warning("无法读取历史任务 %s", path.name)

    def start(self):
        self.thread = threading.Thread(target=self._work, daemon=True, name="h3-job-worker")
        self.thread.start()

    def stop(self):
        self.stopping.set()
        with self.lock:
            active = [job["id"] for job in self.jobs.values() if job["status"] not in TERMINAL]
        for job_id in active:
            try:
                self.cancel(job_id)
            except EngineError:
                pass
        if self.thread:
            self.thread.join(timeout=3)

    def _persist(self, job):
        target = self.settings.data_dir / "jobs" / f"{job['id']}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)

    def _update(self, job_id, **fields):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] == "cancelled" and fields.get("status") != "cancelled" and not fields.get("cancel_pending"):
                return
            job.update(fields, updated_at=now())
            self._persist(job)

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return copy.deepcopy(self.jobs[job_id])

    def history(self):
        with self.lock:
            return sorted(copy.deepcopy(list(self.jobs.values())), key=lambda j: j["created_at"], reverse=True)

    def preflight(self, request: GenerationRequest):
        inventory = {m["id"]: m for m in model_inventory(self.settings)}
        model = inventory.get("ref2va" if request.mode == "ref2va" else request.model)
        if not model or not model["ready"]:
            missing = [f["filename"] for f in model["files"] if not f["ready"]] if model else ["runtime/models.json"]
            raise EngineError("本地模型尚未备齐或大小校验失败: " + ", ".join(missing) + "。请先运行 setup.bat 或下载脚本。")
        self.engine.system_stats()
        from runtime.workflow import required_nodes
        references = request.reference_asset_ids or ([request.reference_asset_id] if request.reference_asset_id else [])
        for node in required_nodes(request.model, bool(references), mode=request.mode):
            if node not in self.engine.object_info(node):
                raise EngineError(f"引擎缺少节点 {node}；请重新运行 setup.bat 安装锁定的 ComfyUI 版本")
        for asset_id in references:
            self.asset_path(asset_id)

    def asset_path(self, asset_id: str):
        # IDs are server generated, and never interpreted as paths.
        if len(asset_id) != 32 or any(c not in "0123456789abcdef" for c in asset_id):
            raise EngineError("参考图 ID 无效")
        metadata_path = self.settings.data_dir / "assets" / f"{asset_id}.json"
        if not metadata_path.is_file():
            raise EngineError("参考图不存在，请重新上传")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        name = metadata["filename"]
        if Path(name).name != name:
            raise EngineError("参考图文件名无效")
        path = self.settings.data_dir / "assets" / name
        if not path.is_file():
            raise EngineError("参考图文件丢失，请重新上传")
        return path

    def submit(self, request: GenerationRequest, *, preflight=True):
        if preflight:
            self.preflight(request)
        with self.lock:
            if sum(j["status"] not in TERMINAL for j in self.jobs.values()) >= 20:
                raise EngineError("队列已满（20项），请等待或取消任务")
            request_data = request.model_dump(exclude_none=True)
            if request.seed == -1:
                request_data["seed"] = secrets.randbelow(2**32)
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "status": "queued", "progress": 0,
                   "message": "等待本机引擎，任务串行执行", "created_at": now(), "updated_at": now(),
                   "request": request_data, "outputs": [], "error": None}
            self.jobs[job_id] = job
            self.cancels[job_id] = threading.Event()
            self._persist(job)
            self.pending.put(job_id)
        return self.get(job_id)

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job["status"] in TERMINAL and not job.get("cancel_pending"):
                return job
            self.cancels.setdefault(job_id, threading.Event()).set()
        if job.get("engine_prompt_id"):
            self._confirm_cancel(job_id, job["engine_prompt_id"])
        else:
            self._update(job_id, status="cancelled", message="任务已取消", progress=0)
        return self.get(job_id)

    def _confirm_cancel(self, job_id, prompt_id):
        self._update(job_id, status="cancelled", engine_prompt_id=prompt_id, cancel_pending=True,
                     message="已记录取消请求，正在确认引擎中止", progress=0)
        try:
            self.engine.cancel(prompt_id)
        except EngineError as exc:
            self._update(job_id, status="failed", cancel_pending=True, error=str(exc),
                         message="取消尚未确认，可能仍在本机引擎执行；恢复连接后自动重试中止")
        else:
            self._update(job_id, status="cancelled", cancel_pending=False, error=None,
                         message="任务已取消，本机引擎已确认中止请求")

    def _cleanup_pending(self):
        with self.lock:
            pending = [(j["id"], j["engine_prompt_id"]) for j in self.jobs.values()
                       if j.get("cancel_pending") and j.get("engine_prompt_id")]
        for job_id, prompt_id in pending:
            self._confirm_cancel(job_id, prompt_id)

    def _work(self):
        while not self.stopping.is_set():
            if time.monotonic() >= self.next_cleanup:
                self._cleanup_pending()
                self.next_cleanup = time.monotonic() + 10
            try:
                job_id = self.pending.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if not self.cancels[job_id].is_set():
                    self._run(job_id)
            except Exception as exc:
                log.warning("任务 %s 失败: %s", job_id, exc)
                self._update(job_id, status="failed", error=str(exc)[:4000], message="生成失败，请查看错误信息")
            finally:
                if self.settings.unload_after_job:
                    try:
                        self.engine.free()
                    except EngineError:
                        pass
                self.pending.task_done()

    def _run(self, job_id):
        from runtime.workflow import build_prompt, video_frame_count
        job = self.get(job_id)
        request = job["request"]
        cancel = self.cancels[job_id]
        self._update(job_id, status="running", progress=5, message="准备本地工作流与参考素材")
        reference_filename = None
        reference_filenames = None
        if request.get("mode") == "ref2va":
            reference_filenames = [self.engine.upload_image(self.asset_path(asset_id))
                                   for asset_id in request.get("reference_asset_ids", [])]
        elif request.get("reference_asset_id"):
            reference_filename = self.engine.upload_image(self.asset_path(request["reference_asset_id"]))
        prompt = build_prompt(request, reference_filename, reference_filenames=reference_filenames)
        if cancel.is_set():
            return
        prompt_id = self.engine.submit(prompt, job_id)
        if cancel.is_set():
            self._confirm_cancel(job_id, prompt_id)
            return
        actual = {}
        if request["model"] == "video":
            frames = video_frame_count(request["duration"])
            actual = {"frames": frames, "fps": 24, "duration_seconds": round(frames / 24, 3)}
        self._update(job_id, engine_prompt_id=prompt_id, actual=actual, progress=10,
                     message="本地推理中，首次加载可能很久；此进度表示执行阶段，不估算采样百分比")
        if cancel.is_set():
            self._confirm_cancel(job_id, prompt_id)
            return
        started = time.monotonic()
        failures = 0
        while not self.stopping.is_set():
            if cancel.is_set():
                self._confirm_cancel(job_id, prompt_id)
                return
            if time.monotonic() - started > self.settings.job_timeout:
                self.engine.cancel(prompt_id)
                raise EngineError("任务超过时间上限，已请求中止；可在 .env 调整 STUDIO_JOB_TIMEOUT")
            try:
                result = self.engine.history(prompt_id)
                failures = 0
            except EngineError:
                failures += 1
                if failures >= 5:
                    raise
                cancel.wait(self.poll_interval)
                continue
            if result:
                status = result.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    errors = [m[1] for m in messages if len(m) > 1 and m[0] in {"execution_error", "execution_interrupted"}]
                    text = json.dumps(errors or messages, ensure_ascii=False)[:3500]
                    if "out of memory" in text.lower():
                        text = "显存或内存不足，请降低分辨率/时长，关闭其他GPU程序；16GB未保证可用。\n" + text
                    raise EngineError(text or "本地引擎执行失败")
                if status.get("completed") or status.get("status_str") == "success":
                    if cancel.is_set():
                        return
                    self._update(job_id, progress=90, message="保存本地生成结果")
                    outputs = self._save_outputs(job_id, result.get("outputs", {}))
                    if not outputs:
                        raise EngineError("引擎执行结束但没有图像或视频输出，请检查节点版本及 data/logs/engine.log")
                    self._update(job_id, status="succeeded", progress=100, outputs=outputs, message="生成完成，结果已保存到本机")
                    return
            cancel.wait(self.poll_interval)

    def _save_outputs(self, job_id, outputs):
        directory = self.settings.data_dir / "outputs" / job_id
        directory.mkdir(parents=True, exist_ok=True)
        collected, seen = [], set()
        for node_output in outputs.values():
            for key in ("images", "videos", "gifs"):
                for item in node_output.get(key, []):
                    name = item.get("filename", "")
                    extension = Path(name).suffix.lower()
                    identity = (item.get("subfolder", ""), name, item.get("type", "output"))
                    if identity in seen or extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}:
                        continue
                    seen.add(identity)
                    safe_name = f"{len(collected) + 1:02d}{extension}"
                    self.engine.download_output(item, directory / safe_name)
                    collected.append({"url": f"/outputs/{job_id}/{safe_name}", "name": name,
                                      "kind": "video" if extension in {".mp4", ".webm"} else "image"})
        return collected
