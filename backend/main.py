from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .comfy_client import ComfyClient, EngineError
from .config import Settings
from .jobs import JobManager
from .schemas import GenerationRequest
from .system import inspect_system


def create_app(settings: Settings | None = None, engine: ComfyClient | None = None):
    settings = settings or Settings()
    settings.prepare()
    engine = engine or ComfyClient(settings.comfy_url)
    manager = JobManager(settings, engine)

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        yield
        await asyncio.to_thread(manager.stop)

    app = FastAPI(title="智能座舱AIGC", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.manager = manager
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed = {f"http://127.0.0.1:{settings.port}", f"http://localhost:{settings.port}",
                       f"http://[::1]:{settings.port}"}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "仅接受本机工作台同源请求"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "不允许跨站操作本机模型"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
        return response

    @app.exception_handler(EngineError)
    async def engine_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/api/health")
    def health():
        return {"ok": True, "offline": True, "service": "minimax-h3-studio"}

    @app.get("/api/system")
    def system():
        return inspect_system(settings, engine)

    @app.get("/api/history")
    def history():
        return {"jobs": manager.history()}

    @app.post("/api/jobs", status_code=201)
    def submit(request: GenerationRequest):
        return manager.submit(request)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return manager.get(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在")

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        try:
            return manager.cancel(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在")

    @app.post("/api/assets", status_code=201)
    async def upload(file: UploadFile = File(...)):
        asset_id = uuid.uuid4().hex
        limit = 20 * 1024 * 1024
        content = bytearray()
        try:
            while chunk := await file.read(1024 * 1024):
                content.extend(chunk)
                if len(content) > limit:
                    raise HTTPException(413, "参考图最多20MB")
        finally:
            await file.close()
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = ".png"
        elif content.startswith(b"\xff\xd8\xff"):
            extension = ".jpg"
        elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            extension = ".webp"
        else:
            raise HTTPException(415, "请选择PNG、JPEG或WebP图片")
        name = asset_id + extension
        (settings.data_dir / "assets" / name).write_bytes(content)
        metadata = {"id": asset_id, "filename": name, "name": Path(file.filename or name).name}
        (settings.data_dir / "assets" / f"{asset_id}.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return {"id": asset_id, "url": f"/assets/{name}", "name": metadata["name"]}

    @app.get("/assets/{filename}")
    def get_asset(filename: str):
        # Serve media only, never the metadata files in this directory.
        if Path(filename).suffix.lower() not in {".png", ".jpg", ".webp"} or Path(filename).name != filename:
            raise HTTPException(404)
        path = settings.data_dir / "assets" / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    app.mount("/outputs", StaticFiles(directory=settings.data_dir / "outputs"), name="outputs")
    web = settings.base_dir / "web"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=app.state.settings.port, log_level="info")
