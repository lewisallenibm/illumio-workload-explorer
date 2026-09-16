NORMALIZATION_MAP = {

    "dupe": "duplicate",
    "dupes": "duplicate",

    "host": "hostname",
    "hosts": "hostname",

    "srv": "server",
    "svr": "server",

    "wrkld": "workload",
    "wrklds": "workloads",

    "env": "environment",

    "prod": "production",
    "dev": "development",

    "stpd": "stopped",
}


class NormalizationService:

    @staticmethod
    def normalize(text):

        words = text.lower().split()

        normalized = []

        for word in words:

            normalized.append(
                NORMALIZATION_MAP.get(
                    word,
                    word
                )
            )

        return " ".join(
            normalized
        )
