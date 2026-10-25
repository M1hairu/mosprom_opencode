"""Models of the lead routes (leads.py, #31).

Consumers: web/src/contracts.ts (generated, make contracts): the guest lead form at the end of
the route (guide), the manager tablet (#38, #132), CSV export and CRM (#34), the /admin lead
list (#56), backend/tests/test_leads.py.
"""

from pydantic import BaseModel, Field, field_validator

PHONE_PATTERN = r"^[0-9+() \-]{5,32}$"  # digits, space, + ( ) -


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(pattern=PHONE_PATTERN)
    company: str = Field(min_length=1, max_length=200)
    material: str = Field(min_length=1, max_length=200)
    task: str = Field(min_length=1, max_length=2000)
    consent_pd: bool = Field(description="Separate consent to personal data processing")
    consent_version: str = Field(
        min_length=1, max_length=32, description="Version of the consent text the guest saw"
    )
    visit_id: str | None = Field(
        default=None, max_length=32, description="Public visit id: adds a `lead` event"
    )

    @field_validator("phone")
    @classmethod
    def phone_has_digits(cls, value: str) -> str:
        if sum(c.isdigit() for c in value) < 5:
            raise ValueError("В телефоне должно быть не меньше 5 цифр")
        return value


class LeadCreated(BaseModel):
    id: int


class ProtocolIn(BaseModel):
    material: str = Field(min_length=1, max_length=200)
    thickness_mm: float = Field(gt=0, le=100)
    machine: str = Field(min_length=1, max_length=100)
    mode: str = Field(min_length=1, max_length=100, description='Machine mode or "оценка"')
    time_min: float = Field(gt=0, le=1000)
    edge_photo_url: str | None = Field(default=None, max_length=500)


class LeadOut(BaseModel):
    id: int
    created_at: str
    name: str
    phone: str
    company: str
    material: str
    task: str
    protocol: ProtocolIn | None
