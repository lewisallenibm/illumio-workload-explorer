from app.database import engine

from app.models.base import Base

from app.models.workload import Workload
from app.models.workload_ip import WorkloadIP
from app.models.import_run import ImportRun
from app.models.workload_change import WorkloadChange

Base.metadata.create_all(
    bind=engine
)

print(
    "workload_changes table created."
)