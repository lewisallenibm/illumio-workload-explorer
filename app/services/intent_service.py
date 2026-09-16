from difflib import SequenceMatcher

from app.services.intent_classifier import (
    IntentClassifier,
)

from app.services.intent_registry import (
    INTENTS,
)

from app.services.normalization_service import (
    NormalizationService,
)


class IntentService:

    AMBIGUITY_THRESHOLD = 10

    HIGH_CONFIDENCE_THRESHOLD = 85

    @staticmethod
    def detect_write_intent(text):

        if (
            "revert" in text
            or "undo" in text
            or "rollback" in text
        ):
            return "revert_last_change"

        if "rename" in text:
            return "rename_workload"

        if (
            "delete" in text
            or "remove" in text
        ):
            return "delete_workload"

        if (
            "suspend" in text
            or "pause" in text
        ):
            return "suspend_workload"

        if (
            "resume" in text
            or "restart" in text
            or "enable" in text
        ):
            return "resume_workload"

        return None

    @staticmethod
    def analyze(command):

        text = (
            NormalizationService.normalize(
                command
            )
        )

        request_type = (
            IntentClassifier.classify(
                text
            )
        )

        if request_type == "write":

            routed_intent = (
                IntentService
                .detect_write_intent(
                    text
                )
            )

            if routed_intent:

                return {
                    "intent": routed_intent,
                    "type": "write",
                    "confidence": 100.0,
                    "ambiguous": False,
                    "top_matches": [
                        {
                            "intent": routed_intent,
                            "score": 100.0,
                        }
                    ],
                }

        matches = []

        for intent, examples in INTENTS.items():

            is_write = (
                intent.startswith(
                    "update_"
                )
                or intent.endswith(
                    "_workload"
                )
                or intent.startswith(
                    "revert_"
                )
            )

            if (
                request_type == "read"
                and is_write
            ):
                continue

            if (
                request_type == "write"
                and not is_write
            ):
                continue

            best_score = 0

            for example in examples:

                score = SequenceMatcher(
                    None,
                    text,
                    example
                ).ratio()

                if score > best_score:

                    best_score = score

            matches.append(
                {
                    "intent": intent,
                    "score": round(
                        best_score * 100,
                        1
                    )
                }
            )

        matches.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        best = matches[0]

        second = (
            matches[1]
            if len(matches) > 1
            else {
                "intent": "none",
                "score": 0,
            }
        )

        difference = (
            best["score"]
            - second["score"]
        )

        ambiguous = False

        if (
            best["score"]
            < IntentService.HIGH_CONFIDENCE_THRESHOLD
        ):

            ambiguous = (
                difference
                < IntentService.AMBIGUITY_THRESHOLD
            )

        return {
            "intent": best["intent"],
            "type": request_type,
            "confidence": best["score"],
            "ambiguous": ambiguous,
            "top_matches": matches[:3],
        }