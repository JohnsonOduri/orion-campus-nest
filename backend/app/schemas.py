from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SetSessionRequest(BaseModel):
    access_token: str
    refresh_token: str


class RegisterRequest(BaseModel):
    full_name: str
    semester: int = Field(ge=1, le=8)
    department: str
    batch: str
    section: str
    admission_year: int
    programme: str = "B.Tech"


class CrAccessRequest(BaseModel):
    reason: Optional[str] = None


class AnnouncementSubmitRequest(BaseModel):
    title: str
    content: str
    category: Optional[str] = None
    department: Optional[str] = None
    batch: Optional[str] = None
    target_role: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class ReviewDecisionRequest(BaseModel):
    approve: bool
    rejection_reason: Optional[str] = None


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    conversation_id: Optional[str] = Field(default=None, max_length=64)


# ---- CR upload workflow (2026-09-28) --------------------------------------

class TimetableDraftRequest(BaseModel):
    entries: list[dict] = Field(default_factory=list, max_length=250)


class TimetableSubmitRequest(BaseModel):
    entries: list[dict] = Field(min_length=1, max_length=250)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    upload_path: Optional[str] = Field(default=None, max_length=300)


class AnnouncementPreviewRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    category: Optional[str] = None


class ClassAnnouncementRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    category: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    valid_until: Optional[str] = None
    upload_path: Optional[str] = Field(default=None, max_length=300)


class ArchiveRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)
