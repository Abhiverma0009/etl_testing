# Suites — one per validation hop

Each file here is a **hop**: a `source:` → `target:` comparison. Run any with:

```powershell
etl-test run --suite config/suites/<name>.yaml
```

## The hop map

```
Global Private Equity (GPE)          Global Credit                 AlpInvest
   Snowflake VIEWS                     3 Excel files (tabs)          files
        │                                   │                          │
        │  gpe_view_to_staging              │  gc_files_to_valdb        │  alpinvest_files_to_valdb
        ▼                                   ▼                          ▼
   STAGING  ◄───────────── ValDB (Access, 2+ tables) ◄────────────────┘
        │                       │  valdb_to_staging
        │  staging_to_bronze    ▼
        ▼                    STAGING
     BRONZE ──► SILVER ──► GOLD      (staging_to_bronze, bronze_to_silver, silver_to_gold)

End-to-end (sign-off):  e2e_valdb_to_gold , e2e_gpe_to_gold
```

## Two comparison bases (you chose BOTH)
- **Layer-by-layer** (diagnosis): each layer vs the one directly upstream — pinpoints
  exactly where data breaks. Files: `*_to_staging`, `staging_to_bronze`,
  `bronze_to_silver`, `silver_to_gold`.
- **End-to-end** (sign-off): original file/view/Access vs final Gold. Files: `e2e_*`.

## Mappings
- `config/mappings/valdb_mapping.xlsx` — ValDB tables. Because the medallion keeps
  the **same table names across schemas**, this one mapping serves every Snowflake
  layer→layer hop for the ValDB flow (source_object = target_table = same name; the
  suite just swaps which schema connection is source vs target).
- `config/mappings/gpe_mapping.xlsx` — GPE view→gold flow.
- `config/mappings/globalcredit_mapping.xlsx` — Global Credit Excel tabs → the 2
  ValDB tables (tab→table mapping TBD from your sample files).

Generate blank, correctly-structured templates with:
```powershell
python samples/make_mapping_template.py
```

## Historical & incremental
Add a `*_prev` baseline connection (a snapshot/clone taken before the current load)
and enable per-table `historical:` / `incremental:` options in the relevant suite
(see `silver_to_gold.yaml` for a commented example).
