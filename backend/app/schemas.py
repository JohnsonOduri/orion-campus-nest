from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SetSessionRequest(BaseModel):
    access_token: str
    refresh_token: str


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    semester: int = Field(ge=1, le=8)
    department: str = Field(min_length=2, max_length=120)
    batch: Optional[str] = Field(default=None, max_length=20)  # same as section; kept for old clients
    section: str = Field(min_length=1, max_length=20)
    admission_year: int
    programme: str = "B.Tech"
    roll_number: Optional[str] = Field(default=None, max_length=20)


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

class TargetClass(BaseModel):
    """The class an ADMIN is acting for (ignored for a CR, whose class
    always comes from their profile)."""
    semester: int = Field(ge=1, le=8)
    department: Optional[str] = Field(default=None, max_length=120)
    section: Optional[str] = Field(default=None, max_length=20)
    programme: str = "B.Tech"


class TimetableDraftRequest(BaseModel):
    entries: list[dict] = Field(default_factory=list, max_length=250)
    target: Optional[TargetClass] = None


class TimetableSubmitRequest(BaseModel):
    entries: list[dict] = Field(min_length=1, max_length=250)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    upload_path: Optional[str] = Field(default=None, max_length=300)
    target: Optional[TargetClass] = None


class ExamDraftRequest(BaseModel):
    entries: list[dict] = Field(default_factory=list, max_length=320)
    exam_type: str = "end_sem"
    target: Optional[TargetClass] = None


class ExamSubmitRequest(ExamDraftRequest):
    note: Optional[str] = Field(default=None, max_length=1000)
    upload_path: Optional[str] = Field(default=None, max_length=300)


class ClassChangePreviewRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    changes: Optional[list[dict]] = Field(default=None, max_length=20)
    target: Optional[TargetClass] = None


class RoleRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    role: str


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
    # one-off class changes this notice announces (CLASS_UPDATE)
    changes: Optional[list[dict]] = Field(default=None, max_length=20)
    target: Optional[TargetClass] = None
    everyone: bool = False  # admin only: campus-wide


class ArchiveRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)
