"""Vercel entry point: exposes the FastAPI app (all routes are rewritten here by vercel.json)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.main import app  # noqa: E402,F401
