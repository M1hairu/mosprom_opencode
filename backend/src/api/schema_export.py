"""JSON Schema of the API models from FastAPI OpenAPI, input of json2ts (make contracts)."""

import json

from api.main import app


def _draft7_tuples(node: object) -> None:
    """json2ts reads a tuple as draft-07 `items: [...]`; Pydantic writes 2020-12 `prefixItems`."""
    if isinstance(node, dict):
        if "prefixItems" in node:
            node["items"] = node.pop("prefixItems")
        for value in node.values():
            _draft7_tuples(value)
    elif isinstance(node, list):
        for value in node:
            _draft7_tuples(value)


def contracts_schema() -> dict:
    schemas = app.openapi()["components"]["schemas"]
    # json2ts resolves $ref inside the document: components/schemas become $defs.
    defs = json.loads(json.dumps(schemas).replace("#/components/schemas/", "#/$defs/"))
    # A field title makes json2ts emit a named alias (Status, Sha) that clashes across models.
    for model in defs.values():
        for field in model.get("properties", {}).values():
            field.pop("title", None)
    _draft7_tuples(defs)
    return {
        "title": "Contracts",
        "description": "Index only. The types below come from backend/src/api/contracts.py.",
        "type": "object",
        "additionalProperties": False,
        "$defs": defs,
    }


if __name__ == "__main__":
    print(json.dumps(contracts_schema(), ensure_ascii=False, indent=2))
