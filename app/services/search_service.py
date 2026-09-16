import re

from app.repositories.workload_repository import (
    WorkloadRepository
)


class SearchService:

    IP_PATTERN = re.compile(
        r"^\d+\.\d+\.\d+\.\d+$"
    )

    @staticmethod
    def search_hostname(
        hostname: str
    ):
        return (
            WorkloadRepository
            .find_by_hostname(
                hostname
            )
        )

    @staticmethod
    def search_ip(
        ip_address: str
    ):
        return (
            WorkloadRepository
            .find_by_ip(
                ip_address
            )
        )

    @classmethod
    def smart_search(
        cls,
        value: str
    ):

        value = value.strip()

        if cls.IP_PATTERN.match(
            value
        ):
            return cls.search_ip(
                value
            )

        return cls.search_hostname(
            value
        )