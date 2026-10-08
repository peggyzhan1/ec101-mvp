from email.parser import BytesParser
from email.policy import default
import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Optional
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from ec101.calculation.engine import calculate_batch
from ec101.contract.workbook import read_standard_workbook
from ec101.db import connect_database, create_database
from ec101.importing.service import ArchiveMetadata, ImportValidationError, import_snapshot
from ec101.reporting.roi import query_roi
from ec101.reporting.verification import build_verification_workbook

from .queries import (
    get_fee_overview,
    get_import,
    list_activity_summaries,
    list_business_rows,
    list_coupon_summaries,
    list_fee_issues,
    list_imports,
    list_release_candidates,
    list_unlinked_coupons,
)


def _integer(query, name, default):
    value = query.get(name, [default])[0]
    return int(value) if value not in (None, "") else default


def _optional_run(query) -> Optional[int]:
    value = query.get("calculationRunId", [None])[0]
    return int(value) if value not in (None, "") else None


def create_handler(db_path: Path, archive_dir: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_workbook(self, content):
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Disposition", "attachment; filename=verification.xlsx")
            self.end_headers()
            self.wfile.write(content)

        def _query(self):
            parsed = urlparse(self.path)
            return parsed.path, parse_qs(parsed.query)

        def do_GET(self):
            path, query = self._query()
            if path == "/health":
                self._send(200, {"status": "ok"})
                return
            verification = re.fullmatch(r"/api/verification/(\d+)", path)
            if verification:
                temporary_path = None
                db = connect_database(db_path)
                try:
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    with NamedTemporaryFile(dir=archive_dir, suffix=".xlsx", delete=False) as temporary:
                        temporary_path = Path(temporary.name)
                    build_verification_workbook(db, int(verification.group(1)), temporary_path)
                    self._send_workbook(temporary_path.read_bytes())
                except LookupError as exc:
                    self._send(404, {"error": str(exc)})
                finally:
                    db.close()
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)
                return
            db = connect_database(db_path)
            try:
                payload = self._dispatch_get(db, path, query)
                self._send(200, payload)
            except LookupError as exc:
                self._send(404, {"error": str(exc)})
            except (TypeError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
            finally:
                db.close()

        def _dispatch_get(self, db, path, query):
            limit = _integer(query, "limit", 100)
            offset = _integer(query, "offset", 0)
            if path == "/api/imports":
                return list_imports(db)
            match = re.fullmatch(r"/api/imports/(\d+)", path)
            if match:
                return get_import(db, int(match.group(1)))
            match = re.fullmatch(r"/api/imports/(\d+)/issues", path)
            if match:
                rows = db.execute(
                    "SELECT code, sheet_name AS sheetName, row_number AS rowNumber, "
                    "column_name AS columnName, message FROM import_validation_issue "
                    "WHERE import_batch_id = ? ORDER BY issue_id",
                    (int(match.group(1)),),
                ).fetchall()
                return {"items": [dict(row) for row in rows], "total": len(rows)}
            match = re.fullmatch(r"/api/imports/(\d+)/release", path)
            if match:
                candidate_value = query.get("candidate", [None])[0]
                candidate = None if candidate_value is None else candidate_value.lower() == "true"
                return list_release_candidates(
                    db, int(match.group(1)), candidate, query.get("query", [""])[0], limit, offset
                )
            match = re.fullmatch(r"/api/business/([a-z]+)", path)
            if match:
                return list_business_rows(
                    db, match.group(1), query.get("dealer", [None])[0],
                    query.get("platform", [None])[0], query.get("query", [""])[0], limit, offset,
                )
            run_id = _optional_run(query)
            if path == "/api/fee-tpm/overview":
                return get_fee_overview(db, run_id)
            if path == "/api/fee-tpm/activities":
                return list_activity_summaries(db, run_id, limit, offset)
            if path == "/api/fee-tpm/issues":
                return list_fee_issues(db, run_id, limit, offset)
            if path == "/api/fee-tpm/coupons":
                return list_coupon_summaries(db, run_id, limit, offset)
            if path == "/api/fee-tpm/coupons/unlinked":
                return list_unlinked_coupons(db, run_id, limit, offset)
            if path == "/api/fee-tpm/settlements":
                return {
                    "activities": list_activity_summaries(db, run_id, limit, offset),
                    "coupons": list_coupon_summaries(db, run_id, limit, offset),
                }
            if path == "/api/roi":
                return {"items": query_roi(db, run_id)}
            raise LookupError(f"接口 {path} 不存在")

        def do_POST(self):
            path, _ = self._query()
            if path != "/api/imports":
                self._send(404, {"error": f"接口 {path} 不存在"})
                return
            archive_path = None
            workbook_path = None
            try:
                fields, files = self._multipart()
                if "standard" not in files or "sources" not in files:
                    raise ValueError("必须同时上传 standard 和 sources")
                archive_dir.mkdir(parents=True, exist_ok=True)
                source_content = files["sources"][1]
                archive_path = archive_dir / f"{uuid4().hex}-sources.zip"
                archive_path.write_bytes(source_content)
                with NamedTemporaryFile(dir=archive_dir, suffix=".xlsx", delete=False) as temporary:
                    temporary.write(files["standard"][1])
                    workbook_path = Path(temporary.name)
                workbook = read_standard_workbook(workbook_path)
                db = connect_database(db_path)
                try:
                    imported = import_snapshot(db, workbook, ArchiveMetadata(
                        str(archive_path), sha256(source_content).hexdigest(), len(source_content)
                    ))
                    run_id = calculate_batch(db, imported.import_batch_id, fields.get("calcDate") or None)
                finally:
                    db.close()
                self._send(201, {
                    "importBatchId": imported.import_batch_id,
                    "calculationRunId": run_id,
                    "status": "calculated",
                    "archive": {
                        "filePath": str(archive_path),
                        "sha256": sha256(source_content).hexdigest(),
                        "fileSize": len(source_content),
                    },
                })
            except ImportValidationError as exc:
                self._send(422, {"error": str(exc), "issues": [issue.__dict__ for issue in exc.issues]})
            except (KeyError, TypeError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
            finally:
                if workbook_path is not None:
                    workbook_path.unlink(missing_ok=True)

        def _multipart(self):
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                raise ValueError("Content-Type 必须是 multipart/form-data")
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
            )
            fields = {}
            files = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                content = part.get_payload(decode=True)
                if filename:
                    files[name] = (filename, content)
                else:
                    fields[name] = content.decode(part.get_content_charset() or "utf-8")
            return fields, files

    return Handler


def serve(host: str, port: int, db_path: Path, archive_dir: Path) -> None:
    if not db_path.exists():
        create_database(db_path)
    server = ThreadingHTTPServer((host, port), create_handler(db_path, archive_dir))
    server.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ec101-api")
    parser.add_argument("--db", type=Path, default=Path("ec101.db"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archives"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    serve(args.host, args.port, args.db, args.archive_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
