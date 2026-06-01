"""User, Role, and UserUseCase models."""
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

try:
    from src.models import Base
except ImportError:
    from models import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    def __repr__(self):
        return f"<Role(id={self.id!r}, name={self.name!r})>"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String)
    password_hash = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    email_verified = Column(Integer, default=0)
    phone_verified = Column(Integer, default=0)
    is_active = Column(Integer, default=0)
    email_token = Column(String)
    created_at = Column(String, server_default=func.now())

    role = relationship("Role")

    def __repr__(self):
        return f"<User(id={self.id!r}, email={self.email!r})>"


class UserUseCase(Base):
    __tablename__ = "user_use_cases"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    use_case_id = Column(
        String,
        ForeignKey("use_cases.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def __repr__(self):
        return f"<UserUseCase(user_id={self.user_id!r}, use_case_id={self.use_case_id!r})>"
