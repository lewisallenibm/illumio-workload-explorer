"""Isolated test database setup.

The test suite never reads or writes the developer's configured PostgreSQL
database.  It uses one in-memory SQLite engine created only after this module
sets DATABASE_URL during pytest startup.
"""

import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest

from app.database import engine
from app.models.base import Base


@pytest.fixture(autouse=True)
def isolated_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
