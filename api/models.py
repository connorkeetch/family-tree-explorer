"""ORM models. Multi-tenant from day one: every tree belongs to a user."""
import datetime as dt

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    pw_hash = Column(String, nullable=False)
    pw_salt = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    trees = relationship("Tree", back_populates="owner", cascade="all, delete-orphan")


class Tree(Base):
    __tablename__ = "trees"

    id = Column(String, primary_key=True)  # unguessable url-safe token
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    meta = Column(JSON, nullable=False)
    # The structured people list (the ancestors.json contract). JSON here, JSONB
    # under Postgres later. Living-person fields are gated at the API layer.
    people = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    owner = relationship("User", back_populates="trees")
