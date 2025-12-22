from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


class MakeCallRequest(BaseModel):
    phone_number: str


class CountryCode(BaseModel):
    name: str
    code: str


class CallInfo(BaseModel):
    call_sid: str
    status: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    start_time: Optional[float] = None


class CallStatusResponse(BaseModel):
    active_calls: int
    models_ready: bool
    calls: Dict[str, Dict[str, Any]]


class StatusResponse(BaseModel):
    status: str
    message: str
    prompt_id: Optional[str] = Field(
        None,
        description="The UUID of the created/updated prompt (returned when creating new prompt)",
    )


class LogEntry(BaseModel):
    timestamp: str
    message: str


class NgrokUrlRequest(BaseModel):
    url: str


class CallRecord(BaseModel):
    call_sid: str
    status: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    direction: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration_human: Optional[str] = None


class CallStatusSummary(BaseModel):
    ongoing: List[CallRecord] = Field(default_factory=list)
    declined: List[CallRecord] = Field(default_factory=list)
    completed: List[CallRecord] = Field(default_factory=list)
    others: List[CallRecord] = Field(default_factory=list)


class SystemPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The system prompt text")
    name: Optional[str] = Field(None, description="The name of the system prompt")
    welcome_message: Optional[str] = Field(
        None, description="Custom welcome message for calls. If not provided, will be generated from system prompt."
    )
    organization_id: Optional[str] = Field(None, description="Organization ID this prompt belongs to")
    id: Optional[str] = Field(
        None,
        description="UUID for the prompt (optional - if not provided, backend will generate one). Used for update/activate operations.",
    )


class SystemPromptResponse(BaseModel):
    prompt: str
    name: Optional[str] = None
    welcome_message: Optional[str] = None


class SystemPromptListItem(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    prompt: str
    welcome_message: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    organization_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Organization name")
    domain: Optional[str] = Field(None, description="Organization domain")
    api_key: Optional[str] = Field(None, description="API key for authentication")


class OrganizationResponse(BaseModel):
    id: str
    name: str
    domain: Optional[str] = None
    api_key: Optional[str] = None
    created_at: Optional[str] = None


class WelcomeMessageRequest(BaseModel):
    welcome_message: Optional[str] = Field(None, description="Custom welcome message for calls")
    organization_id: Optional[str] = Field(None, description="Organization ID")

