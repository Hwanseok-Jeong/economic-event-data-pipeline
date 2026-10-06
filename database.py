"""Backend connection boundary; MySQL credentials come from DATABASE_URL."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class MySQLConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        return self.connection.exec_driver_sql(statement.replace('?', '%s'), parameters)

    def executemany(self, statement, records):
        return self.connection.exec_driver_sql(statement.replace('?', '%s'), records)


@contextmanager
def connect(db, initialize=False):
    root = Path(__file__).resolve().parent
    if db == 'mysql':
        from sqlalchemy import create_engine
        url = os.environ.get('DATABASE_URL', '')
        if not url.startswith('mysql+pymysql://'):
            raise ValueError('Set DATABASE_URL to a mysql+pymysql connection URL')
        engine = create_engine(url, pool_pre_ping=True)
        try:
            if initialize:
                # MySQL DDL implicitly commits; keep it outside the data transaction.
                with engine.begin() as connection:
                    for statement in (root / 'sql/schema_mysql.sql').read_text().split(';'):
                        if statement.strip():
                            connection.exec_driver_sql(statement)
            with engine.begin() as connection:
                yield MySQLConnection(connection)
        finally:
            engine.dispose()
    else:
        path = Path(db)
        if initialize:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.is_file():
            raise FileNotFoundError(f'Database does not exist: {db}')
        connection = sqlite3.connect(db)
        try:
            if initialize:
                connection.executescript((root / 'sql/schema.sql').read_text())
            with connection:
                yield connection
        finally:
            connection.close()
