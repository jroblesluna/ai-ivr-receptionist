"""CallerProfile model — per-caller memory for demo use cases."""
from sqlalchemy import Column, ForeignKey, String, Text

try:
    from src.models import Base
except ImportError:
    from models import Base


class CallerProfile(Base):
    __tablename__ = "caller_profiles"

    phone = Column(String, primary_key=True)
    use_case_id = Column(
        String,
        ForeignKey("use_cases.id"),
        primary_key=True,
    )
    profile_json = Column(Text, default="{}")
    updated_at = Column(String)

    def __repr__(self):
        return f"<CallerProfile(phone={self.phone!r}, use_case_id={self.use_case_id!r})>"
