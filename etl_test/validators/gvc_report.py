"""Back-compat shim. The GVC report validator was generalised into
:mod:`etl_test.validators.report` (legacy vs new, any report). This module keeps
the old import path (``from .gvc_report import GvcReportValidator``) working.
"""

from __future__ import annotations

from .report import GvcReportValidator, ReportValidator

__all__ = ["GvcReportValidator", "ReportValidator"]
