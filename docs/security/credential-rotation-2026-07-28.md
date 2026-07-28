# Database credential exposure and rotation record

## Scope

A plaintext SATT database credential was present in `CLAUDE.md` and
`reference/SV_COMMON_AUDIT_IMPLEMENTATION.md`. History review found the same
credential in three commits, from `b1dbdb33c224109757e4eb56fb8fd5077ab6bca7`
through `e1eef1f4be9d050dc43e6794a48dbb83e5aff659`.

The credential is identified only by SHA-256 fingerprint prefix
`ab908dfd31fd`. Its value is intentionally omitted.

## Remediation

On 2026-07-28, an explicitly authorized GitHub Actions maintenance job:

1. Confirmed by one-way comparison that the tracked credential matched the
   active SATT database credential.
2. Generated a replacement inside the production host process.
3. Changed only the SATT database role and SATT environment file.
4. Restarted SATT and verified service health and replacement authentication.
5. Verified that the exposed credential no longer authenticated.
6. Kept both credential values out of workflow output.

Run `30394058088` completed successfully against commit
`117fdf9f99744b3ca583432c55ee7d9f9cdc333a`. The ordinary deployment job was
skipped.

## History decision

Published Git history is not rewritten. Rewriting all affected refs would
disrupt existing clones and does not invalidate credentials held in forks,
caches, or external copies. Rotation is the effective security control; the
current tracked files are sanitized, the old value is invalid, and this record
preserves non-secret audit evidence.

If repository policy later requires history rewriting, treat it as a separately
approved coordinated operation. Rotation remains mandatory regardless of any
history rewrite.
