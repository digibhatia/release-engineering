"""Entrypoint. The actual FastAPI app lives in src/interfaces/api.py.
Run with: uvicorn app:app --reload --port 8000
"""

from src.interfaces.api import app  # noqa: F401
