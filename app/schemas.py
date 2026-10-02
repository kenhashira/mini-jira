"""Request/response models and the status workflow rules."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["todo", "in_progress", "in_review", "done"]
Priority = Literal["low", "medium", "high"]

# Jira-style workflow: an issue can only move along these transitions.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "todo": {"in_progress"},
    "in_progress": {"todo", "in_review"},
    "in_review": {"in_progress", "done"},
    "done": {"in_progress"},  # reopen
}


class ProjectCreate(BaseModel):
    key: str = Field(pattern=r"^[A-Z]{2,10}$")
    name: str = Field(min_length=1, max_length=100)


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    priority: Priority = "medium"
    assignee: Optional[str] = None


class IssueUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[Priority] = None
    assignee: Optional[str] = None


class Transition(BaseModel):
    status: Status


class CommentCreate(BaseModel):
    author: str = Field(min_length=1)
    body: str = Field(min_length=1)
