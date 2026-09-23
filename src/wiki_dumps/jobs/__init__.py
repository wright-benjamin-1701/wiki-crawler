"""Extraction jobs — auto-discovered from this package directory.

To add a new job, create ``src/wiki_dumps/jobs/<name>.py`` with a class that has:
- ``name: str`` class attribute (used as the CLI job name)
- ``__init__(self, db_url: str)`` constructor
- ``matches``, ``extract``, ``flush``, ``setup_schema`` methods (see ExtractJob Protocol)

No changes to this file or cli.py are required.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from wiki_dumps.extract.base import ExtractJob


def discover_job_classes() -> dict[str, type[ExtractJob]]:
    """Scan this package directory and return all job classes keyed by their .name."""
    jobs_dir = Path(__file__).parent
    result: dict[str, type[ExtractJob]] = {}
    for module_path in sorted(jobs_dir.glob("*.py")):
        if module_path.stem.startswith("_"):
            continue
        module = importlib.import_module(f"wiki_dumps.jobs.{module_path.stem}")
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            job_name = getattr(obj, "name", None)
            if (
                isinstance(obj, type)
                and isinstance(job_name, str)
                # only classes defined in this module, not imported ones
                and getattr(obj, "__module__", "") == module.__name__
            ):
                result[job_name] = cast("type[ExtractJob]", obj)
    return result
