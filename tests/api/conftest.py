from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.request import urlopen

import pytest

from ec101.api.server import create_handler
from ec101.calculation.engine import calculate_batch
from ec101.confirmation.master_data import sync_master_data
from ec101.contract.workbook import read_standard_workbook
from ec101.converters.kuaima import convert_kuaima
from ec101.db import connect_database, create_database
from ec101.importing.service import ArchiveMetadata, import_snapshot
from tests.fixtures.kuaima_builder import build_kuaima_request


def import_conversion(db, conversion):
    content = conversion.sources_zip_path.read_bytes()
    return import_snapshot(
        db,
        read_standard_workbook(conversion.workbook_path),
        ArchiveMetadata(str(conversion.sources_zip_path), sha256(content).hexdigest(), len(content)),
    )


@pytest.fixture
def api_seed(tmp_path):
    database_path = tmp_path / "api.db"
    create_database(database_path)
    db = connect_database(database_path)

    request_a = build_kuaima_request(tmp_path / "dealer-a")
    conversion_a = convert_kuaima(request_a)
    batch_a = import_conversion(db, conversion_a).import_batch_id
    old_run = calculate_batch(db, batch_a, "2026-09-21")
    latest_a = calculate_batch(db, batch_a, "2026-09-22")

    request_b = build_kuaima_request(tmp_path / "dealer-b")
    request_b = replace(request_b, dealer_name="经销商乙")
    conversion_b = convert_kuaima(request_b)
    batch_b = import_conversion(db, conversion_b).import_batch_id
    latest_b = calculate_batch(db, batch_b, "2026-09-22")
    platform_id = db.execute(
        "SELECT dealer_platform_id FROM customer WHERE import_batch_id = ? LIMIT 1",
        (batch_a,),
    ).fetchone()[0]
    master_sync = sync_master_data(
        db,
        "areapartner",
        [{
            "sap_customer_primary_key": "sap-pk-1",
            "sap_customer_code": "0570502563",
            "sap_customer_name": "佳源食品商行",
        }],
        [{
            "source_mapping_id": "mapping-1",
            "dealer_platform_id": platform_id,
            "source_customer_code": "C1",
            "source_customer_name": "客户一",
            "sap_customer_code": "0570502563",
            "sap_customer_name": "佳源食品商行",
            "match_status": "匹配成功",
        }],
        "2026-10-01 09:00:00",
    )
    db.close()

    return {
        "db_path": database_path,
        "archive_dir": tmp_path / "archives",
        "batch_a": batch_a,
        "batch_b": batch_b,
        "old_run": old_run,
        "latest_a": latest_a,
        "latest_b": latest_b,
        "conversion_a": conversion_a,
        "master_sync_batch_id": master_sync.master_sync_batch_id,
    }


@pytest.fixture
def api_db(api_seed):
    db = connect_database(api_seed["db_path"])
    yield db
    db.close()


@pytest.fixture
def api_server(api_seed):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        create_handler(api_seed["db_path"], api_seed["archive_dir"]),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield base_url
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def get_json(url):
    with urlopen(url) as response:
        return response.status, json.loads(response.read())
