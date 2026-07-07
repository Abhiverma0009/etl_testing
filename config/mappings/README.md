# Mapping workbooks

Place your Excel source-to-target mapping workbook(s) here (e.g.
`valdb_mapping.xlsx`) and point `suite.yaml`'s `mapping:` at it.

## Expected sheets

| Sheet | Required columns | Purpose |
|-------|------------------|---------|
| **Tables** | `target_table` (+ `source_object`, `target_db/schema`, `layer`, `load_type`, `key_columns`, `active`) | One row per target table |
| **Columns** | `target_table`, `target_column` (+ `source_column`, `source_datatype`, `target_datatype`, `nullable`, `transformation`, `default_value`, `compare`, `case_sensitive`, `numeric_tolerance`) | One row per target column |
| **BusinessRules** | `rule_id`, `target_table`, `rule_type` (+ `column`, `expected`, `allowed_values`, `filter`, `params`(JSON), `severity`, `use_case`, `description`) | One row per business rule |
| **ReferentialIntegrity** | `child_table`, `parent_table`, `child_columns`, `parent_columns` (+ `severity`, `description`) | One row per FK relationship |

- `key_columns`, `allowed_values`, `child_columns` etc. may list multiple values
  separated by `,` `;` or `|`.
- `params` is a JSON object for rule arguments that don't fit the convenience
  columns (e.g. `{"when": "COMPANY == 'X'"}`, `{"group_by": "COMPANY", "type_column": "LINE_TYPE", "expect_distinct": 2}`).
- Sheet/column name matching is case-insensitive and tolerant of spaces/underscores.

See `samples/demo_mapping.xlsx` (created by `python samples/build_demo.py`) for a
fully worked example. The parser validates structure and reports actionable
errors; reconcile this contract with the client's real mapping document when it
arrives.

## Business rule types

`value_equals`, `allowed_values`, `not_allowed`, `conditional` (alias
`flag_override`), `not_null`, `range`, `unique`, `must_exist`, `must_not_exist`,
`combine`, `split`, `valid_expr`. See the docstring at the top of
`etl_test/validators/business_rules.py` for each rule type's parameters.
