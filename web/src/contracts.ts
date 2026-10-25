// Generated from FastAPI OpenAPI (backend/src/api/contracts.py). Do not edit: make contracts

/**
 * Index only. The types below come from backend/src/api/contracts.py.
 */
export interface Contracts {}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Analytics".
 */
export interface Analytics {
  site_id: string;
  zones: ZoneTime[];
  /**
   * visit: visits created; zone: with an `arrive` event; lead: with a `lead` event
   */
  funnel: FunnelStep[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ZoneTime".
 */
export interface ZoneTime {
  zone_id: string;
  /**
   * Visits with a closed stay in the zone
   */
  visits: number;
  seconds_total: number;
  seconds_avg: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "FunnelStep".
 */
export interface FunnelStep {
  step: "visit" | "zone" | "lead";
  visits: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DocumentVersion".
 */
export interface DocumentVersion {
  site_id: string;
  version: number;
  status: "draft" | "published";
  author: string;
  created_at: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "EventIn".
 */
export interface EventIn {
  visit_token: string;
  kind: "arrive" | "leave" | "lead";
  /**
   * Required for arrive and leave
   */
  zone_id?: string | null;
  src: "qr" | "nfc" | "manual";
  /**
   * Made by the client; a repeat is not written twice
   */
  client_event_id: string;
  /**
   * Client clock; the offline queue sends late
   */
  occurred_at: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "EventMessage".
 */
export interface EventMessage {
  type?: "event";
  event_id: number;
  site_id: string;
  visit_id: string;
  role: string;
  zone_id: string | null;
  kind: "arrive" | "leave" | "lead";
  src: "qr" | "nfc" | "manual";
  occurred_at: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "EventOut".
 */
export interface EventOut {
  event_id: number;
  /**
   * True: the event was already written, nothing changed
   */
  duplicate: boolean;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  code: string;
  severity: "error" | "warning";
  message: string;
  refs: FindingRef[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "FindingRef".
 */
export interface FindingRef {
  kind: "room" | "zone" | "object" | "layer" | "wall" | "opening";
  id: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "HTTPValidationError".
 */
export interface HTTPValidationError {
  detail?: ValidationError[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ValidationError".
 */
export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: {};
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Health".
 */
export interface Health {
  status: "ok";
  /**
   * Commit of the build (GIT_SHA); unknown outside docker compose
   */
  sha: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Identity".
 */
export interface Identity {
  role: "editor" | "manager" | "expert";
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "LeadCreated".
 */
export interface LeadCreated {
  id: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "LeadIn".
 */
export interface LeadIn {
  name: string;
  phone: string;
  company: string;
  material: string;
  task: string;
  /**
   * Separate consent to personal data processing
   */
  consent_pd: boolean;
  /**
   * Version of the consent text the guest saw
   */
  consent_version: string;
  /**
   * Public visit id: adds a `lead` event
   */
  visit_id?: string | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "LeadOut".
 */
export interface LeadOut {
  id: number;
  created_at: string;
  name: string;
  phone: string;
  company: string;
  material: string;
  task: string;
  protocol: ProtocolIn | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ProtocolIn".
 */
export interface ProtocolIn {
  material: string;
  thickness_mm: number;
  machine: string;
  /**
   * Machine mode or "оценка"
   */
  mode: string;
  time_min: number;
  edge_photo_url?: string | null;
}
/**
 * The tablet's event for a guest: the manager knows visit_id, not the guest's token.
 *
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ManualEventIn".
 */
export interface ManualEventIn {
  kind: "arrive" | "leave" | "lead";
  /**
   * Required for arrive and leave
   */
  zone_id?: string | null;
  src: "manual";
  /**
   * Made by the client; a repeat is not written twice
   */
  client_event_id: string;
  /**
   * Tablet clock
   */
  occurred_at: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanAttributeDef".
 */
export interface PlanAttributeDef {
  key: string;
  label: string;
  type: "string" | "number" | "boolean";
  required: boolean;
  default?: string | number | boolean | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanCatalog".
 */
export interface PlanCatalog {
  version: string;
  /**
   * @maxItems 200
   */
  objectTypes: PlanObjectType[];
  zoneTypes: PlanZoneType[];
  /**
   * @maxItems 50
   */
  rules?: (PlanCountRule | PlanDistanceRule)[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanObjectType".
 */
export interface PlanObjectType {
  id: string;
  label: string;
  category?: string;
  defaultBase_m?: number;
  /**
   * Takes part in collision checks
   */
  physical?: boolean;
  occupiesFloor?: boolean;
  symbol?: "rect" | "circle" | "triangle";
  outline?: [[number, number], [number, number], [number, number], ...[number, number][]] | null;
  attributes?: PlanAttributeDef[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanZoneType".
 */
export interface PlanZoneType {
  id: string;
  label: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanCountRule".
 */
export interface PlanCountRule {
  id: string;
  source: "team-assumption" | "organizer-material";
  rationale: string;
  kind: "count";
  zoneTypeId: string;
  objectTypeId: string;
  scope: "direct" | "inclusive";
  min: number | null;
  max: number | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanDistanceRule".
 */
export interface PlanDistanceRule {
  id: string;
  source: "team-assumption" | "organizer-material";
  rationale: string;
  kind: "distance-to-entrance";
  objectTypeId: string;
  maxDistance_m: number;
  entranceId: string | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanDocument".
 */
export interface PlanDocument {
  schemaVersion: 1;
  id: string;
  name: string;
  room: PlanRoom;
  /**
   * @maxItems 200
   */
  walls: PlanWall[];
  /**
   * @maxItems 200
   */
  openings: PlanOpening[];
  /**
   * @minItems 1
   * @maxItems 50
   */
  layers: [PlanLayer, ...PlanLayer[]];
  /**
   * @maxItems 100
   */
  zones: PlanZone[];
  /**
   * @maxItems 300
   */
  objects: PlanObject[];
  catalog: PlanCatalog;
  extensions?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanRoom".
 */
export interface PlanRoom {
  id: string;
  /**
   * @minItems 3
   * @maxItems 256
   */
  boundary: [[number, number], [number, number], [number, number], ...[number, number][]];
  ceilingHeight_m: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanWall".
 */
export interface PlanWall {
  id: string;
  /**
   * @minItems 2
   * @maxItems 2
   */
  from: [number, number];
  /**
   * @minItems 2
   * @maxItems 2
   */
  to: [number, number];
  thickness_m: number;
  height_m: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanOpening".
 */
export interface PlanOpening {
  id: string;
  wallId: string;
  /**
   * From the wall's `from` end to the near edge
   */
  offset_m: number;
  width_m: number;
  kind: "entrance" | "door" | "window";
  sill_m: number;
  height_m: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanLayer".
 */
export interface PlanLayer {
  id: string;
  name: string;
  visible: boolean;
  locked: boolean;
  order: number;
  typeId?: string | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanZone".
 */
export interface PlanZone {
  id: string;
  typeId: string;
  name: string;
  /**
   * @minItems 3
   * @maxItems 256
   */
  polygon: [[number, number], [number, number], [number, number], ...[number, number][]];
  parentId: string | null;
  layerId: string;
  attributes: {
    [k: string]: string | number | boolean | null;
  };
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlanObject".
 */
export interface PlanObject {
  id: string;
  typeId: string;
  label: string;
  /**
   * Centre of the object
   *
   * @minItems 2
   * @maxItems 2
   */
  position: [number, number];
  /**
   * Extent before rotation
   *
   * @minItems 2
   * @maxItems 2
   */
  size_m: [number, number];
  /**
   * Positive turns clockwise
   */
  rotation_deg: number;
  base_m: number;
  height_m: number;
  zoneId: string | null;
  layerId: string;
  attributes: {
    [k: string]: string | number | boolean | null;
  };
  locked?: boolean | null;
  /**
   * Ring in fractions of size_m, box [-0.5, 0.5]; absent — type
   */
  outline?: [[number, number], [number, number], [number, number], ...[number, number][]] | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RoleChange".
 */
export interface RoleChange {
  role: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RoleMessage".
 */
export interface RoleMessage {
  type?: "role";
  site_id: string;
  visit_id: string;
  role: string;
}
/**
 * Whose content is on the zone screen. visit_id is None until the first scan.
 *
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ScreenMessage".
 */
export interface ScreenMessage {
  type?: "screen";
  site_id: string;
  zone_id: string;
  visit_id: string | null;
  role: string | null;
  since: string | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SiteDocument".
 */
export interface SiteDocument {
  plan: StoredPlan;
  /**
   * 10 зон слайда 3 + вход, переговоры, испытательный блок. Тексты для посетителя без цифр: число — {{fact:<id>}}, имя экспоната — {{item:<id>}} (G1). G5 (луч класса 4) проверяет только POST /api/validate. Каждое из 5 сообщений слайда 10 несёт хотя бы одна зона (carries). Зона в maintenance — с заменой (S2).
   */
  zones: {
    version: 1;
    zones: {
      id:
        | "entrance"
        | "crystals"
        | "quantrons"
        | "diodes"
        | "laser_sources"
        | "robots"
        | "engraving"
        | "cutting"
        | "handheld"
        | "optomechanics"
        | "edu_class"
        | "meeting"
        | "test_lab";
      name: string;
      exhibits: string[];
      /**
       * Способ показа: работа станка, витрина, видео, симулятор.
       */
      display: string;
      safety: {
        /**
         * true — вход только с сопровождением.
         */
        restricted: boolean;
        /**
         * true — в зоне кабина с блокировкой двери. Роли students, media, government не входят в такую зону, в restricted и в test_lab.
         */
        interlock: boolean;
        notes?: string[];
      };
      status: "normal" | "maintenance";
      /**
       * Что показать, пока зона на обслуживании (S2). Обязательно при status: maintenance.
       */
      maintenance?: {
        /**
         * Что видит посетитель вместо зоны: видео, образцы, другая зона.
         */
        replacement: string;
        /**
         * id зоны-замены, если есть.
         */
        zone?: string;
      };
      /**
       * Сообщения слайда 10: масштаб, история, локализация, полный цикл, российское производство.
       */
      carries: ("scale" | "history" | "localization" | "full_cycle" | "russian_production")[];
      /**
       * Тексты зоны для посетителя.
       */
      messages: string[];
    }[];
  };
  /**
   * 6 аудиторий слайда 7 → шаги по зонам. Роль — один маршрут. Сумма минут ≤ duration_max_min; органы власти ≤ 40 мин (S4.1). Пропуск зоны — в skipped с причиной. Тексты без цифр: число — {{fact:<id>}}, экспонат — {{item:<id>}} (G1).
   */
  routes: {
    version: 1;
    routes: {
      role: "prospect" | "customer" | "education" | "government" | "students" | "media";
      title: string;
      /**
       * Длительность визита роли, минуты.
       */
      duration_max_min: number;
      /**
       * @minItems 1
       */
      steps: [
        {
          zone: string;
          minutes: number;
          message: string;
        },
        ...{
          zone: string;
          minutes: number;
          message: string;
        }[]
      ];
      skipped?: {
        zone: string;
        reason: string;
      }[];
    }[];
  };
  /**
   * Каждое число продукта, записки и слайдов. У факта есть источник: case, public или norm (G1). Число T8 (80, 400, 14400) требует public (G14). Проверяет scripts/check-content.py.
   */
  facts: {
    version: 1;
    facts: {
      id: string;
      /**
       * Число для расчётов и сверки.
       */
      value: number;
      /**
       * Единица: %, м², ед./год, шт. и т. п.
       */
      unit: string;
      /**
       * Как писать число в продукте и на слайде.
       */
      text: string;
      /**
       * Число из кейса: номер слайда и формулировка кейса.
       */
      case?: {
        slide: number;
        value: string;
      };
      /**
       * Публичный источник: адрес, дата публикации или проверки, значение в источнике.
       */
      public?: {
        url: string;
        date: string;
        value: string;
        note?: string;
      };
      /**
       * Норма: документ и пункт.
       */
      norm?: {
        doc: string;
        clause: string;
        url?: string;
      };
      /**
       * true — норму или число надо проверить; интерфейс показывает метку «уточняется».
       */
      check?: boolean;
    }[];
  };
  /**
   * Станки и изделия для зон, плана и подбора станка. Неизвестное пишем явно: null в laser_class, beam, size_mm или в одном измерении. Габарит — полный size_mm + size_source, иначе estimate: true + estimate_basis (G4). Цена, рабочее поле и мощность — только с источником.
   */
  catalog: {
    version: 1;
    items: {
      id: string;
      name: string;
      category:
        | "cutting"
        | "engraving"
        | "welding"
        | "cleaning"
        | "hardening"
        | "optomechanics"
        | "component"
        | "ventilation"
        | "education";
      /**
       * Длина × ширина × высота, мм, как в источнике. null — габарит не опубликован; null в измерении — измерение не опубликовано.
       */
      size_mm: {
        length: number | null;
        width: number | null;
        height: number | null;
      } | null;
      /**
       * Откуда габарит: URL или документ и страница.
       */
      size_source?: string;
      /**
       * Другие опубликованные габариты с источником (например, сайт и каталог расходятся).
       */
      size_alt?: {
        size_mm: {
          length: number;
          width: number;
          height: number;
        };
        size_source: string;
      }[];
      /**
       * true — габарит оценочный или неполный; интерфейс показывает метку «оценка».
       */
      estimate: boolean;
      /**
       * Основание оценки.
       */
      estimate_basis?: string;
      /**
       * null — класс не опубликован.
       */
      laser_class: "1" | "1M" | "2" | "2M" | "3R" | "3B" | "4" | "none" | null;
      /**
       * null — неизвестно.
       */
      beam: "open" | "closed" | null;
      /**
       * Рабочее поле, мм.
       */
      work_area_mm?: {
        length: number;
        width: number;
        source: string;
      };
      /**
       * Мощность лазера, Вт: диапазон исполнений; одно значение — min = max.
       */
      power_w?: {
        min: number;
        max: number;
        source: string;
      };
      price_from?: {
        value_rub: number;
        source: string;
        date?: string;
      };
      /**
       * Карточка изделия: URL или документ.
       */
      source: string;
      /**
       * true — экспонат есть в действующем шоуруме.
       */
      in_current_showroom: boolean;
      /**
       * id типа объекта в catalog.objectTypes плана (PlanDocument, content/plan-219*.json). Связывает экспонат с объектами плана; lint проверяет, что тип есть в плане.
       */
      plan_type?: string;
      /**
       * Пояснение: неизвестный класс или луч, расхождение источников, [СПРОСИТЬ].
       */
      note?: string;
    }[];
  };
}
/**
 * Validate with PlanDocument, serialize the exact input including unknown extensions.
 *
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "StoredPlan".
 */
export interface StoredPlan {
  schemaVersion: 1;
  id: string;
  name: string;
  room: PlanRoom;
  /**
   * @maxItems 200
   */
  walls: PlanWall[];
  /**
   * @maxItems 200
   */
  openings: PlanOpening[];
  /**
   * @minItems 1
   * @maxItems 50
   */
  layers: [PlanLayer, ...PlanLayer[]];
  /**
   * @maxItems 100
   */
  zones: PlanZone[];
  /**
   * @maxItems 300
   */
  objects: PlanObject[];
  catalog: PlanCatalog;
  extensions?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SiteDocumentVersion".
 */
export interface SiteDocumentVersion {
  site_id: string;
  version: number;
  status: "draft" | "published";
  author: string;
  created_at: string;
  body: SiteDocument;
  findings: Finding[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ValidateResponse".
 */
export interface ValidateResponse {
  findings: Finding[];
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "VersionInput".
 */
export interface VersionInput {
  version: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "VisitCreate".
 */
export interface VisitCreate {
  site_id: string;
  role?: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "VisitCreated".
 */
export interface VisitCreated {
  /**
   * Public id: screens and the tablet use it
   */
  visit_id: string;
  /**
   * Secret of the guest's phone; sent with the guest's events
   */
  token: string;
  site_id: string;
  role: string;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "VisitInfo".
 */
export interface VisitInfo {
  visit_id: string;
  role: string;
  created_at: string;
  /**
   * Zone of the latest `arrive` event
   */
  last_zone_id: string | null;
  last_event_at: string | null;
}
