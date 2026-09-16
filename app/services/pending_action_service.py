class PendingActionService:

    _pending_action = None

    @classmethod
    def set_action(
        cls,
        plan
    ):
        cls._pending_action = plan

    @classmethod
    def get_action(
        cls
    ):
        return cls._pending_action

    @classmethod
    def clear_action(
        cls
    ):
        cls._pending_action = None