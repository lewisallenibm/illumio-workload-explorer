"""Run enabled, due automations once. Intended for a single scheduler worker."""

from app.services.automation_service import AutomationService


def main() -> int:
    runs = AutomationService().run_due()
    print(f"Due automations run: {len(runs)}")
    for run in runs:
        print(f"  run={run.id} automation={run.automation_id} status={run.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
