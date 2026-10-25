"""Guest leads, manager test protocol, export and webhook (#31).

The guest is anonymous. The consent to personal data (152-FZ) is a separate field: no consent,
no row. A forbidden material is rejected with REJ_MATERIAL_FORBIDDEN (concept/05-safety.md 7.2).
The webhook never blocks the save: a failure is only logged.
"""

import csv
import html
import io
import json
import logging
import os
import urllib.request
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import auth, db
from api.broker import broker
from api.lead_contracts import LeadCreated, LeadIn, LeadOut, ProtocolIn
from api.lead_model import Lead
from api.model import Site
from api.visit_contracts import EventMessage, Slug
from api.visit_model import GuestEvent, Visit

log = logging.getLogger("leads")
router = APIRouter(prefix="/api/sites/{site_id}")
Db = Annotated[Session, Depends(db.get_session)]

FORBIDDEN_MATERIALS = ("пвх", "pvc", "поливинилхлорид", "polyvinyl")
CSV_COLUMNS = [
    "id", "created_at", "consent_at", "consent_version", "name", "phone", "company", "material", "task",
    "p_material", "p_thickness_mm", "p_machine", "p_mode", "p_time_min", "p_edge_photo_url",
]  # fmt: skip
UNSAFE_START = ("=", "+", "-", "@", "\t", "\r")


def reject(code: str, message: str) -> HTTPException:
    return HTTPException(422, {"code": code, "message": message})


def is_forbidden(material: str) -> bool:
    text = material.lower()
    return any(word in text for word in FORBIDDEN_MATERIALS)


def to_out(row: Lead) -> LeadOut:
    protocol = None
    if row.p_filled_at is not None:
        protocol = ProtocolIn(
            material=row.p_material,
            thickness_mm=row.p_thickness_mm,
            machine=row.p_machine,
            mode=row.p_mode,
            time_min=row.p_time_min,
            edge_photo_url=row.p_edge_photo_url,
        )
    return LeadOut(
        id=row.id,
        created_at=row.created_at.isoformat(),
        name=row.name,
        phone=row.phone,
        company=row.company,
        material=row.material,
        task=row.task,
        protocol=protocol,
    )


def send_webhook(payload: dict) -> None:
    url = os.environ.get("LEADS_WEBHOOK_URL", "")
    if not url:
        return
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=5).close()
    except Exception:
        log.exception("Webhook заявки не доставлен: заявка сохранена")


def add_lead_event(session: Session, site_id: str, visit_id: str, lead_id: int) -> None:
    """The analytics funnel and the tablet badge read the `lead` event of the visit."""
    visit = session.get(Visit, visit_id)
    if visit is None or visit.site_id != site_id:
        return  # unknown visit: the lead is saved anyway
    event = GuestEvent(
        visit_id=visit.id,
        site_id=site_id,
        zone_id=None,
        kind="lead",
        src="manual",
        client_event_id=f"lead-{lead_id}",
        occurred_at=datetime.now(UTC),
    )
    session.add(event)
    session.commit()
    broker.publish(
        (site_id,),
        EventMessage(
            event_id=event.id,
            site_id=site_id,
            visit_id=visit.id,
            role=visit.role,
            zone_id=None,
            kind="lead",
            src="manual",
            occurred_at=event.occurred_at,
        ),
    )


@router.post("/leads", status_code=201)
def create_lead(
    site_id: Slug, body: LeadIn, session: Db, background: BackgroundTasks
) -> LeadCreated:
    if not body.consent_pd:
        raise reject("REJ_CONSENT_REQUIRED", "Нужно согласие на обработку персональных данных")
    if is_forbidden(body.material):
        raise reject(
            "REJ_MATERIAL_FORBIDDEN",
            "Этот материал мы не обрабатываем лазером. Он выделяет вредные газы. "
            "Привезите образец без покрытия или другой материал",
        )
    if session.get(Site, site_id) is None:
        raise HTTPException(404, "Площадка не найдена")
    row = Lead(site_id=site_id, **body.model_dump(exclude={"consent_pd", "visit_id"}))
    session.add(row)
    session.commit()
    session.refresh(row)
    if body.visit_id:
        add_lead_event(session, site_id, body.visit_id, row.id)
    background.add_task(send_webhook, {"event": "lead", "site_id": site_id, "lead_id": row.id})
    return LeadCreated(id=row.id)


@router.put("/leads/{lead_id}/protocol")
def fill_protocol(
    site_id: Slug,
    lead_id: int,
    body: ProtocolIn,
    session: Db,
    _: Annotated[auth.Identity, Depends(auth.manager)],
) -> LeadOut:
    row = lead_row(session, site_id, lead_id)
    if is_forbidden(body.material):
        raise reject("REJ_MATERIAL_FORBIDDEN", "Материал в перечне запрета")
    row.p_material = body.material
    row.p_thickness_mm = body.thickness_mm
    row.p_machine = body.machine
    row.p_mode = body.mode
    row.p_time_min = body.time_min
    row.p_edge_photo_url = body.edge_photo_url
    row.p_filled_at = datetime.now(UTC)
    session.commit()
    return to_out(row)


def lead_row(session: Session, site_id: str, lead_id: int) -> Lead:
    row = session.get(Lead, lead_id)
    if row is None or row.site_id != site_id:
        raise HTTPException(404, "Заявка не найдена")
    return row


def staff(user: Annotated[auth.Identity, Depends(auth.identity)]) -> auth.Identity:
    if user.role not in ("editor", "manager"):
        raise HTTPException(403, "Нужна роль редактора или менеджера")
    return user


def rows(session: Session, site_id: str) -> list[Lead]:
    query = select(Lead).where(Lead.site_id == site_id).order_by(Lead.id)
    return list(session.scalars(query))


@router.get("/leads")
def list_leads(
    site_id: Slug, session: Db, _: Annotated[auth.Identity, Depends(staff)]
) -> list[LeadOut]:
    return [to_out(row) for row in rows(session, site_id)]


def safe_cell(column: str, value) -> str:
    """Stops spreadsheet formula injection from guest text. The phone is validated: no prefix."""
    text = "" if value is None else str(value)
    if column == "phone":
        return text
    return "'" + text if text[:1] in UNSAFE_START else text


@router.get("/leads.csv")
def leads_csv(site_id: Slug, session: Db, _: Annotated[auth.Identity, Depends(staff)]) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in rows(session, site_id):
        writer.writerow([safe_cell(column, getattr(row, column)) for column in CSV_COLUMNS])
    return Response(
        "﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )


REPORT_PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Протокол испытания № {id}</title>
<style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: Montserrat, Verdana, sans-serif; color: #020A0A; margin: 0; }}
header {{ border-bottom: 4px solid #DD191C; padding-bottom: 8px; margin-bottom: 20px; }}
header b {{ color: #DD191C; font-size: 22px; letter-spacing: 1px; }}
h1 {{ font-size: 20px; margin: 0 0 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #D9D9D9; }}
th {{ width: 40%; color: #606060; font-weight: normal; }}
footer {{ margin-top: 24px; color: #868686; font-size: 12px; }}
@media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style></head><body>
<header><b>ЛАССАРД</b> <span>LASSARD</span></header>
<h1>Протокол испытания образца № {id}</h1>
<table>
<tr><th>Заказчик</th><td>{company}</td></tr>
<tr><th>Материал</th><td>{material}</td></tr>
<tr><th>Толщина, мм</th><td>{thickness}</td></tr>
<tr><th>Станок</th><td>{machine}</td></tr>
<tr><th>Режим</th><td>{mode}</td></tr>
<tr><th>Время, мин</th><td>{time}</td></tr>
{photo}</table>
<footer>Значения взяты из протокола, который заполнил менеджер.</footer>
</body></html>"""


def ru_number(value: float) -> str:
    """2.0 -> "2", 2.5 -> "2,5"."""
    return f"{value:g}".replace(".", ",")


@router.get("/leads/{lead_id}/report", response_class=HTMLResponse)
def report(
    site_id: Slug,
    lead_id: int,
    session: Db,
    _: Annotated[auth.Identity, Depends(auth.manager)],
) -> HTMLResponse:
    """Printable A4 page. The PDF comes from the browser print dialog."""
    row = lead_row(session, site_id, lead_id)
    if row.p_filled_at is None:
        raise HTTPException(409, "Протокол ещё не заполнен")
    e = html.escape
    photo = ""
    if row.p_edge_photo_url:
        photo = f"<tr><th>Фото кромки</th><td>{e(row.p_edge_photo_url)}</td></tr>"
    page = REPORT_PAGE.format(
        id=row.id,
        company=e(row.company),
        material=e(row.p_material),
        thickness=ru_number(row.p_thickness_mm),
        machine=e(row.p_machine),
        mode=e(row.p_mode),
        time=ru_number(row.p_time_min),
        photo=photo,
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
