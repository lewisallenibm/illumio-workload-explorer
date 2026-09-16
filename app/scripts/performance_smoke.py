"""Read-only timing check for the paged PostgreSQL browser query paths."""

import argparse
from dataclasses import dataclass
from time import perf_counter

from app.repositories.cmdb_repository import CmdbRepository, ReconciliationRepository
from app.repositories.illumio_workload_repository import IllumioWorkloadRepository


@dataclass(frozen=True)
class Measurement:
    name: str
    seconds: float
    rows: int | None = None


def _measure(name, callback) -> Measurement:
    started = perf_counter()
    value = callback()
    seconds = perf_counter() - started
    rows = len(value) if hasattr(value, "__len__") else value if isinstance(value, int) else None
    return Measurement(name, seconds, rows)


def collect_performance(page_size=500, workload_repository=IllumioWorkloadRepository,
                        cmdb_repository=CmdbRepository, reconciliation_repository=ReconciliationRepository):
    """Time representative page, filter, and page-jump queries without writes."""
    if page_size not in (250, 500, 1000):
        raise ValueError("page_size must be one of 250, 500, or 1000")

    measurements = []
    workload_total = _measure("Workloads: filtered count", workload_repository.count)
    measurements.append(workload_total)
    measurements.append(_measure(
        f"Workloads: first {page_size:,}-row page",
        lambda: workload_repository.search(limit=page_size, offset=0),
    ))
    measurements.append(_measure(
        f"Workloads: last {page_size:,}-row page jump",
        lambda: workload_repository.search(
            limit=page_size, offset=max((workload_total.rows or 0) - page_size, 0)
        ),
    ))

    cmdb_total = _measure("CMDB: filtered count", cmdb_repository.count)
    measurements.append(cmdb_total)
    measurements.append(_measure(
        f"CMDB: first {page_size:,}-row page",
        lambda: cmdb_repository.search(limit=page_size, offset=0),
    ))
    measurements.append(_measure(
        f"CMDB: last {page_size:,}-row page jump",
        lambda: cmdb_repository.search(
            limit=page_size, offset=max((cmdb_total.rows or 0) - page_size, 0)
        ),
    ))

    latest_run = reconciliation_repository.latest_completed_run()
    if latest_run is None:
        return measurements

    run_id = latest_run.id
    reconciliation_total = _measure(
        "Reconciliation: filtered count",
        lambda: reconciliation_repository.count(run_id=run_id),
    )
    measurements.append(reconciliation_total)
    measurements.append(_measure(
        f"Reconciliation: first {page_size:,}-row filtered page",
        lambda: reconciliation_repository.search(
            status="LABEL_MISMATCH", run_id=run_id, limit=page_size, offset=0,
        ),
    ))
    measurements.append(_measure(
        f"Reconciliation: last {page_size:,}-row page jump",
        lambda: reconciliation_repository.search(
            run_id=run_id,
            limit=page_size,
            offset=max((reconciliation_total.rows or 0) - page_size, 0),
        ),
    ))
    return measurements


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=500, choices=(250, 500, 1000))
    parser.add_argument(
        "--max-seconds", type=float,
        help="Optional failure threshold for each operation (useful in a controlled release check).",
    )
    args = parser.parse_args(argv)

    measurements = collect_performance(args.page_size)
    print("Read-only PostgreSQL performance smoke check")
    for measurement in measurements:
        suffix = f" | {measurement.rows:,} rows" if measurement.rows is not None else ""
        print(f"{measurement.name}: {measurement.seconds:.3f}s{suffix}")

    if args.max_seconds is not None:
        slow = [item for item in measurements if item.seconds > args.max_seconds]
        if slow:
            print(f"{len(slow)} operation(s) exceeded {args.max_seconds:.3f}s.")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
