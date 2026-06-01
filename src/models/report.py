"""Report model — call report index records."""
from sqlalchemy import Column, String

try:
    from src.models import Base
except ImportError:
    from models import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(String(16), primary_key=True)
    datetime = Column(String)
    caller_number = Column(String)
    caller_name = Column(String)
    topic = Column(String)
    language = Column(String)

    def __repr__(self):
        return f"<Report(id={self.id!r}, datetime={self.datetime!r})>"
