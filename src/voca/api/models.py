"""
Pydantic models for API request/response validation.
"""
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


class TestStatus(str, Enum):
    """Status for medical test results."""
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class MedicalTestResult(BaseModel):
    """Structured medical test result."""
    name: str
    status: TestStatus
    value: Optional[str] = None
    unit: Optional[str] = None


class MedicalDemoRequest(BaseModel):
    """Request to initiate a medical demo call."""
    phone_number: str
    patient_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    test_results: List[MedicalTestResult] = Field(default_factory=list)
    medical_advice: Optional[str] = None


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


class LogEntry(BaseModel):
    timestamp: str
    message: str


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
    welcome_message: Optional[str] = Field(None, description="Custom welcome message for calls. If not provided, will be generated from system prompt.")
    organization_id: Optional[str] = Field(
        None,
        description="Organization ID this prompt belongs to",
    )


class SystemPromptResponse(BaseModel):
    prompt: str
    name: Optional[str] = None
    welcome_message: Optional[str] = None


class SystemPromptListItem(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = None
    name: Optional[str] = None
    prompt: str
    welcome_message: Optional[str] = None
    is_default: Optional[bool] = None
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

