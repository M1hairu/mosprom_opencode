import { describe, expect, it } from "vitest";
import { canSend, CONSENT_VERSION, emptyDraft, leadBody, leadError, phoneOk } from "./leadForm";

const full = { name: "Анна", phone: "+7 (900) 000-00-00", company: "ООО Тест", material: "сталь 3 мм", task: "маркировка", consent_pd: true };

describe("canSend", () => {
  it("is false for an empty form", () => {
    expect(canSend(emptyDraft())).toBe(false);
  });
  it("is true when all fields and the consent are filled", () => {
    expect(canSend(full)).toBe(true);
  });
  it("is false without the consent", () => {
    expect(canSend({ ...full, consent_pd: false })).toBe(false);
  });
  it("is false when a field has only spaces", () => {
    expect(canSend({ ...full, task: "   " })).toBe(false);
  });
  it("is false for a phone with letters or fewer than 5 digits", () => {
    expect(canSend({ ...full, phone: "abc12345" })).toBe(false);
    expect(phoneOk("+7 (9)")).toBe(false);
    expect(phoneOk("8 900 000")).toBe(true);
  });
});

describe("leadBody", () => {
  it("adds the visit id and the consent version", () => {
    const body = leadBody({ ...full, name: " Анна " }, "v123");
    expect(body).toMatchObject({ name: "Анна", visit_id: "v123", consent_version: CONSENT_VERSION, consent_pd: true });
  });
});

describe("leadError", () => {
  it("shows the server message of our reject", () => {
    const body = { detail: { code: "REJ_MATERIAL_FORBIDDEN", message: "Этот материал мы не обрабатываем лазером." } };
    expect(leadError(422, body)).toBe("Этот материал мы не обрабатываем лазером.");
  });
  it("shows a Russian fallback for a Pydantic list", () => {
    const body = { detail: [{ loc: ["body", "phone"], msg: "String should match pattern" }] };
    expect(leadError(422, body)).toBe("Заявка не создана: проверьте поля формы.");
  });
  it("shows the status for other errors", () => {
    expect(leadError(500, null)).toBe("Заявка не создана: ошибка сервера 500.");
  });
});
