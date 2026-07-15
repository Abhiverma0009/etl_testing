"use client";

/**
 * Inline help for the two free-form JSON fields in the suite editor. Kept next
 * to the inputs (a plain <details> rather than a dialog, so it can't fight the
 * editor Sheet for focus/stacking) and documents only keys the engine actually
 * reads — see etl_test/validators/*.py.
 */

function Key({ name, type, children }: { name: string; type: string; children: React.ReactNode }) {
  return (
    <div className="border-b py-1.5 last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <code className="font-mono text-[11px] font-semibold text-foreground">{name}</code>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{type}</span>
      </div>
      <div className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">{children}</div>
    </div>
  );
}

function Details({ children }: { children: React.ReactNode }) {
  return (
    <details className="mt-1.5 rounded-md border bg-muted/30 px-2.5 py-1.5">
      <summary className="cursor-pointer select-none text-xs font-medium text-foreground">
        Accepted keys &amp; example
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

function Example({ code }: { code: string }) {
  return (
    <>
      <div className="mt-2.5 text-[11px] font-medium text-foreground">Example</div>
      <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 font-mono text-[10.5px] leading-relaxed">
        {code}
      </pre>
    </>
  );
}

export function SuiteOptionsHelp() {
  return (
    <>
      <p className="mb-1.5 text-xs text-muted-foreground">
        Settings applied to every check in this test case. Leave the default unless you need
        different tolerances.
      </p>
      <Details>
        <Key name="variance_threshold" type="number · default 0.0001">
          Max variance (0.0001 = 0.01%) before <b>Reconciliation</b> flags a difference.
        </Key>
        <Key name="numeric_tolerance" type="number">
          How close two numbers must be to count as matching — absorbs rounding
          (<b>Reconciliation</b>, <b>Transformation</b>).
        </Key>
        <Key name="schema_case_sensitive" type="true / false · default false">
          Compare column names case-sensitively (<b>Schema</b>).
        </Key>
        <Example
          code={`{
  "variance_threshold": 0.0001,
  "numeric_tolerance": 0.01,
  "schema_case_sensitive": false
}`}
        />
      </Details>
    </>
  );
}

export function TableOptionsHelp() {
  return (
    <>
      <p className="mb-1.5 text-xs text-muted-foreground">
        Which target tables this test case runs against — <code className="rounded bg-muted px-1">[]</code>{" "}
        means every table in the mapping. Also lets you override settings per table.
      </p>
      <Details>
        <div className="mb-2 rounded border bg-background p-2 text-[11.5px] text-muted-foreground">
          <div className="font-medium text-foreground">Two accepted shapes</div>
          <div className="mt-1">
            Scope only:{" "}
            <code className="rounded bg-muted px-1 font-mono text-[10.5px]">
              [&quot;HOLDINGS&quot;, &quot;POSITIONS&quot;]
            </code>
          </div>
          <div className="mt-0.5">
            Scope + settings:{" "}
            <code className="rounded bg-muted px-1 font-mono text-[10.5px]">
              [{"{"} &quot;name&quot;: &quot;HOLDINGS&quot;, &quot;options&quot;: {"{…}"} {"}"}]
            </code>
          </div>
        </div>

        <div className="mb-1 text-[11px] font-medium text-foreground">Keys inside &quot;options&quot;</div>
        <Key name="severity" type="P1 – P4 · default P1">
          Severity of this table&rsquo;s failures.
        </Key>
        <Key name="target_where / source_where" type="string filter">
          Restrict which rows are read, e.g. <code>QUARTER=&apos;2026Q1&apos;</code>.
        </Key>
        <Key name="source_options / target_options" type="object">
          Connector settings. For file sources:{" "}
          <code>{`{"path": "GC_*.xlsx", "sheet": ["Holdings"]}`}</code>.
        </Key>
        <Key name="group_by" type="column name">
          Adds per-group counts (<b>Row count</b>).
        </Key>
        <Key name="null_not_zero" type="list of columns">
          Columns where a null must not be loaded as 0 (<b>Null handling</b>).
        </Key>
        <Key name="lineage_columns" type="list of columns">
          Audit columns that must exist &amp; be populated. Default{" "}
          <code>[&quot;SOURCE_SYSTEM&quot;, &quot;LOAD_TIMESTAMP&quot;]</code> (<b>Lineage</b>).
        </Key>
        <Key name="completeness" type="object (or list)">
          <code>{`{"column": "STATUS", "expected_values": [...], "forbidden_values": [...]}`}</code>{" "}
          (<b>Completeness</b>).
        </Key>
        <Key name="incremental" type="object">
          <code>{`{"baseline": "<connection name>"}`}</code> — needs the table to have key_columns
          (<b>Incremental</b>).
        </Key>
        <Key name="historical" type="object">
          <code>{`{"period_column", "expected_periods", "baseline", "baseline_object", "current_period"}`}</code>{" "}
          (<b>Historical</b>).
        </Key>
        <Key name="cross_source" type="object">
          <code>{`{"second_source", "object", "key_columns", "compare_columns", "rename"}`}</code>{" "}
          (<b>Cross-source</b>).
        </Key>

        <Example
          code={`[
  {
    "name": "VALDB_TABLE_1",
    "options": {
      "source_options": {
        "path": "GC_*.xlsx",
        "sheet": ["Holdings", "Positions"]
      },
      "target_where": "QUARTER='2026Q1'",
      "severity": "P1"
    }
  }
]`}
        />
        <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
          <b>Note:</b> Incremental, Historical and Cross-source only run when their config is present
          here — a table without it reports <b>SKIPPED</b> for that category.
        </p>
      </Details>
    </>
  );
}
