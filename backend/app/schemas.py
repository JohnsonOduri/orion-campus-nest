from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    full_name: str
    semester: int = Field(ge=1, le=8)
    department: str
    batch: str
    section: str
    admission_year: int
    programme: str = "B.Tech"
    password: Optional[str] = None


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
    query: str = Field(min_length=1)
