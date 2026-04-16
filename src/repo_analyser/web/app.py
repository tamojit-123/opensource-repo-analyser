from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from repo_analyser.agents.workflow import CoordinatorService
from repo_analyser.config import get_settings
from repo_analyser.logging_utils import configure_logging, get_logger, reset_request_id, set_request_id
from repo_analyser.models import AgentLogEvent, ChatRequest


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    base_dir = Path(__file__).resolve().parent
    app = FastAPI(title=settings.app_name)
    logger = get_logger(__name__, "web")
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")
    app.mount("/generated_issues", StaticFiles(directory=str(settings.output_dir)), name="generated_issues")
    coordinator = CoordinatorService(settings)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = set_request_id(request_id)
        started = time.perf_counter()
        logger.info("Incoming request %s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers["x-request-id"] = request_id
            logger.info("Completed request %s %s status=%s duration_ms=%s", request.method, request.url.path, response.status_code, elapsed_ms)
            return response
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception("Request failed %s %s after %sms: %s", request.method, request.url.path, elapsed_ms, exc)
            raise
        finally:
            reset_request_id(token)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        logger.debug("Rendering index page.")
        return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name})

    @app.post("/api/analyze/stream")
    async def analyze_stream(payload: ChatRequest) -> StreamingResponse:
        logger.info("Starting streaming analysis for repo_url=%s", payload.repo_url)
        async def event_stream() -> AsyncIterator[str]:
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def emit_log(event: AgentLogEvent) -> None:
                logger.info(
                    "Streaming agent event agent=%s status=%s message=%s",
                    event.agent,
                    event.status,
                    event.message,
                    extra={"agent": event.agent},
                )
                await queue.put(_sse({"type": "log", "payload": event.model_dump(mode="json")}))

            async def run_analysis() -> None:
                try:
                    result = await coordinator.analyze(str(payload.repo_url), emit_log)
                    logger.info("Streaming final analysis result for %s", payload.repo_url)
                    await queue.put(_sse({"type": "result", "payload": result.model_dump(mode="json")}))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Streaming analysis failed for %s: %s", payload.repo_url, exc)
                    error = AgentLogEvent(agent="coordinator", status="failed", message=str(exc))
                    await queue.put(_sse({"type": "log", "payload": error.model_dump(mode="json")}))
                finally:
                    await queue.put(None)

            task = asyncio.create_task(run_analysis())
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    yield item
            finally:
                await task

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        logger.debug("Health check requested.")
        return {"status": "ok"}

    return app


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
