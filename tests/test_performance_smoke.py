from types import SimpleNamespace

import pytest

from app.scripts.performance_smoke import collect_performance


class _Workloads:
    @staticmethod
    def count():
        return 1_250

    @staticmethod
    def search(limit, offset):
        return [object()] * min(limit, 1_250 - offset)


class _Cmdb:
    @staticmethod
    def count():
        return 1_800

    @staticmethod
    def search(limit, offset):
        return [object()] * min(limit, 1_800 - offset)


class _Reconciliation:
    @staticmethod
    def latest_completed_run():
        return SimpleNamespace(id=77)

    @staticmethod
    def count(run_id):
        assert run_id == 77
        return 2_200

    @staticmethod
    def search(**kwargs):
        assert kwargs["run_id"] == 77
        return [object()] * min(kwargs["limit"], 2_200 - kwargs["offset"])


def test_performance_smoke_covers_page_and_jump_queries_for_all_three_browsers():
    measurements = collect_performance(
        500, workload_repository=_Workloads, cmdb_repository=_Cmdb,
        reconciliation_repository=_Reconciliation,
    )

    assert len(measurements) == 9
    assert any("Workloads: last 500-row page jump" == item.name for item in measurements)
    assert any("CMDB: first 500-row page" == item.name for item in measurements)
    assert any("Reconciliation: first 500-row filtered page" == item.name for item in measurements)


def test_performance_smoke_rejects_unsupported_page_size():
    with pytest.raises(ValueError, match="page_size"):
        collect_performance(750, _Workloads, _Cmdb, _Reconciliation)
