from app.database import engine
from app.models.base import Base

import app.models.import_run
import app.models.workload
import app.models.workload_ip


def main():
    Base.metadata.create_all(engine)

    print("Schema created successfully.")


if __name__ == "__main__":
    main()