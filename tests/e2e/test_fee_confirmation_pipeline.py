from decimal import Decimal
from pathlib import Path

from ec101.confirmation.master_data import (
    sync_master_data,
    upsert_platform_customer_identity,
)
from ec101.confirmation.queries import (
    get_confirmation_overview,
    list_confirmation_exceptions,
    list_confirmation_reconciliation,
)
from ec101.confirmation.recipients import FeeCycleInput, import_fee_recipients
from ec101.confirmation.surveys import import_survey_responses
from ec101.db import connect_database, create_database


ROOT = Path(__file__).parents[2]


def _customer(code: str) -> dict[str, str]:
    return {
        "sap_customer_primary_key": f"sap-{code}",
        "sap_customer_code": code,
        "sap_customer_name": f"客户{code}",
    }


def _mapping(platform_id: int, code: str, platform_no: str, sequence: int) -> dict:
    return {
        "source_mapping_id": f"mapping-{sequence}",
        "dealer_platform_id": platform_id,
        "source_customer_code": platform_no,
        "source_customer_name": f"平台客户{platform_no}",
        "sap_customer_code": code,
        "sap_customer_name": f"客户{code}",
        "match_status": "匹配成功",
    }


def _recipient(code: str, amount: int) -> dict[str, str]:
    return {
        "费用周期": "2026-09",
        "太古客户编号": code,
        "太古客户名称": f"客户{code}",
        "应发金额": str(amount),
        "备注": "协议费用",
    }


def _response(sequence: int, code: str, answer: str, submitted_at: str) -> dict[str, str]:
    return {
        "费用周期": "2026-09",
        "太古客户编号": code,
        "太古客户名称": f"客户{code}",
        "是否收到本期全部协议费用": answer,
        "未收到原因": "尚未到账" if answer == "尚未收到" else "",
        "补充说明": "",
        "答卷手机号": "13800000000",
        "提交时间": submitted_at,
        "问卷星原始序号": str(sequence),
    }


def test_customer_cycle_confirmation_pipeline_keeps_recipient_population_and_amounts(tmp_path):
    database_path = tmp_path / "fee-confirmation.db"
    create_database(database_path)
    db = connect_database(database_path)
    try:
        platform_id = db.execute(
            "INSERT INTO dealer_platform (dealer_name, platform_name) "
            "VALUES ('兴路强', '兴路强平台')"
        ).lastrowid
        identities = [
            ("A", "XA"),
            ("B", "XB"),
            ("C", "XC"),
            ("E", "XE1"),
            ("E", "XE2"),
        ]
        for _, platform_no in identities:
            upsert_platform_customer_identity(
                db, int(platform_id), platform_no, f"平台客户{platform_no}", "2026-10-01"
            )
        mappings = [
            _mapping(int(platform_id), code, platform_no, sequence)
            for sequence, (code, platform_no) in enumerate(identities, start=1)
        ]
        master = sync_master_data(
            db,
            "areapartner",
            [_customer(code) for code in "ABCDE"],
            mappings,
            "2026-10-01 09:00:00",
        )
        imported = import_fee_recipients(
            db,
            FeeCycleInput("2026-09", "2026年9月", "2026-09-01", "2026-09-30"),
            [_recipient(code, amount) for code, amount in zip("ABCDE", range(100, 600, 100))],
            master.master_sync_batch_id,
            "2026-10-01 10:00:00",
        )
        assert (imported.recipient_count, imported.matched_count) == (5, 3)
        assert (imported.unmatched_count, imported.ambiguous_count) == (1, 1)

        import_survey_responses(
            db,
            "2026-09",
            "survey.xlsx",
            "survey-hash",
            [
                _response(1, "A", "已收到", "2026-10-09 10:00:00"),
                _response(2, "B", "尚未收到", "2026-10-09 11:00:00"),
                _response(3, "D", "已收到", "2026-10-09 12:00:00"),
                _response(4, "E", "尚未收到", "2026-10-09 13:00:00"),
                _response(5, "E", "已收到", "2026-10-09 14:00:00"),
                _response(6, "X", "已收到", "2026-10-09 15:00:00"),
            ],
            "2026-10-10 09:00:00",
        )

        reconciliation = list_confirmation_reconciliation(db, "2026-09", None, "", 100, 0)
        by_code = {item["sapCustomerCode"]: item for item in reconciliation["items"]}
        assert reconciliation["total"] == 5
        assert {code: item["confirmationStatus"] for code, item in by_code.items()} == {
            "A": "已确认收到",
            "B": "确认未收到",
            "C": "未提交",
            "D": "已确认收到",
            "E": "答卷冲突",
        }
        assert {code: Decimal(str(item["expectedAmount"])) for code, item in by_code.items()} == {
            code: Decimal(str(amount)) for code, amount in zip("ABCDE", range(100, 600, 100))
        }

        overview = get_confirmation_overview(db, "2026-09")
        assert overview["recipient"] == {"customerCount": 5, "expectedAmount": 1500}
        assert overview["outsideListResponseCount"] == 1
        exceptions = list_confirmation_exceptions(db, "2026-09", None, 100, 0)
        assert {item["kind"] for item in exceptions["items"]} >= {
            "outside_list",
            "conflict",
            "unmatched_mapping",
            "ambiguous_mapping",
        }

        survey_columns = {row["name"] for row in db.execute("PRAGMA table_info(survey_response)")}
        assert survey_columns.isdisjoint({
            "fee_recipient_id",
            "third_party_order_no",
            "sales_document_no",
            "coupon_no",
            "voucher_no",
            "expected_amount",
        })
    finally:
        db.close()


def test_fee_confirmation_contract_is_documented():
    dictionary = (ROOT / "docs" / "数据库字典.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs" / "标准数据契约.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert all(name in dictionary for name in (
        "master_sync_batch",
        "taikoo_customer_snapshot",
        "platform_customer_identity",
        "customer_mapping_snapshot",
        "fee_cycle",
        "fee_recipient",
        "fee_cycle_activity",
        "survey_import_batch",
        "survey_response",
        "v_effective_survey_response",
        "v_fee_confirmation_reconciliation",
    ))
    assert "费用周期 | 太古客户编号 | 太古客户名称 | 应发金额 | 备注" in contract
    assert "是否收到本期全部协议费用" in contract
    assert "客资快照 → 应发名单 → 问卷答卷 → 对账" in readme
    assert "手机号" in readme and "不得提交" in readme
