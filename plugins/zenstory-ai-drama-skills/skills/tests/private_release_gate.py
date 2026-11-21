"""Load maintainer-local release terms without storing them in the repository."""

from __future__ import annotations

import os
from pathlib import Path


REQUIRE_ENV = "DRAMA_REQUIRE_PRIVATE_RELEASE_GATE"
TERMS_FILE_ENV = "DRAMA_PRIVATE_TERMS_FILE"


def load_private_terms(default_path: Path | None = None) -> frozenset[str]:
    """Return exact local terms; fail closed when protected-release mode is set."""

    configured = os.environ.get(TERMS_FILE_ENV)
    required = os.environ.get(REQUIRE_ENV) == "1"
    if required and not configured:
        raise RuntimeError(f"{REQUIRE_ENV}=1 requires an explicit {TERMS_FILE_ENV}")
    path = Path(configured).expanduser() if configured else default_path
    if path is None or not path.is_file():
        if required:
            raise RuntimeError(
                f"{REQUIRE_ENV}=1 requires a readable {TERMS_FILE_ENV}"
            )
        return frozenset()
    terms = frozenset(
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )
    if required and not terms:
        raise RuntimeError(f"protected-release terms file is empty: {path}")
    return terms
