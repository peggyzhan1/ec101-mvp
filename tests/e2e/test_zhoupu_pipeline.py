from hashlib import sha256
from pathlib import Path

from ec101.calculation.engine import calculate_batch
from ec101.contract.workbook import read_standard_workbook
from ec101.converters.zhoupu import convert_zhoupu
from ec101.db import connect_database, create_database
from ec101.importing.service import ArchiveMetadata, import_snapshot
from tests.fixtures.zhoupu_builder import build_zhoupu_request


def test_zhoupu_convert_import_calculate_pipeline_has_same_unlinked_coupon_behavior(tmp_path):
    conversion = convert_zhoupu(build_zhoupu_request(tmp_path))
    workbook = read_standard_workbook(conversion.workbook_path)
    database_path = tmp_path / "ec101.db"
    create_database(database_path)
    db = connect_database(database_path)
    archive = conversion.sources_zip_path.read_bytes()
    imported = import_snapshot(db, workbook, ArchiveMetadata(
        str(conversion.sources_zip_path), sha256(archive).hexdigest(), len(archive)
    ))

    run_id = calculate_batch(db, imported.import_batch_id, "2026-09-22")

    assert tuple(db.execute(
        "SELECT released_orders, released_activity_benefit, released_coupon_benefit "
        "FROM calculation_run WHERE calculation_run_id = ?", (run_id,)
    ).fetchone()) == (1, 10, 5)
    assert tuple(db.execute(
        "SELECT used_count, used_amount, linked_amount, releasable_count, releasable_amount, "
        "unlinked_count, unlinked_amount FROM coupon_fee_summary WHERE calculation_run_id = ?",
        (run_id,),
    ).fetchone()) == (2, 10, 5, 1, 5, 1, 5)
    unlinked = db.execute(
        "SELECT coupon_no, discount_amount FROM coupon_redemption WHERE order_id IS NULL"
    ).fetchone()
    assert tuple(unlinked) == ("ZP-CPN-2", 5)
    engine_source = Path(__file__).parents[2].joinpath("src/ec101/calculation/engine.py").read_text()
    assert "舟谱" not in engine_source
    db.close()
