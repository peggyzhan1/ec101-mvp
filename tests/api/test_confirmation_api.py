from io import BytesIO
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from openpyxl import Workbook
import pytest

import ec101.api.server as server_module

from .conftest import get_json


def workbook_bytes(headers, row):
    output = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append(row)
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def multipart(fields, name, filename, content):
    boundary = f"----ec101-{uuid4().hex}"
    body = bytearray()
    for field_name, value in fields.items():
        body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"\r\n\r\n{value}\r\n'.encode()
        )
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n".encode()
    )
    body.extend(content)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def post_workbook(url, fields, name, filename, content):
    body, content_type = multipart(fields, name, filename, content)
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
    )
    with urlopen(request) as response:
        return response.status, json.loads(response.read())


def recipients_content():
    return workbook_bytes(
        ("费用周期", "太古客户编号", "太古客户名称", "应发金额", "备注"),
        ("2026-09", "0570502563", "佳源食品商行", "500.00", "协议费用"),
    )


def survey_content():
    return workbook_bytes(
        (
            "费用周期", "太古客户编号", "太古客户名称", "是否收到本期全部协议费用",
            "未收到原因", "补充说明", "答卷手机号", "提交时间", "问卷星原始序号",
        ),
        (
            "2026-09", "0570502563", "佳源食品商行", "已收到", "", "",
            "13800000000", "2026-10-09 16:15:00", "1",
        ),
    )


def test_confirmation_recipient_survey_and_get_routes(api_server, api_seed):
    status, recipients = post_workbook(
        f"{api_server}/api/fee-confirmation/recipients",
        {
            "feeCycle": "2026-09",
            "cycleName": "2026年9月",
            "periodStart": "2026-09-01",
            "periodEnd": "2026-09-30",
            "masterSyncBatchId": str(api_seed["master_sync_batch_id"]),
        },
        "recipients",
        "recipients.xlsx",
        recipients_content(),
    )
    assert status == 201
    assert recipients["recipientCount"] == 1
    assert recipients["matchedCount"] == 1

    status, survey = post_workbook(
        f"{api_server}/api/fee-confirmation/surveys",
        {"feeCycle": "2026-09"},
        "survey",
        "survey.xlsx",
        survey_content(),
    )
    assert status == 201
    assert survey["rowCount"] == 1
    assert survey["matchedCount"] == 1

    status, overview = get_json(
        f"{api_server}/api/fee-confirmation/overview?feeCycle=2026-09"
    )
    assert status == 200
    assert overview["received"] == {"customerCount": 1, "expectedAmount": 500}
    params = urlencode({"feeCycle": "2026-09", "status": "已确认收到", "query": "佳源"})
    status, rows = get_json(f"{api_server}/api/fee-confirmation/recipients?{params}")
    assert status == 200 and rows["total"] == 1
    assert "respondentMobile" not in rows["items"][0]
    status, exceptions = get_json(
        f"{api_server}/api/fee-confirmation/exceptions?feeCycle=2026-09"
    )
    assert status == 200 and exceptions["total"] == 0
    assert list(api_seed["archive_dir"].glob("*.xlsx")) == []


def test_confirmation_routes_validate_required_fields_and_unknown_cycle(api_server):
    with pytest.raises(HTTPError) as missing:
        get_json(f"{api_server}/api/fee-confirmation/overview")
    assert missing.value.code == 400

    with pytest.raises(HTTPError) as unknown:
        get_json(f"{api_server}/api/fee-confirmation/overview?feeCycle=2099-01")
    assert unknown.value.code == 404

    with pytest.raises(HTTPError) as bad_upload:
        post_workbook(
            f"{api_server}/api/fee-confirmation/recipients",
            {"feeCycle": "2026-09"},
            "recipients",
            "recipients.xlsx",
            recipients_content(),
        )
    assert bad_upload.value.code == 400


def test_confirmation_upload_rejects_malformed_workbook_as_json_400(api_server):
    with pytest.raises(HTTPError) as malformed:
        post_workbook(
            f"{api_server}/api/fee-confirmation/surveys",
            {"feeCycle": "2026-09"},
            "survey",
            "survey.xlsx",
            b"not-an-xlsx",
        )

    assert malformed.value.code == 400
    assert "error" in json.loads(malformed.value.read())


def test_confirmation_upload_enforces_request_size_limit(api_server, monkeypatch):
    monkeypatch.setattr(server_module, "MAX_MULTIPART_BYTES", 128)

    with pytest.raises(HTTPError) as too_large:
        post_workbook(
            f"{api_server}/api/fee-confirmation/surveys",
            {"feeCycle": "2026-09"},
            "survey",
            "survey.xlsx",
            survey_content(),
        )

    assert too_large.value.code == 400
    assert "大小" in json.loads(too_large.value.read())["error"]
