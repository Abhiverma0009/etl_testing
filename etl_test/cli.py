"""etl-test command line interface.

Examples
--------
  etl-test test-connection snowflake_gold
  etl-test list-tests
  etl-test run --suite config/suite.yaml
  etl-test run --suite config/suite.yaml --tests reconciliation,business_rules --table DealFundValuedAsset
  etl-test reconciliation --mapping config/mappings/valdb.xlsx --source access_valdb --target snowflake_gold
  etl-test export-mapping config/mappings/valdb_mapping.xlsx
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from .config_loader import Connections, load_env, load_suite, load_yaml
from .core.runner import run_validation
from .exceptions import EtlTestError
from .logging_setup import configure_logging
from .mapping import load_mapping
from .mapping.models import MappingBook
from .validators import all_categories

DEFAULT_CONNECTIONS = "config/connections.yaml"
DEFAULT_OUTPUT = "output"


@click.group()
@click.option("--log-level", default="INFO", show_default=True)
@click.option("--env-file", default=None, help="Path to a .env file (optional).")
@click.pass_context
def cli(ctx: click.Context, log_level: str, env_file: str | None) -> None:
    """ETL migration data consistency & integrity test framework."""
    configure_logging(log_level)
    load_env(env_file)
    ctx.ensure_object(dict)


# --------------------------------------------------------------------------------
@cli.command("list-tests")
def list_tests() -> None:
    """List the available test categories."""
    click.echo("Available test categories:")
    for c in all_categories():
        click.echo(f"  - {c}")


@cli.command("test-connection")
@click.argument("name")
@click.option("--connections", "connections_path", default=DEFAULT_CONNECTIONS,
              show_default=True)
def test_connection(name: str, connections_path: str) -> None:
    """Open NAME and run a trivial probe query."""
    from .connectors.factory import make_connector
    conns = Connections.from_file(connections_path)
    conn = make_connector(conns.get(name))
    try:
        conn.test_connection()
        click.secho(f"OK: connection '{name}' ({conn.type_name}) is reachable.", fg="green")
    except Exception as exc:  # noqa: BLE001
        click.secho(f"FAILED: {exc}", fg="red")
        sys.exit(2)
    finally:
        conn.close()


@cli.command("export-mapping")
@click.argument("xlsx_path")
@click.option("--output", "out_path", default=None,
              help="Output .json path (default: alongside the input, same stem).")
def export_mapping(xlsx_path: str, out_path: str | None) -> None:
    """Parse a mapping workbook and dump it as JSON (for the Next.js importer).

    The JSON shape is consumed by `etl_test.mapping.json_loader`, so a suite can
    later point its `mapping:` at the `.json` file instead of the `.xlsx`.
    """
    book = load_mapping(xlsx_path)
    data = {
        "source_file": book.source_file,
        "tables": [
            {**{k: v for k, v in asdict(t).items() if k != "columns"},
             "columns": [asdict(c) for c in t.columns]}
            for t in book.tables.values()
        ],
        "business_rules": [asdict(r) for r in book.business_rules],
        "ref_integrity": [asdict(r) for r in book.ref_integrity],
        "warnings": book.warnings,
    }
    out = Path(out_path) if out_path else Path(xlsx_path).with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    click.echo(f"Exported: {out}")


@cli.command("import-suites")
@click.argument("xlsx_path")
@click.option("--suites-dir", default="config/suites", show_default=True)
@click.option("--scenarios-path", default="config/scenarios.yaml", show_default=True)
@click.option("--connections", "connections_path", default=DEFAULT_CONNECTIONS, show_default=True)
@click.option("--mappings-dir", default="config/mappings", show_default=True)
def import_suites_cmd(xlsx_path, suites_dir, scenarios_path, connections_path, mappings_dir) -> None:
    """Import test cases (suites) + scenarios from an Excel workbook.

    Writes one config/suites/<name>.yaml per test case and upserts scenarios
    into scenarios.yaml. Prints a single JSON summary line on stdout (consumed
    by the app's importer)."""
    from .suite_import import import_suites
    try:
        summary = import_suites(
            xlsx_path, suites_dir=suites_dir, scenarios_path=scenarios_path,
            connections_path=connections_path, mappings_dir=mappings_dir)
    except EtlTestError as exc:
        click.secho(f"Import error: {exc}", fg="red", err=True)
        sys.exit(2)
    click.echo(json.dumps(summary))


# --------------------------------------------------------------------------------
def _merge_suite_table_options(mapping: MappingBook, suite: dict[str, Any]) -> list[str] | None:
    """Apply per-table options from the suite onto the mapping; return table names."""
    entries = suite.get("tables") or suite.get("datasets") or []
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
            continue
        name = entry.get("name")
        if not name:
            continue
        names.append(name)
        tm = mapping.table(name)
        if tm is not None and entry.get("options"):
            tm.options.update(entry["options"])
    return names or None


def _load_for_suite(suite_path: str, connections_path: str | None
                    ) -> tuple[Connections, MappingBook, dict[str, Any], list[str] | None]:
    suite = load_suite(suite_path)
    conns_path = suite.get("connections") or connections_path or DEFAULT_CONNECTIONS
    connections = Connections.from_file(conns_path)
    mapping_path = suite.get("mapping")
    if mapping_path:
        mapping = load_mapping(mapping_path)
    elif suite.get("reports"):
        # A report-only suite (GVC/MD&A) needs no source→target mapping.
        mapping = MappingBook(source_file="(reports only)")
    else:
        raise EtlTestError(
            f"Suite {suite_path} must specify 'mapping:' (path to .xlsx/.json) "
            f"or 'reports:' (a list of report ids).")
    table_names = _merge_suite_table_options(mapping, suite)
    return connections, mapping, suite, table_names


def _inject_reports(suite: dict[str, Any], options: dict[str, Any],
                    categories: list[str]) -> tuple[dict[str, Any], list[str]]:
    """If the suite lists ``reports:``, load & flatten them into
    ``options['report_specs']`` and ensure the ``report`` category runs."""
    report_ids = suite.get("reports") or []
    if not report_ids:
        return options, categories
    from .reporting.reports import load_reports
    reports_dir = suite.get("reports_dir", "config/reports")
    specs = load_reports(list(report_ids), reports_dir)
    options = dict(options)
    options["report_specs"] = list(options.get("report_specs") or []) + specs
    if "report" not in categories and "gvc_report" not in categories:
        categories = [*categories, "report"]
    return options, categories


def _execute(connections, mapping, *, categories, target, source, table_names,
             options, output_dir, suite_name, expected: str = "pass") -> int:
    run, json_path = run_validation(
        connections=connections, mapping=mapping, categories=categories,
        target_name=target, source_name=source, table_names=table_names,
        options=options, output_dir=Path(output_dir), suite_name=suite_name,
        expected=expected,
    )
    counts = run.counts()
    color = "green" if run.passed else "red"
    neg = " (negative test)" if run.is_negative else ""
    click.secho(
        f"\n{'PASS' if run.passed else 'FAIL'}{neg} — "
        f"{counts['PASS']} pass / {counts['WARN']} warn / {counts['FAIL']} fail / "
        f"{counts['ERROR']} error / {counts['SKIPPED']} skipped",
        fg=color, bold=True)
    click.echo(f"Results:   {json_path}")
    return run.exit_code()


# --------------------------------------------------------------------------------
@cli.command("run")
@click.option("--suite", "suite_path", required=True, help="Path to suite.yaml")
@click.option("--connections", "connections_path", default=None,
              help="Override connections.yaml (else taken from suite or default).")
@click.option("--tests", default=None,
              help="Comma-separated category filter (default: all in suite).")
@click.option("--table", "tables", multiple=True,
              help="Limit to specific target table(s); repeatable.")
@click.option("--output", "output_dir", default=DEFAULT_OUTPUT, show_default=True)
def run_cmd(suite_path, connections_path, tests, tables, output_dir) -> None:
    """Run a suite of tests defined in a YAML file."""
    try:
        connections, mapping, suite, table_names = _load_for_suite(suite_path, connections_path)
    except EtlTestError as exc:
        click.secho(f"Config error: {exc}", fg="red"); sys.exit(2)

    categories = _resolve_categories(tests, suite)
    if tables:
        table_names = list(tables)

    options = suite.get("options", {})
    options, categories = _inject_reports(suite, options, categories)
    target = suite.get("target")
    source = suite.get("source")
    if not target:
        click.secho("Suite must define 'target:' (a connection name).", fg="red")
        sys.exit(2)

    code = _execute(connections, mapping, categories=categories, target=target,
                    source=source, table_names=table_names, options=options,
                    output_dir=output_dir, suite_name=Path(suite_path).name,
                    expected=suite.get("expected", "pass"))
    sys.exit(code)


def _resolve_categories(tests: str | None, suite: dict[str, Any]) -> list[str]:
    available = all_categories()
    if tests:
        requested = [t.strip() for t in tests.split(",") if t.strip()]
    elif suite.get("tests"):
        requested = list(suite["tests"])
    else:
        requested = available
    invalid = [t for t in requested if t not in available]
    if invalid:
        raise click.ClickException(
            f"Unknown test categor(ies): {invalid}. Available: {available}")
    return requested


# --------------------------------------------------------------------------------
def _make_category_command(category: str):
    @click.command(name=category, help=f"Run the '{category}' validator.")
    @click.option("--suite", "suite_path", default=None,
                  help="Suite to source connections/mapping/tables from.")
    @click.option("--mapping", "mapping_path", default=None,
                  help="Mapping .xlsx (when not using --suite).")
    @click.option("--connections", "connections_path", default=DEFAULT_CONNECTIONS,
                  show_default=True)
    @click.option("--source", default=None, help="Source connection name.")
    @click.option("--target", default=None, help="Target connection name.")
    @click.option("--table", "tables", multiple=True, help="Target table(s); repeatable.")
    @click.option("--output", "output_dir", default=DEFAULT_OUTPUT, show_default=True)
    def _cmd(suite_path, mapping_path, connections_path, source, target, tables, output_dir):
        if suite_path:
            connections, mapping, suite, table_names = _load_for_suite(
                suite_path, connections_path)
            target = target or suite.get("target")
            source = source or suite.get("source")
            options = suite.get("options", {})
            if category in ("report", "gvc_report"):
                options, _ = _inject_reports(suite, options, [category])
            suite_name = Path(suite_path).name
        else:
            if not mapping_path or not target:
                raise click.ClickException(
                    "Without --suite you must provide --mapping and --target.")
            connections = Connections.from_file(connections_path)
            mapping = load_mapping(mapping_path)
            options = {}
            table_names = None
            suite_name = None
        if tables:
            table_names = list(tables)
        if not target:
            raise click.ClickException("A --target connection is required.")
        code = _execute(connections, mapping, categories=[category], target=target,
                        source=source, table_names=table_names, options=options,
                        output_dir=output_dir, suite_name=suite_name)
        sys.exit(code)
    return _cmd


for _cat in all_categories():
    cli.add_command(_make_category_command(_cat))


if __name__ == "__main__":
    cli()
