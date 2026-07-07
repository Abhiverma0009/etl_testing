"""ETL migration data consistency & integrity test framework.

Replaces ATOP Jumbo for the Carlyle Val DB -> Snowflake migration. Extracts data
from legacy + target sources, normalizes, compares, validates business rules, and
renders a self-contained HTML dashboard per run.
"""

__version__ = "0.1.0"
