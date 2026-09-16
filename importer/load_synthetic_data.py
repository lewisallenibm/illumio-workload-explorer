import pandas as pd

from app.database import SessionLocal

from app.models.import_run import ImportRun
from app.models.workload import Workload
from app.models.workload_ip import WorkloadIP


def main():

    session = SessionLocal()

    df = pd.read_csv(
        "sample_data/synthetic_workloads.csv"
    )

    import_run = ImportRun(
        filename="synthetic_workloads.csv",
        row_count=len(df),
        status="SUCCESS"
    )

    session.add(import_run)
    session.commit()

    for _, row in df.iterrows():

        workload = Workload(
            import_run_id=import_run.id,
            hostname=row["hostname"],
            app=row["app"],
            env=row["env"],
            loc=row["loc"],
            role=row["role"],
            enforcement=row["enforcement"],
            online=bool(row["online"]),
            agent_status=row["agent_status"],
            agent_health=row["agent_health"]
        )

        session.add(workload)
        session.flush()

        workload_ip = WorkloadIP(
            workload_id=workload.id,
            interface_name="eth0",
            ip_address=row["ip_address"]
        )

        session.add(workload_ip)

    session.commit()

    print(
        f"Imported {len(df)} workloads successfully."
    )

    session.close()


if __name__ == "__main__":
    main()