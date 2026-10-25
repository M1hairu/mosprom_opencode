"""Editor adds and deletes facts and catalog exhibits; used entries stay (#274)."""

from test_site_documents import URL, credentials, save

# Fixtures engine, client and document of the site document tests.
pytest_plugins = ("test_site_documents",)

FACT = {
    "value": 600,
    "unit": "чел.",
    "text": "более 600 сотрудников на производстве",
    "public": {"url": "https://lassard.ru/about/career", "date": "2026-10-24", "value": "600"},
}


def test_new_fact_gets_code_from_text_and_lands_in_draft(client, document):
    save(client, document)
    answer = client.post(f"{URL}/facts", json=FACT, auth=credentials())
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "draft"
    fact = answer.json()["body"]["facts"]["facts"][-1]
    assert fact["id"] == "bolee_600_sotrudnikov_na"


def test_fact_without_source_is_refused(client, document):
    save(client, document)
    fact = {k: v for k, v in FACT.items() if k != "public"}
    answer = client.post(f"{URL}/facts", json=fact, auth=credentials())
    assert answer.status_code == 422
    assert any("без источника" in e for e in answer.json()["detail"]["errors"])


def test_fact_number_must_be_in_its_text(client, document):
    save(client, document)
    answer = client.post(f"{URL}/facts", json={**FACT, "value": 700}, auth=credentials())
    assert answer.status_code == 422
    assert any("нет числа value=700" in e for e in answer.json()["detail"]["errors"])


def test_used_fact_is_not_deleted_and_places_are_listed(client, document):
    draft = save(client, document)
    answer = client.delete(f"{URL}/facts/employees", auth=credentials())
    assert answer.status_code == 409
    assert answer.json()["detail"]["usage"]
    versions = client.get(f"{URL}/versions", auth=credentials("expert")).json()
    assert versions[0]["version"] == draft["version"]


def test_unused_fact_is_deleted(client, document):
    save(client, document)
    answer = client.delete(f"{URL}/facts/laser_power_max", auth=credentials())
    assert answer.status_code == 200, answer.text
    ids = [f["id"] for f in answer.json()["body"]["facts"]["facts"]]
    assert "laser_power_max" not in ids


def test_exhibit_in_a_zone_is_not_deleted(client, document):
    save(client, document)
    zone = next(z for z in document["zones"]["zones"] if z["exhibits"])
    answer = client.delete(f"{URL}/items/{zone['exhibits'][0]}", auth=credentials())
    assert answer.status_code == 409
    assert f"зона «{zone['name']}»" in answer.json()["detail"]["usage"]


def test_exhibit_without_size_source_or_estimate_is_refused(client, document):
    save(client, document)
    item = {
        "name": "Стенд",
        "category": "education",
        "size_mm": {"length": 1000, "width": 500, "height": 1200},
        "estimate": False,
        "laser_class": None,
        "beam": None,
        "source": "https://lassard.ru",
        "in_current_showroom": False,
    }
    answer = client.post(f"{URL}/items", json=item, auth=credentials())
    assert answer.status_code == 422
    assert any("(G4)" in e for e in answer.json()["detail"]["errors"])
    answer = client.post(f"{URL}/items", json={**item, "size_source": "замер"}, auth=credentials())
    assert answer.status_code == 200, answer.text


def test_expert_cannot_add_or_delete(client, document):
    save(client, document)
    assert client.post(f"{URL}/facts", json=FACT, auth=credentials("expert")).status_code == 403
    assert client.delete(f"{URL}/facts/x", auth=credentials("expert")).status_code == 403
