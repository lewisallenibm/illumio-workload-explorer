from app.services.illumio.illumio_client import (
    IllumioClient
)

from app.services.illumio.mock_data_generator import (
    MockDataGenerator
)


class MockIllumioClient(IllumioClient):

    def get_workloads(self):

        return MockDataGenerator.generate(40_000)

    def get_labels(self):

        return [
            {
                "type": "Role",
                "value": "Application"
            },
            {
                "type": "Role",
                "value": "Database"
            },
            {
                "type": "Environment",
                "value": "Production"
            }
        ]