"""Models of the visit, event, SSE and analytics routes (visits.py, analytics.py).

Consumers: web/src/contracts.ts (generated, make contracts): the guide, the zone screen, the
tablet. Kept apart from contracts.py so that task branches do not edit one file.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

# Ids come from content (site, zone) or from the client (event). Letters, digits, _ . -
Slug = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", max_length=64)]
Role = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=32)
]  # audience id, e.g. the "Other" button of the entrance question
# manual: the tablet moves a guest to a zone (POST /api/visits/{visit_id}/events, manager role).
Source = Literal["qr", "nfc", "manual"]
EventKind = Literal["arrive", "leave", "lead"]


class VisitCreate(BaseModel):
    site_id: Slug
    role: Role = "other"


class VisitCreated(BaseModel):
    visit_id: str = Field(description="Public id: screens and the tablet use it")
    token: str = Field(description="Secret of the guest's phone; sent with the guest's events")
    site_id: str
    role: str


class RoleChange(BaseModel):
    role: Role


class VisitInfo(BaseModel):
    visit_id: str
    role: str
    created_at: AwareDatetime
    last_zone_id: str | None = Field(description="Zone of the latest `arrive` event")
    last_event_at: AwareDatetime | None


class EventIn(BaseModel):
    visit_token: str
    kind: EventKind
    zone_id: Slug | None = Field(default=None, description="Required for arrive and leave")
    src: Source
    client_event_id: Slug = Field(description="Made by the client; a repeat is not written twice")
    occurred_at: AwareDatetime = Field(description="Client clock; the offline queue sends late")

    @model_validator(mode="after")
    def zone_for_arrive_and_leave(self) -> "EventIn":
        if self.kind != "lead" and self.zone_id is None:
            raise ValueError("zone_id обязателен для событий arrive и leave")
        return self


class ManualEventIn(BaseModel):
    """The tablet's event for a guest: the manager knows visit_id, not the guest's token."""

    kind: EventKind
    zone_id: Slug | None = Field(default=None, description="Required for arrive and leave")
    src: Literal["manual"]
    client_event_id: Slug = Field(description="Made by the client; a repeat is not written twice")
    occurred_at: AwareDatetime = Field(description="Tablet clock")

    @model_validator(mode="after")
    def zone_for_arrive_and_leave(self) -> "ManualEventIn":
        if self.kind != "lead" and self.zone_id is None:
            raise ValueError("zone_id обязателен для событий arrive и leave")
        return self


class EventOut(BaseModel):
    event_id: int
    duplicate: bool = Field(description="True: the event was already written, nothing changed")


# --- SSE messages: one JSON object per `data:` line, `type` tells which.


class ScreenMessage(BaseModel):
    """Whose content is on the zone screen. visit_id is None until the first scan."""

    type: Literal["screen"] = "screen"
    site_id: str
    zone_id: str
    visit_id: str | None
    role: str | None
    since: AwareDatetime | None


class EventMessage(BaseModel):
    type: Literal["event"] = "event"
    event_id: int
    site_id: str
    visit_id: str
    role: str
    zone_id: str | None
    kind: EventKind
    src: Source
    occurred_at: AwareDatetime


class RoleMessage(BaseModel):
    type: Literal["role"] = "role"
    site_id: str
    visit_id: str
    role: str


SiteStreamMessage = Annotated[
    ScreenMessage | EventMessage | RoleMessage, Field(discriminator="type")
]


# --- GET /api/analytics


class ZoneTime(BaseModel):
    zone_id: str
    visits: int = Field(description="Visits with a closed stay in the zone")
    seconds_total: int
    seconds_avg: int


class FunnelStep(BaseModel):
    step: Literal["visit", "zone", "lead"]
    visits: int


class Analytics(BaseModel):
    site_id: str
    zones: list[ZoneTime]
    funnel: list[FunnelStep] = Field(
        description="visit: visits created; zone: with an `arrive` event; lead: with a `lead` event"
    )
