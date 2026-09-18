from fairscape_models.sql.models import Base
from sqlalchemy.engine import Engine
from sqlalchemy import event, create_engine


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """ Set PRAGMA options for SQL
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


class SQLConfig():
    def __init__(
        self, 
        filepath: str | None = None, 
        connectionString: str | None = None,
        ):

        if filepath:
            self.connectionString = f"sqlite:///{filepath}"
        elif connectionString:
            self.connectionString = connectionString
        elif not filepath and not connectionString:
            raise Exception("SQLConfig needs a filepath for SQLite database or a connection string to a SQL Database")


    def engine(self,
        cacheSize: int = 800
    )->Engine:
        """ Create the SQL Alchemy Engine and Create the Base Metadata Tables
        """
        self.engine = create_engine(self.connectionString, query_cache_size=cacheSize) 
        Base.metadata.create_all(self.engine)
        return self.engine
