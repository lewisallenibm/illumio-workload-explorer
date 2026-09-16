from app.config import settings


class IllumioService:

    @staticmethod
    def using_real_client():
        return settings.ILLUMIO_USE_REAL_CLIENT

    @staticmethod
    def get_client():

        if settings.ILLUMIO_USE_REAL_CLIENT:

            from app.services.illumio.real_illumio_client import (
                RealIllumioClient,
            )

            return RealIllumioClient()

        from app.services.illumio.mock_illumio_client import (
            MockIllumioClient,
        )

        return MockIllumioClient()

    @staticmethod
    def get_workloads():

        return IllumioService.get_client().get_workloads()

    @staticmethod
    def get_labels():

        return IllumioService.get_client().get_labels()
