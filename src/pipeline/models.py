"""Data models and schema definitions for the Job Pipeline Agent."""

from datetime import date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_serializer
from slugify import slugify


class StageEnum(str, Enum):
    RESEARCHING = "researching"
    APPLIED = "applied"
    SCREEN_SCHEDULED = "screen_scheduled"
    SCREEN_DONE = "screen_done"
    ONSITE_SCHEDULED = "onsite_scheduled"
    ONSITE_DONE = "onsite_done"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    STALE = "stale"


class SourceEnum(str, Enum):
    COLD = "cold"
    WARM_INTRO = "warm_intro"
    RECRUITER = "recruiter"
    REFERRAL = "referral"


class LocationTypeEnum(str, Enum):
    REMOTE = "remote"
    SF_HYBRID = "sf_hybrid"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class ContactRoleEnum(str, Enum):
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    REFERRER = "referrer"


class ContactChannelEnum(str, Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    SLACK = "slack"


class DirectionEnum(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Contact(BaseModel):
    name: str
    role: ContactRoleEnum
    channel: ContactChannelEnum
    handle: Optional[str] = None


class LastContact(BaseModel):
    direction: DirectionEnum
    date: date
    summary: str


class Application(BaseModel):
    company: str
    role: str
    url: Optional[str] = None
    applied_on: Optional[date] = None
    source: SourceEnum = SourceEnum.COLD
    referrer: Optional[str] = None
    stage: StageEnum = StageEnum.APPLIED
    stage_changed_on: date
    location_type: LocationTypeEnum = LocationTypeEnum.REMOTE
    comp_discussed: Optional[str] = None
    contacts: List[Contact] = Field(default_factory=list)
    last_contact: Optional[LastContact] = None
    next_action: Optional[str] = None
    nudge_count: int = 0
    notes: Optional[str] = None

    @property
    def slug(self) -> str:
        return f"{slugify(self.company)}-{slugify(self.role)}"

    @field_serializer("applied_on", "stage_changed_on", mode="plain")
    def serialize_date(self, d: Optional[date]) -> Optional[str]:
        return d.isoformat() if d else None


class VettingVerdictEnum(str, Enum):
    LIKELY_LEGITIMATE = "likely_legitimate"
    NEEDS_VERIFICATION = "needs_verification"
    LIKELY_FRAUDULENT = "likely_fraudulent"


class VettingInput(BaseModel):
    sender_email: Optional[str] = None
    reply_to_email: Optional[str] = None
    claimed_company: Optional[str] = None
    claimed_role: Optional[str] = None
    message_text: str


class VettingResult(BaseModel):
    verdict: VettingVerdictEnum
    signals_against: List[str] = Field(default_factory=list)
    signals_for: List[str] = Field(default_factory=list)
    recommended_action: List[str] = Field(default_factory=list)
    role_legitimate: Optional[bool] = None
    channel_safe: Optional[bool] = None
