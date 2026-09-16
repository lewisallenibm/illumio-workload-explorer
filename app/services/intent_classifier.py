READ_KEYWORDS = {

    "show",
    "find",
    "list",
    "display",
    "view",
    "what",
    "which",
    "report",
    "summary",
}

WRITE_KEYWORDS = {

    "change",
    "set",
    "update",
    "modify",
    "activate",
    "deactivate",
    "stop",
    "suspend",
    "resume",
    "delete",
    "remove",
    "create",
    "rename",
    "edit",
}


class IntentClassifier:

    @staticmethod
    def classify(command):

        text = command.lower()

        read_score = 0
        write_score = 0

        for word in READ_KEYWORDS:

            if word in text:
                read_score += 1

        for word in WRITE_KEYWORDS:

            if word in text:
                write_score += 1

        if write_score > read_score:

            return "write"

        return "read"