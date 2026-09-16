from abc import ABC
from abc import abstractmethod


class IllumioClient(ABC):

    @abstractmethod
    def get_workloads(self):
        pass

    @abstractmethod
    def get_labels(self):
        pass