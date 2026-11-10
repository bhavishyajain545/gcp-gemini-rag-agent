# Runbook: Database migration with row-count verification

**Scope:** Moving a relational database (PostgreSQL / Aurora / SQL Server) between servers, clusters or clouds.  
**Reference case:** a 186 GB PostgreSQL database with 411 schemas moved with zero data loss using this procedure.

## Principles
- Never trust a migration tool's "completed" message. Verify counts yourself.
- Freeze writes on the source during the final cutover; a migration without a write freeze cannot be verified.
- Keep the source untouched until the verification report is signed off.

## Procedure
1. **Inventory the source.** Record database size, number of schemas and tables, and the largest 20 tables by row count:
   `SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;`
2. **Take a consistent backup** (`pg_dump -Fc` or a storage snapshot). Note the exact timestamp.
3. **Restore to the target** with the same extensions and roles created first. Missing roles cause `pg_restore` warnings such as "role does not exist"; these are expected when roles were intentionally not migrated, but every other error must be investigated.
4. **Row-count verification.** Run the same count query on source and target and diff the results. A reusable approach:
   - Generate one `SELECT '<schema>.<table>', count(*) FROM <schema>.<table>` per table from `information_schema.tables`.
   - Save both outputs as CSV and compare with `diff` or a short Python script.
   - Any table whose counts differ is a **blocker**; find the cause (sequence/identity gaps, partial restore, writes after the backup) before cutover.
5. **Checksum sample rows** for the 10 most important tables (for example users, orders, documents): compare `md5(string_agg(row::text, ',' ORDER BY id))` over the same id range on both sides.
6. **Application cutover:** update the connection string in the secret store / Key Vault, restart the application, and run the smoke test (login, one read, one write).
7. **Verification report:** table count, total rows source vs target, mismatches (should be zero), checksum results, cutover time. Attach it to the migration ticket.

## Rollback
If verification fails after cutover, point the application back at the source (the source was left untouched) and reopen the migration ticket with the mismatch list.

## Common pitfalls
- Sequences not advanced on the target, causing duplicate-key errors on the first insert: run `setval` for every sequence from the source values.
- Large objects (`pg_largeobject`) skipped by schema-only dumps.
- Timezone differences making timestamp comparisons look wrong; compare in UTC.
