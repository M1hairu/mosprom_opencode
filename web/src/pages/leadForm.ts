// Test lead from the manager tablet (#132): POST /api/sites/{site}/leads with the visit_id of the guest.
import type { LeadIn } from "../contracts";

/** Draft wording (D-019): shown as «черновик» until ЛАССАРД approves the text and the policy URL. */
export const CONSENT_VERSION = "draft-2026-10";
export const CONSENT_TEXT =
  "Я согласен, что ЛАССАРД обработает моё имя, телефон и название компании. Цель — подготовить тест " +
  "на моём образце и связаться со мной. Обработка — по 152-ФЗ и политике ЛАССАРД в отношении персональных данных.";
/** No real policy URL is known yet: the form shows this mark instead of a link. */
export const POLICY_LINK_TEXT = "Политика обработки персональных данных ЛАССАРД: [СПРОСИТЬ]";

export type LeadDraft = Pick<LeadIn, "name" | "phone" | "company" | "material" | "task" | "consent_pd">;

export const emptyDraft = (): LeadDraft => ({ name: "", phone: "", company: "", material: "", task: "", consent_pd: false });

// Same rule as PHONE_PATTERN and phone_has_digits in backend/src/api/lead_contracts.py.
const PHONE = /^[0-9+() -]{5,32}$/;

export function phoneOk(phone: string): boolean {
  const p = phone.trim();
  return PHONE.test(p) && (p.match(/[0-9]/g)?.length ?? 0) >= 5;
}

/** The submit button is enabled only when this is true. */
export function canSend(d: LeadDraft): boolean {
  const filled = [d.name, d.company, d.material, d.task].every((s) => s.trim().length > 0);
  return filled && phoneOk(d.phone) && d.consent_pd;
}

export function leadBody(d: LeadDraft, visitId: string): LeadIn {
  return {
    name: d.name.trim(),
    phone: d.phone.trim(),
    company: d.company.trim(),
    material: d.material.trim(),
    task: d.task.trim(),
    consent_pd: d.consent_pd,
    consent_version: CONSENT_VERSION,
    visit_id: visitId,
  };
}

const INVALID = "Заявка не создана: проверьте поля формы.";

/** Russian text of a failed response. 422 comes as {code, message} (our rejects) or as a Pydantic list. */
export function leadError(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (status === 422) {
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string" && message) return message;
    }
    return INVALID;
  }
  if (status === 404) return "Заявка не создана: площадка не найдена.";
  return `Заявка не создана: ошибка сервера ${status}.`;
}
