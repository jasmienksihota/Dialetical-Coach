"""FastAPI application: JSON API + static single-page frontend (localhost only)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import conversations as convs
from . import exercises, library
from .config import ROOT, TAGS, Settings
from .db import Database
from .errors import AppError
from .export import export_markdown
from .ingest import ingest_file
from .modes import LEVELS, MODES, RUBRIC_NOTE
from .providers import make_provider_factory
from .retrieval import Scope, get_retriever
from .tutor import Services, chat_turn

STATIC = Path(__file__).parent / "static"
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}
FIXTURE_DIR = ROOT / "fixtures" / "synthetic"
FIXTURE_TAGS = {  # demo fixtures only: suggested tags for the SYNTHETIC files
    "synthetic_a_mill_town_notes.md": ["foundations"],
    "synthetic_b_workshop_handbook.txt": ["investigation", "cadre"],
    "synthetic_c_harbour_primer.pdf": ["organization", "cadre"],
    "synthetic_injection_notes.txt": ["foundations"],
    "synthetic_e_scanned_like.pdf": [],
}


class ScopeIn(BaseModel):
    doc_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    include_secondary: bool = False


class ConversationIn(BaseModel):
    title: str = ""
    provider: str = "demo"
    scope: ScopeIn = Field(default_factory=ScopeIn)


class ConversationPatch(BaseModel):
    title: str | None = None
    scope: ScopeIn | None = None


class MessageIn(BaseModel):
    text: str
    intent: str = "ask"


class FlagIn(BaseModel):
    block_index: int | None = None
    chunk_id: str | None = None
    note: str = ""


class ApprovalIn(BaseModel):
    approved: bool


class ExerciseIn(BaseModel):
    mode: str = "dialectical"
    level: str = "beginner"
    scenario_kind: str = "fictional"
    multi_source: bool = True
    focus: str = ""
    historical_topic: str = ""
    provider: str = "demo"
    scope: ScopeIn = Field(default_factory=ScopeIn)
    allow_single_source: bool = False


class ExerciseActionIn(BaseModel):
    action: str
    text: str = ""
    confirm: bool = False


def create_app(settings: Settings | None = None, provider_factory=None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.db_path, force_no_fts=settings.force_no_fts)
    svc = Services(settings=settings, db=db, retriever=get_retriever(db),
                   make_provider=provider_factory or make_provider_factory(settings))
    allowed_hosts = set(LOOPBACK) | {settings.host}

    app = FastAPI(title="Source-Grounded Reasoning Tutor", docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.svc = svc

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "")
        name = host[: host.index("]") + 1] if host.startswith("[") else host.split(":")[0]
        if name not in allowed_hosts:
            return JSONResponse({"detail": "This app only answers on localhost."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
            if urlparse(origin).netloc != host:
                return JSONResponse({"detail": "Cross-origin requests are refused."}, status_code=403)
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    # ----------------------------------------------------------------- status
    @app.get("/api/status")
    def status():
        with db.tx() as c:
            counts = {
                "documents": c.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "approved": c.execute("SELECT COUNT(*) FROM documents WHERE approved=1").fetchone()[0],
                "conversations": c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            }
        return {**settings.public_dict(), "retrieval_mode": db.retrieval_mode,
                "retrieval_note": ("Lexical (word-matching) retrieval only. It does not match "
                                   "synonyms or paraphrases and is not semantic or hybrid search."),
                "tags": [{"slug": s, "label": l} for s, l in TAGS], "counts": counts,
                "modes": [{"key": k, "title": v["title"]} for k, v in MODES.items()],
                "levels": LEVELS, "rubric_note": RUBRIC_NOTE}

    # ----------------------------------------------------------------- library
    @app.post("/api/documents")
    async def upload(file: UploadFile = File(...), title: str = Form(""), author: str = Form(""),
                     date: str = Form(""), edition: str = Form(""), tags: str = Form(""),
                     kind: str = Form("primary")):
        data = await file.read(settings.max_upload_bytes + 1)
        res = ingest_file(db, settings, file.filename or "upload", data, title=title, author=author,
                          date=date, edition=edition, tags=[t for t in tags.split(",") if t.strip()],
                          kind=kind)
        with db.tx() as c:
            return {**res, "document": library.get_document(c, res["document_id"])}

    @app.post("/api/demo/fixtures")
    def load_fixtures():
        """Import the clearly-labeled SYNTHETIC demo documents (unapproved)."""
        results = []
        for name, tags in FIXTURE_TAGS.items():
            f = FIXTURE_DIR / name
            if f.is_file():
                r = ingest_file(db, settings, name, f.read_bytes(), tags=tags)
                results.append({"filename": name, **r})
        notes = FIXTURE_DIR / "synthetic_secondary_notes.md"
        if notes.is_file():
            r = ingest_file(db, settings, notes.name, notes.read_bytes(), kind="secondary_notes")
            results.append({"filename": notes.name, **r})
        return {"imported": results,
                "message": "Synthetic fixtures imported UNAPPROVED. They are invented test texts, not real sources."}

    @app.get("/api/documents")
    def documents():
        with db.tx() as c:
            return library.list_documents(c)

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str):
        with db.tx() as c:
            return library.get_document(c, doc_id)

    @app.patch("/api/documents/{doc_id}")
    async def patch_document(doc_id: str, request: Request):
        body = await request.json()
        with db.tx() as c:
            return library.update_document(c, doc_id, body)

    @app.post("/api/documents/{doc_id}/approval")
    def approval(doc_id: str, body: ApprovalIn):
        with db.tx() as c:
            return library.set_approval(c, doc_id, body.approved)

    @app.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: str):
        with db.tx() as c:
            library.delete_document(c, settings, doc_id)
        return {"deleted": doc_id}

    @app.get("/api/documents/{doc_id}/chunks")
    def doc_chunks(doc_id: str, offset: int = 0, limit: int = 40):
        with db.tx() as c:
            return library.document_chunks(c, doc_id, offset, limit)

    @app.get("/api/passages/{chunk_id}")
    def passage(chunk_id: str, context: int = 2):
        with db.tx() as c:
            return library.get_passage(c, chunk_id, max(0, min(context, 5)))

    @app.get("/api/search")
    def search(q: str, doc_ids: str = "", tags: str = "", include_secondary: bool = False,
               limit: int = 8):
        scope = Scope([d for d in doc_ids.split(",") if d], [t for t in tags.split(",") if t],
                      include_secondary)
        with db.tx() as c:
            res = svc.retriever.search(c, q, scope, limit=max(1, min(limit, 25)))
        return {"hits": res.hits, "strength": res.strength, "notes": res.notes,
                "distinct_docs": res.distinct_docs, "terms": res.terms, "mode": res.mode}

    # ----------------------------------------------------------------- conversations
    def _check_provider(kind: str):
        svc.make_provider(kind)    # raises AppError with a setup message if live is unconfigured

    @app.post("/api/conversations")
    def new_conversation(body: ConversationIn):
        if body.provider not in ("demo", "live"):
            raise AppError("provider must be 'demo' or 'live'.", 400)
        _check_provider(body.provider)
        with db.tx() as c:
            cid = convs.create_conversation(c, body.title or "New study chat", "chat", body.provider,
                                            body.scope.model_dump())
            return convs.get_conversation(c, cid)

    @app.get("/api/conversations")
    def list_conversations():
        with db.tx() as c:
            return convs.list_conversations(c)

    @app.get("/api/conversations/{cid}")
    def get_conversation(cid: str):
        with db.tx() as c:
            conv = convs.get_conversation(c, cid)
        if conv["exercise"]:
            conv["exercise"] = exercises.public_exercise(conv["exercise"])
        return conv

    @app.patch("/api/conversations/{cid}")
    def patch_conversation(cid: str, body: ConversationPatch):
        with db.tx() as c:
            convs.update_conversation(c, cid, title=body.title,
                                      scope=body.scope.model_dump() if body.scope else None)
            return convs.get_conversation(c, cid)

    @app.delete("/api/conversations/{cid}")
    def remove_conversation(cid: str):
        with db.tx() as c:
            convs.delete_conversation(c, cid)
        return {"deleted": cid}

    @app.post("/api/conversations/{cid}/messages")
    def post_message(cid: str, body: MessageIn):
        return chat_turn(svc, cid, body.text, body.intent)

    @app.post("/api/messages/{mid}/flags")
    def flag(mid: int, body: FlagIn):
        with db.tx() as c:
            fid = convs.add_flag(c, mid, body.block_index, body.chunk_id, body.note)
        return {"id": fid}

    @app.delete("/api/flags/{fid}")
    def unflag(fid: int):
        with db.tx() as c:
            convs.delete_flag(c, fid)
        return {"deleted": fid}

    # ----------------------------------------------------------------- exercises
    @app.post("/api/exercises")
    def start_exercise(body: ExerciseIn):
        if body.provider not in ("demo", "live"):
            raise AppError("provider must be 'demo' or 'live'.", 400)
        return exercises.start_exercise(svc, {**body.model_dump(), "scope": body.scope.model_dump()})

    @app.post("/api/conversations/{cid}/exercise")
    def exercise_step(cid: str, body: ExerciseActionIn):
        return exercises.exercise_action(svc, cid, body.action, body.text, body.confirm)

    # ----------------------------------------------------------------- export
    @app.get("/api/conversations/{cid}/export.md")
    def export(cid: str, transcript: bool = False):
        with db.tx() as c:
            md = export_markdown(c, cid, transcript)
            title = convs.get_row(c, cid)["title"]
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in title)[:60].strip("-") or "session"
        return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{safe}.md"'})

    # ----------------------------------------------------------------- frontend
    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def app_factory() -> FastAPI:
    return create_app()
