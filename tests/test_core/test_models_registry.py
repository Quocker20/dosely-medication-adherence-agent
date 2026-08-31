"""Guards against the exact failure class that broke the nightly
adherence-review job (docs/adherence-review-fix-plan.md Defect 1/5): a Celery
task module that runs fine when imported alongside the rest of the app (as
every other test in this suite does, via conftest.py's `from src.main import
app`) but crashes with NoReferencedTableError the first time it actually
writes to the database, because a ForeignKey target declared in a model
module nobody imported is unresolved.

configure_mappers() alone does NOT reproduce this -- verified empirically:
a bare `import src.modules.adherence.models; configure_mappers()`, with
admin.models (which declares doctor_profiles, the target of
Alert.assigned_doctor_id) never imported, still returns cleanly.
ForeignKey.column is resolved lazily against MetaData, and configure_mappers()
does not force that resolution for plain Column-level foreign keys. What
production actually hit was SQLAlchemy resolving every table's
ForeignKeyConstraint during unit-of-work dependency sorting on flush --
`Base.metadata.sorted_tables` triggers the identical resolution path (and
raises the identical NoReferencedTableError) without needing a live database,
so that is what this test forces instead.

Both tests below intentionally avoid importing `src.main` or anything under
`src/modules` at module scope, other than `src.core.models_registry` itself --
doing so would silently populate the registry these tests exist to check.
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _model_module_names() -> set[str]:
    """Every src/modules/<slice>/models.py, as a dotted module path."""
    return {
        f"src.modules.{p.parent.name}.models"
        for p in (REPO_ROOT / "src" / "modules").glob("*/models.py")
    }


def _imported_module_names(registry_path: Path) -> set[str]:
    """Every `from <package> import <submodule>` target in
    models_registry.py, as a full dotted path -- `from src.modules.adherence
    import models` counts as `src.modules.adherence.models`, matching what
    `_model_module_names` produces."""
    tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def _task_module_names() -> list[str]:
    """Every src/modules/<slice>/tasks.py, as a dotted module path."""
    return sorted(
        f"src.modules.{p.parent.name}.tasks"
        for p in (REPO_ROOT / "src" / "modules").glob("*/tasks.py")
    )


def test_registry_completeness():
    """Every module that declares an ORM model must be imported by
    src/core/models_registry.py. A model module added without updating the
    registry is exactly how Defect 1 happened -- this test exists so the
    next one is caught at commit time instead of on a production worker."""
    registry_path = REPO_ROOT / "src" / "core" / "models_registry.py"
    declared = _model_module_names()
    imported = _imported_module_names(registry_path)
    missing = declared - imported
    assert not missing, (
        f"src/core/models_registry.py does not import: {sorted(missing)}. "
        "Add them, or configure_mappers() will fail in any process that "
        "imports the registry but not these modules directly."
    )


@pytest.mark.parametrize("module_name", _task_module_names())
def test_task_module_resolves_all_foreign_keys_in_isolation(module_name):
    """Import exactly one tasks.py module in a clean subprocess -- nothing
    else -- then force resolution of every ForeignKeyConstraint the same way
    a real flush does (see module docstring for why configure_mappers()
    alone is not enough). This is what a Celery worker process actually
    does; a passing test suite that only ever imports tasks.py alongside the
    full app (as every other test here does via conftest.py) would never
    have caught Defect 1."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import {module_name}; "
            "from src.core.database import Base; "
            "Base.metadata.sorted_tables",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{module_name} left at least one ForeignKey unresolvable in "
        f"isolation -- this is what crashed the nightly adherence-review "
        f"job in production:\n{result.stderr}"
    )
