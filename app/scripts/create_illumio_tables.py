from app.database import engine
from app.models.base import Base

import app.models.illumio.illumio_workload
import app.models.illumio.illumio_interface
import app.models.illumio.illumio_label
import app.models.illumio.illumio_workload_label
import app.models.illumio.sync_run


Base.metadata.create_all(
    bind=engine
)

print(
    "Illumio tables created."
)