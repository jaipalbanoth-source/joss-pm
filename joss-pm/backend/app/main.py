"""JOSS Project Management - FastAPI backend.  Run:  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations
from contextlib import asynccontextmanager

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import seed
from .routers.api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed.seed()
    yield


app = FastAPI(title="JOSS Project Management", version="1.0.0", lifespan=lifespan,
              description="PM Workspace API: Edit Project, Tasks, QA, Jade Contacts, Resource Mgmt and the checked Commit to JOSS.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

# Serve the React UI (frontend/ at the project root) from the same origin: http://localhost:8000/
FRONTEND = Path(os.environ.get("JOSS_FRONTEND", Path(__file__).resolve().parents[2] / "frontend"))
if (FRONTEND / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="ui")
