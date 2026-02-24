from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from main import run_cli


def run() -> None:
    """Entrypoint used by the installed `cronbot` console script."""
    run_cli()


if __name__ == "__main__":
    run()
