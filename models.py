"""
Data models and schemas for the magicpin Vera Engagement Assistant.
Strict typing ensures zero schema failures and exact API contract compliance.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class Identity(BaseModel):
    name: str
    city: str
    locality: str
    place_id: Optional[str] = None
    verified: bool = False
    languages: List[str] = Field(default_factory=lambda: ["en"])
    owner_first_name: Optional[str] = None
    established_year: Optional[int] = None


class PerformanceDelta(BaseModel):
    views_pct: Optional[float] = 0.0
    calls_pct: Optional[float] = 0.0
    ctr_pct: Optional[float] = 0.0


class PerformanceSnapshot(BaseModel):
    window_days: int = 30
    views: int = 0
    calls: int = 0
    directions: int = 0
    ctr: float = 0.0
    leads: Optional[int] = 0
    delta_7d: Optional[Dict[str, Any]] = None


class MerchantOffer(BaseModel):
    id: str
    title: str
    status: str
    started: Optional[str] = None
    ended: Optional[str] = None


class CustomerIdentity(BaseModel):
    name: str
    phone_redacted: Optional[str] = "<redacted>"
    language_pref: Optional[str] = "en"


class CustomerRelationship(BaseModel):
    first_visit: Optional[str] = None
    last_visit: Optional[str] = None
    visits_total: Optional[int] = 1
    services_received: List[str] = Field(default_factory=list)


# API Request / Response Models

class ContextPushRequest(BaseModel):
    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


class ContextPushResponse(BaseModel):
    accepted: bool
    ack_id: Optional[str] = None
    stored_at: Optional[str] = None
    reason: Optional[str] = None
    current_version: Optional[int] = None


class TickRequest(BaseModel):
    now: str
    available_triggers: List[str] = Field(default_factory=list)


class ActionItem(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: List[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: List[ActionItem] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


class ReplyResponse(BaseModel):
    action: Literal["send", "wait", "end"]
    body: Optional[str] = ""
    cta: Optional[str] = "none"
    wait_seconds: Optional[int] = None
    rationale: str


class HealthzResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int
    contexts_loaded: Dict[str, int]


class MetadataResponse(BaseModel):
    team_name: str
    team_members: List[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str
