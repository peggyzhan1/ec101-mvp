from hashlib import sha256
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from ec101.api.queries import get_import, list_imports

from .conftest import get_json


def multipart(fields, files):
    boundary = f"----ec101-{uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for name, filename, content, content_type in files:
        body.extend(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n".encode()
        )
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def test_import_read_models(api_db, api_seed):
    imports = list_imports(api_db)
    detail = get_import(api_db, api_seed["batch_a"])

    assert len(imports) == 2
    assert detail["importBatchId"] == api_seed["batch_a"]
    assert detail["status"] == "calculated"
    assert detail["latestCalculationRunId"] == api_seed["latest_a"]


def test_health_import_detail_and_issue_http_routes(api_server, api_seed):
    assert get_json(f"{api_server}/health") == (200, {"status": "ok"})
    status, imports = get_json(f"{api_server}/api/imports")
    assert status == 200 and len(imports) == 2
    status, detail = get_json(f"{api_server}/api/imports/{api_seed['batch_a']}")
    assert status == 200 and detail["importBatchId"] == api_seed["batch_a"]
    status, issues = get_json(f"{api_server}/api/imports/{api_seed['batch_a']}/issues")
    assert status == 200 and issues == {"items": [], "total": 0}


def test_post_import_archives_sources_imports_and_calculates_once(api_server, api_seed):
    workbook = api_seed["conversion_a"].workbook_path.read_bytes()
    sources = api_seed["conversion_a"].sources_zip_path.read_bytes()
    body, content_type = multipart(
        {"calcDate": "2026-09-22"},
        [
            ("standard", "standard.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("sources", "sources.zip", sources, "application/zip"),
        ],
    )
    request = Request(
        f"{api_server}/api/imports", data=body, method="POST",
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
    )

    with urlopen(request) as response:
        payload = json.loads(response.read())

    assert response.status == 201
    assert payload["status"] == "calculated"
    assert payload["calculationRunId"] > 0
    assert payload["archive"]["sha256"] == sha256(sources).hexdigest()
