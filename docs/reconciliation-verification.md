# Reconciliation Verification Pack

This private project document describes the testable contract for comparing
the active CMDB snapshot with the active Illumio snapshot. It is designed for
both operational review and technical audit.

## Contract

1. A hostname is normalized by trimming whitespace, ignoring case, and
   removing one trailing dot.
2. An exact normalized hostname match is accepted only when both sides have
   exactly one candidate.
3. A short hostname may match one FQDN with the same first hostname segment.
   Two different FQDNs never match each other through that fallback.
4. Duplicate CMDB identities or multiple Illumio candidates are always saved
   as `AMBIGUOUS_MATCH`; the application never chooses the first row.
5. For an accepted workload match, CMDB application/role/environment/location
   are compared to Illumio labels of the same canonical name.
6. Every review condition is saved with copied hostname/value evidence in the
   reconciliation result. A later CMDB or Illumio snapshot cannot overwrite
   that historical evidence.
7. Only `LABEL_MISMATCH` and `LABEL_MISSING` can be approved for the guarded
   PCE write-back workflow. Approval alone never changes PCE.

## Automated proof

Run the contract tests locally:

```bash
python -m pytest -q tests/test_reconciliation_runs.py
```

They prove exact matching, normalization, short-name/FQDN matching,
non-matching full FQDNs, duplicate safety, each label condition, non-approvable
review conditions, and immutable history after a new source snapshot.

## Evidence produced by a run

`reconciliation_runs` records which successful CMDB import and Illumio sync
were used and stores aggregate counts. `reconciliation_results` holds one
durable review row per issue: hostname, field, expected CMDB value, observed
Illumio value, status, approval state, and Illumio href.
