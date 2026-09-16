import csv


class ExportService:

    @staticmethod
    def export_workloads(
        workloads,
        file_path
    ):

        with open(
            file_path,
            "w",
            newline="",
            encoding="utf-8"
        ) as csv_file:

            writer = csv.writer(
                csv_file
            )

            writer.writerow([
                "hostname",
                "app",
                "environment",
                "role",
                "enforcement",
                "agent_status",
                "agent_health"
            ])

            for workload in workloads:

                writer.writerow([
                    workload.hostname,
                    workload.app,
                    workload.env,
                    workload.role,
                    workload.enforcement,
                    workload.agent_status,
                    workload.agent_health
                ])