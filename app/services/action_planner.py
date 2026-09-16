import re


class ActionPlanner:

    @staticmethod
    def extract_hostname(command):

        tokens = command.upper().split()

        for token in tokens:

            if (
                token.isdigit()
                or token == "WORKLOAD"
            ):
                continue

            if any(
                c.isdigit()
                for c in token
            ):
                return token.strip(",.")

        return None

    @staticmethod
    def extract_workload_id(command):

        match = re.search(
            r"workload\s+(\d+)",
            command.lower()
        )

        if match:

            return int(
                match.group(1)
            )

        return None

    @staticmethod
    def build_plan(command):

        text = command.lower()

        workload_id = (
            ActionPlanner.extract_workload_id(
                command
            )
        )

        hostname = (
            ActionPlanner.extract_hostname(
                command
            )
        )

        if (
            "revert" in text
            or "undo" in text
            or "rollback" in text
        ):

            return {
                "action": "revert_last_change",
                "workload_id": workload_id,
                "hostname": hostname,
            }

        if (
            "rename" in text
            and " to " in text
        ):

            new_name = (
                command.split(
                    " to ",
                    1
                )[1]
                .strip()
                .upper()
            )

            return {
                "action": "rename_workload",
                "workload_id": workload_id,
                "hostname": hostname,
                "new_name": new_name,
            }

        if (
            "delete" in text
            or "remove" in text
        ):

            return {
                "action": "delete_workload",
                "workload_id": workload_id,
                "hostname": hostname,
            }

        if (
            "resume" in text
            or "enable" in text
            or "restart" in text
        ):

            return {
                "action": "resume_workload",
                "workload_id": workload_id,
                "hostname": hostname,
            }

        if (
            "suspend" in text
            or "pause" in text
        ):

            return {
                "action": "suspend_workload",
                "workload_id": workload_id,
                "hostname": hostname,
            }

        if (
            "active" in text
            or "activate" in text
        ):
            status = "active"

        elif (
            "stopped" in text
            or "stop" in text
        ):
            status = "stopped"

        elif (
            "suspended" in text
            or "suspend" in text
        ):
            status = "suspended"

        else:
            status = None

        return {
            "action": "update_workload_status",
            "workload_id": workload_id,
            "hostname": hostname,
            "new_status": status,
        }