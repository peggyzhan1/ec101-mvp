from hashlib import sha256

from ec101.calculation.engine import calculate_batch
from ec101.contract.workbook import read_standard_workbook
from ec101.converters.kuaima import convert_kuaima
from ec101.db import connect_database, create_database
from ec101.importing.service import ArchiveMetadata, import_snapshot
from tests.fixtures.kuaima_builder import build_kuaima_request


def test_kuaima_convert_import_calculate_pipeline(tmp_path):
    conversion = convert_kuaima(build_kuaima_request(tmp_path))
    workbook = read_standard_workbook(conversion.workbook_path)
    database_path = tmp_path / "ec101.db"
    create_database(database_path)
    db = connect_database(database_path)
    archive_bytes = conversion.sources_zip_path.read_bytes()
    imported = import_snapshot(db, workbook, ArchiveMetadata(
        str(conversion.sources_zip_path), sha256(archive_bytes).hexdigest(), len(archive_bytes)
    ))

    run_id = calculate_batch(db, imported.import_batch_id, "2026-09-22")

    assert db.execute(
        "SELECT released_orders, released_activity_benefit, released_coupon_benefit "
        "FROM calculation_run WHERE calculation_run_id = ?", (run_id,)
    ).fetchone()[:] == (1, 10, 5)
    assert tuple(db.execute(
        "SELECT used_count, used_amount, linked_amount, releasable_count, releasable_amount, "
        "unlinked_count, unlinked_amount FROM coupon_fee_summary WHERE calculation_run_id = ?",
        (run_id,),
    ).fetchone()) == (2, 8, 5, 1, 5, 1, 3)
    db.close()
