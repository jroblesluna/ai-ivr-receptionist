"""UseCase and Topic models with parent-child relationship."""
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

try:
    from src.models import Base
except ImportError:
    from models import Base


class UseCase(Base):
    __tablename__ = "use_cases"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    industry = Column(String)
    url = Column(String)
    forward_to = Column(String)
    voice_en = Column(String)
    voice_es = Column(String)
    slogan_en = Column(String)
    slogan_es = Column(String)
    is_demo = Column(Integer, default=0)
    demo_code = Column(String)
    ivr_type = Column(String, default="topics")
    system_prompt = Column(Text)
    system_prompt_es = Column(Text)
    knowledge_base = Column(Text)

    topics = relationship(
        "Topic", back_populates="use_case", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<UseCase(id={self.id!r}, name={self.name!r})>"


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    use_case_id = Column(
        String,
        ForeignKey("use_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    key = Column(String, nullable=False)
    digit = Column(String)
    meeting_type = Column(Integer, default=0)
    label_en = Column(String)
    label_es = Column(String)
    menu_text_en = Column(String)
    menu_text_es = Column(String)
    greeting_en = Column(String)
    greeting_es = Column(String)
    system_extra_en = Column(String)
    system_extra_es = Column(String)
    questions_en = Column(Text, default="[]")
    questions_es = Column(Text, default="[]")

    use_case = relationship("UseCase", back_populates="topics")

    __table_args__ = (
        UniqueConstraint("use_case_id", "key", name="uq_topic_use_case_key"),
    )

    def __repr__(self):
        return f"<Topic(id={self.id!r}, use_case_id={self.use_case_id!r}, key={self.key!r})>"
