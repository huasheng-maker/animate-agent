"""Repository paths with environment-variable overrides.

Paths are anchored to the installed source tree instead of the process working
directory. Deployments may relocate writable data and cache directories without
editing source files.
"""

from __future__ import annotations

import os
from pathlib import Path


def _configured_path(name: str, default: Path, *, base: Path | None = None) -> Path:
    configured = os.environ.get(name)
    if not configured:
        return default.resolve()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (base or PROJECT_ROOT) / path
    return path.resolve()


_SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = _configured_path(
    "ANIMATE_AGENT_PROJECT_ROOT",
    _SOURCE_PROJECT_ROOT,
    base=_SOURCE_PROJECT_ROOT,
)
CONFIG_PATH = _configured_path(
    "ANIMATE_AGENT_CONFIG_PATH",
    PROJECT_ROOT / "config" / "app.example.yaml",
)
ENV_FILE = _configured_path("ANIMATE_AGENT_ENV_FILE", PROJECT_ROOT / ".env")
DATA_DIR = _configured_path("ANIMATE_AGENT_DATA_DIR", PROJECT_ROOT / "data")
ASSETS_DIR = _configured_path("ANIMATE_AGENT_ASSETS_DIR", PROJECT_ROOT / "assets")
CACHE_DIR = _configured_path("ANIMATE_AGENT_CACHE_DIR", PROJECT_ROOT / ".cache")

DOCUMENTS_DIR = DATA_DIR / "documents"
GENERATED_DIR = DATA_DIR / "generated"
RUNS_DIR = DATA_DIR / "runs"
SAMPLES_DIR = DATA_DIR / "samples"
STORYBOARD_SAMPLES_DIR = SAMPLES_DIR / "storyboards"
GLYPH_DATA_DIR = ASSETS_DIR / "glyphs"
