"""Import every module that declares a SQLAlchemy ORM model, once.

A mapped class only registers itself on Base.metadata -- and becomes visible
to configure_mappers()'s ForeignKey resolution -- when its module is
imported. main.py never hits this: it imports every router, and through
them every model. Anything else that touches the ORM in isolation (Alembic's
env.py, a Celery worker importing a single tasks.py) does not get that for
free, and configure_mappers() is process-global and all-or-nothing -- one
missing module breaks every mapped class, not just the one whose FK target
is absent.

This was the root cause of the nightly adherence-review job crashing with
NoReferencedTableError on every run: alerts.assigned_doctor_id targets
doctor_profiles, declared in admin/models.py, which nothing in the Celery
task's own import chain pulled in. See
docs/adherence-review-fix-plan.md Defect 1 and Defect 5.

Import this module -- not the individual submodules -- from alembic/env.py
and from every src/modules/*/tasks.py that touches the ORM. Keep this list in
step with src/modules/*/models.py; dashboard has no models.py of its own, it
only reads other slices' tables.
"""

from src.modules.adherence import models as _adherence_models  # noqa: F401
from src.modules.adherence_review import models as _adherence_review_models  # noqa: F401
from src.modules.admin import models as _admin_models  # noqa: F401
from src.modules.agents import models as _agents_models  # noqa: F401
from src.modules.auth import models as _auth_models  # noqa: F401
from src.modules.patients import models as _patients_models  # noqa: F401
from src.modules.prescriptions import models as _prescriptions_models  # noqa: F401
