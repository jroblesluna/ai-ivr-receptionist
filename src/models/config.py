"""Config model — key/value store for application configuration."""
from sqlalchemy import Column, String, Text

try:
    from src.models import Base
except ImportError:
    from models import Base


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Config(key={self.key!r})>"
