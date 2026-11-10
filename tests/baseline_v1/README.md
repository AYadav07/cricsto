# v1 baseline results

Saved 2026-11-10 from the v1 database (Cricsheet CSV "Ashwin" format: `ipl`, `t20s`, `odis`, all **men's** only), just before v1 was removed.

Step 2 of the v2 plan compares the same queries on the v2 (JSON) database against these files. Expect differences only where v2 fixes something (e.g. retired hurt no longer counted as out, `city` now uses the venue's latest spelling, and v2 `t20s` / `odis` include women's matches unless filtered on `gender = 'male'`).

`vs_bowler_type_ipl_2022.csv` is empty because `data/reference/bowler_types.csv` had no rows.
