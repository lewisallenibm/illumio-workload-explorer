from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.action_planner import (
    ActionPlanner,
)

from app.services.action_validation_service import (
    ActionValidationService,
)

from app.services.intent_service import (
    IntentService,
)

from app.services.operations_service import (
    OperationsService,
)

from app.services.pending_action_service import (
    PendingActionService,
)

from app.services.workload_update_service import (
    WorkloadUpdateService,
)

from app.services.audit_service import (
    AuditService,
)

from app.services.revert_service import (
    RevertService,
)


class OperationsConsoleWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.command = QTextEdit()

        self.command.setStyleSheet(
            """
            QTextEdit {
                color: white;
            }
            """
        )

        self.analyze_button = QPushButton(
            "Analyze"
        )

        self.confirm_button = QPushButton(
            "Confirm Action"
        )

        self.output = QTextEdit()

        self.output.setReadOnly(True)

        self.analyze_button.clicked.connect(
            self.analyze
        )

        self.confirm_button.clicked.connect(
            self.confirm_action
        )

        layout = QVBoxLayout()

        layout.addWidget(
            QLabel("Enter Command")
        )

        layout.addWidget(
            self.command
        )

        layout.addWidget(
            self.analyze_button
        )

        layout.addWidget(
            self.confirm_button
        )

        layout.addWidget(
            QLabel("Results")
        )

        layout.addWidget(
            self.output
        )

        self.setLayout(
            layout
        )

    def confirm_action(self):

        action = (
            PendingActionService.get_action()
        )

        if action is None:

            self.output.setText(
                """
No Pending Action

Run Analyze first
to generate an action plan.
"""
            )

            return

        validation = (
            ActionValidationService.validate(
                action
            )
        )

        if not validation["valid"]:

            output = f"""
Cannot Execute

Reason:

{validation["message"]}
"""

            if "matches" in validation:

                output += "\n\nMatches Found\n\n"

                for workload in (
                    validation["matches"]
                ):

                    output += (
                        f"ID: {workload.id} "
                        f"Hostname: "
                        f"{workload.hostname}\n"
                    )

            self.output.setText(
                output
            )

            return

        workload = (
            validation["workload"]
        )

        #
        # EXECUTE STATUS UPDATE
        #

        if (
            action["action"]
            == "update_workload_status"
        ):

            try:

                previous_status = (
                    workload.agent_status
                )

                new_status = (
                    action["new_status"]
                )

                WorkloadUpdateService.update_workload(
                    workload.id,
                    {
                        "agent_status": (
                            new_status
                        )
                    }
                )

                PendingActionService.clear_action()

                output = f"""
Action Completed

Action:
Update Workload Status

Workload ID:
{workload.id}

Hostname:
{workload.hostname}

Field:
agent_status

Previous:
{previous_status}

Current:
{new_status}

Audit:
Recorded

Status:
SUCCESS
"""

                self.output.setText(
                    output
                )

                return

            except Exception as ex:

                self.output.setText(
                    f"""
Execution Failed

Reason:

{ex}
"""
                )

                return

        #
        # EXECUTE RENAME
        #

        if (
            action["action"]
            == "rename_workload"
        ):

            try:

                previous_hostname = (
                    workload.hostname
                )

                new_hostname = (
                    action["new_name"]
                )

                WorkloadUpdateService.update_workload(
                    workload.id,
                    {
                        "hostname": (
                            new_hostname
                        )
                    }
                )

                PendingActionService.clear_action()

                output = f"""
Action Completed

Action:
Rename Workload

Workload ID:
{workload.id}

Field:
hostname

Previous:
{previous_hostname}

Current:
{new_hostname}

Audit:
Recorded

Status:
SUCCESS
"""
                self.output.setText(
                    output
                )

                return

            except Exception as ex:

                self.output.setText(
                    f"""
Execution Failed

Reason:

{ex}
"""
                )

                return

        #
        # EXECUTE SUSPEND
        #

        if (
            action["action"]
            == "suspend_workload"
        ):

            try:

                previous_status = (
                    workload.agent_status
                )

                new_status = (
                    "suspended"
                )

                WorkloadUpdateService.update_workload(
                    workload.id,
                    {
                        "agent_status": (
                            new_status
                        )
                    }
                )

                PendingActionService.clear_action()

                output = f"""
Action Completed

Action:
Suspend Workload

Workload ID:
{workload.id}

Hostname:
{workload.hostname}

Field:
agent_status

Previous:
{previous_status}

Current:
{new_status}

Audit:
Recorded

Status:
SUCCESS
"""

                self.output.setText(
                    output
                )

                return

            except Exception as ex:

                self.output.setText(
                    f"""
Execution Failed

Reason:

{ex}
"""
                )

                return

        #
        # EXECUTE RESUME
        #

        if (
            action["action"]
            == "resume_workload"
        ):

            try:

                previous_status = (
                    workload.agent_status
                )

                new_status = (
                    "active"
                )

                WorkloadUpdateService.update_workload(
                    workload.id,
                    {
                        "agent_status": (
                            new_status
                        )
                    }
                )

                PendingActionService.clear_action()

                output = f"""
Action Completed

Action:
Resume Workload

Workload ID:
{workload.id}

Hostname:
{workload.hostname}

Field:
agent_status

Previous:
{previous_status}

Current:
{new_status}

Audit:
Recorded

Status:
SUCCESS
"""

                self.output.setText(
                    output
                )

                return

            except Exception as ex:

                self.output.setText(
                    f"""
Execution Failed

Reason:

{ex}
"""
                )

                return

        #
        # EXECUTE REVERT
        #

        if (
            action["action"]
            == "revert_last_change"
        ):

            try:

                change = (
                    AuditService
                    .get_latest_change_for_workload(
                        workload.id
                    )
                )

                if change is None:

                    self.output.setText(
                        """
No Audit History Found

Nothing to revert.
"""
                    )

                    return

                previous_value = (
                    change.new_value
                )

                reverted_value = (
                    change.old_value
                )

                RevertService.revert_change(
                    change.id
                )

                PendingActionService.clear_action()

                output = f"""
Action Completed

Action:
Revert Change

Workload ID:
{workload.id}

Change ID:
{change.id}

Field:
{change.field_name}

Previous:
{previous_value}

Current:
{reverted_value}

Audit:
Recorded

Status:
SUCCESS
"""

                self.output.setText(
                    output
                )

                return

            except Exception as ex:

                self.output.setText(
                    f"""
Execution Failed

Reason:

{ex}
"""
                )

                return

        #
        # SAFE MODE ACTIONS
        #

        output = f"""
Action Confirmation

Action:
{action["action"]}

Hostname:
{workload.hostname}

Workload ID:
{workload.id}

Status:
READY TO EXECUTE

Execution not yet enabled
for this action type.
"""

        self.output.setText(
            output
        )

    def analyze(self):

        command = (
            self.command.toPlainText()
        )

        result = (
            IntentService.analyze(
                command
            )
        )

        if result["ambiguous"]:

            output = """
Ambiguous Request

Multiple possible intents detected.

Top Matches

"""

            for match in result["top_matches"]:

                output += (
                    f'{match["intent"]}: '
                    f'{match["score"]}%\n'
                )

            output += (
                "\nPlease clarify your request.\n"
            )

            self.output.setText(
                output
            )

            return

        output = f"""
Detected Intent

Type:
{result["type"]}

Intent:
{result["intent"]}

Confidence:
{result["confidence"]}

=================================

Top Matches

"""

        for match in result["top_matches"]:

            output += (
                f'{match["intent"]}: '
                f'{match["score"]}%\n'
            )

        output += "\n=================================\n"

        if result["type"] == "write":

            plan = (
                ActionPlanner.build_plan(
                    command
                )
            )

            PendingActionService.set_action(
                plan
            )

            action = plan["action"]

            if action == "update_workload_status":

                output += f"""

Proposed Action

Action:
Update Workload Status

Hostname:
{plan["hostname"]}

Workload ID:
{plan["workload_id"]}

Requested Status:
{plan["new_status"]}

Status:
NOT EXECUTED
"""

            elif action == "rename_workload":

                output += f"""

Proposed Action

Action:
Rename Workload

Hostname:
{plan["hostname"]}

Workload ID:
{plan["workload_id"]}

New Name:
{plan["new_name"]}

Status:
NOT EXECUTED
"""

            elif action == "suspend_workload":

                output += f"""

Proposed Action

Action:
Suspend Workload

Hostname:
{plan["hostname"]}

Workload ID:
{plan["workload_id"]}

Status:
NOT EXECUTED
"""

            elif action == "resume_workload":

                output += f"""

Proposed Action

Action:
Resume Workload

Hostname:
{plan["hostname"]}

Workload ID:
{plan["workload_id"]}

Status:
NOT EXECUTED
"""
            elif action == "revert_last_change":

                latest_change = (
                    AuditService
                    .get_latest_change_for_workload(
                        plan["workload_id"]
                    )
                )

                if latest_change is None:

                    output += """

Proposed Action

No audit history found
for this workload.

Status:
NOT AVAILABLE
"""

                else:

                    plan["change_id"] = (
                        latest_change.id
                    )

                    PendingActionService.set_action(
                        plan
                    )

                    output += f"""

Proposed Action

Action:
Revert Change

Workload ID:
{plan["workload_id"]}

Change ID:
{latest_change.id}

Field:
{latest_change.field_name}

Current Value:
{latest_change.new_value}

Will Revert To:
{latest_change.old_value}

Status:
NOT EXECUTED
"""

            elif action == "delete_workload":

                output += f"""

Proposed Action

Action:
Delete Workload

Hostname:
{plan["hostname"]}

Workload ID:
{plan["workload_id"]}

Impact:
1 Workload

Status:
NOT EXECUTED
"""

            output += """

=================================

Click Confirm Action
to continue.
"""

            self.output.setText(
                output
            )

            return

        if result["intent"] == "show_duplicate_hostnames":

            duplicates = (
                OperationsService
                .get_duplicate_hostnames()
            )

            output += "\nDuplicate Hostnames\n\n"

            output += "\n".join(
                duplicates
            )

        elif result["intent"] == "show_duplicate_ips":

            ips = (
                OperationsService
                .get_duplicate_ips()
            )

            output += "\nDuplicate IPs\n\n"

            output += "\n".join(
                ips
            )

        elif result["intent"] == "show_unhealthy_workloads":

            workloads = (
                OperationsService
                .get_unhealthy_workloads()
            )

            output += "\nUnhealthy Workloads\n\n"

            for workload in workloads:

                output += (
                    f"{workload.hostname}\n"
                )

        elif result["intent"] == "show_stopped_agents":

            workloads = (
                OperationsService
                .get_stopped_agents()
            )

            output += "\nStopped Agents\n\n"

            for workload in workloads:

                output += (
                    f"{workload.hostname}\n"
                )

        elif result["intent"] == "show_suspended_agents":

            workloads = (
                OperationsService
                .get_suspended_agents()
            )

            output += "\nSuspended Agents\n\n"

            for workload in workloads:

                output += (
                    f"{workload.hostname}\n"
                )

        elif result["intent"] == "show_recent_changes":

            changes = (
                OperationsService
                .get_recent_changes()
            )

            output += "\nRecent Changes\n\n"

            for change in changes:

                output += (
                    f"{change.field_name}: "
                    f"{change.old_value} -> "
                    f"{change.new_value}\n"
                )

        elif result["intent"] == "show_dashboard_summary":

            summary = (
                OperationsService
                .get_dashboard_summary()
            )

            output += f"""

Dashboard Summary

Total Workloads:
{summary["total"]}

Healthy Agents:
{summary["healthy"]}

Stopped Agents:
{summary["stopped"]}

Suspended Agents:
{summary["suspended"]}
"""

        elif result["intent"] == "show_top_modified_workloads":

            rows = (
                OperationsService
                .get_top_modified_workloads()
            )

            output += "\nTop Modified Workloads\n\n"

            for hostname, count in rows:

                output += (
                    f"{hostname}: "
                    f"{count} changes\n"
                )

        self.output.setText(
            output
        )