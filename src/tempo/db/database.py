# db/database.py
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(settings.DB_URL)


def create_db_and_tables():
    """
    Create the tables registered with SQLModel.metadata (i.e. classes with table=True)
    More info: https://sqlmodel.tiangolo.com/tutorial/create-db-and-table/#sqlmodel-metadata
    """
    SQLModel.metadata.create_all(engine)


# Session getter (can be kept here or moved to main.py)
def get_session():
    with Session(engine) as session:
        yield session
