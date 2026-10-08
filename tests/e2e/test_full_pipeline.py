from ec101.calculation.engine import calculate_batch
from ec101.contract.workbook import read_standard_workbook
from ec101.db import connect_database, create_database
from ec101.importing.service import ArchiveMetadata, import_snapshot
from ec101.api.queries import get_fee_overview, list_coupon_summaries, list_unlinked_coupons
from ec101.converters.kuaima import convert_kuaima
from ec101.converters.zhoupu import convert_zhoupu
from tests.fixtures.kuaima_builder import build_kuaima_request
from tests.fixtures.zhoupu_builder import build_zhoupu_request


def _run(db_path, result):
    db = connect_database(db_path)
    try:
        imported = import_snapshot(db, read_standard_workbook(result.workbook_path), ArchiveMetadata(str(result.sources_zip_path), "test", 1))
        run_id = calculate_batch(db, imported.import_batch_id, "2026-10-08")
        return get_fee_overview(db, run_id), list_coupon_summaries(db, run_id, 100, 0), list_unlinked_coupons(db, run_id, 100, 0)
    finally:
        db.close()


def test_synthetic_platforms_convert_import_and_calculate(tmp_path):
    db_path = tmp_path / "ec101.db"
    create_database(db_path)
    kuaima_dir, zhoupu_dir = tmp_path / "kuaima", tmp_path / "zhoupu"
    kuaima_dir.mkdir()
    zhoupu_dir.mkdir()
    kuaima = _run(db_path, convert_kuaima(build_kuaima_request(kuaima_dir)))
    zhoupu = _run(db_path, convert_zhoupu(build_zhoupu_request(zhoupu_dir)))

    assert kuaima[0]["totalBenefit"] > 0
    assert zhoupu[0]["totalBenefit"] > 0
    assert kuaima[1]["items"][0]["unlinkedCount"] == 1
    assert kuaima[2]["items"][0]["couponNo"] == "CP2"
    assert "theoretical" not in str(kuaima).lower()
