from __future__ import annotations

import json
from pathlib import Path

from autodetections.models import CaseResult, JobRun
from autodetections.utils import first_present, safe_read_text, slugify


class AvocadoResultLoader:
    """Loads standard Avocado job-results trees into normalized models."""

    def load(self, job_root: str, build_id: str = "", date: str = "", host: str = "") -> JobRun:
        root = Path(job_root).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Job root does not exist: {root}")

        cases = self._load_from_results_json(root)
        if not cases:
            cases = self._load_from_test_dirs(root)

        return JobRun(
            job_id=root.name,
            root_path=str(root),
            build_id=build_id,
            date=date,
            host=host,
            cases=cases,
            metadata={"job_root": str(root)},
        )

    def _load_from_results_json(self, root: Path) -> list[CaseResult]:
        results_path = root / "results.json"
        if not results_path.exists():
            return []

        payload = json.loads(safe_read_text(results_path))
        raw_items: list[dict] = []
        if isinstance(payload, list):
            raw_items = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            for key in ("tests", "results", "items"):
                items = payload.get(key)
                if isinstance(items, list):
                    raw_items = [item for item in items if isinstance(item, dict)]
                    if raw_items:
                        break

        cases: list[CaseResult] = []
        for index, item in enumerate(raw_items, start=1):
            name = first_present(item, ("name", "test_name", "test", "id"), f"case_{index}")
            case_id = first_present(item, ("id", "test_id"), "")
            if not case_id:
                case_id = f"{index}-{slugify(name)}"
            status = first_present(item, ("status", "result", "state"), "UNKNOWN").upper()
            duration_raw = first_present(item, ("duration", "time_elapsed", "elapsed"), "")
            try:
                duration = float(duration_raw) if duration_raw else None
            except ValueError:
                duration = None
            log_dir_raw = first_present(item, ("logdir", "log_dir", "workdir"), "")
            log_dir = str((root / log_dir_raw).resolve()) if log_dir_raw and not Path(log_dir_raw).is_absolute() else log_dir_raw
            cases.append(
                CaseResult(
                    case_id=case_id,
                    name=name,
                    status=status,
                    duration_seconds=duration,
                    log_dir=log_dir,
                    metadata=item,
                )
            )
        return cases

    def _load_from_test_dirs(self, root: Path) -> list[CaseResult]:
        test_results_dir = root / "test-results"
        if not test_results_dir.exists():
            return []

        cases: list[CaseResult] = []
        for child in sorted(test_results_dir.iterdir()):
            if not child.is_dir():
                continue
            status = self._read_status(child)
            case_name = self._guess_case_name(child.name)
            cases.append(
                CaseResult(
                    case_id=child.name,
                    name=case_name,
                    status=status,
                    log_dir=str(child.resolve()),
                    metadata={"source": "test-results"},
                )
            )
        return cases

    def _read_status(self, case_dir: Path) -> str:
        status_json = case_dir / "status.json"
        if status_json.exists():
            payload = json.loads(safe_read_text(status_json))
            if isinstance(payload, dict):
                return first_present(payload, ("status", "result", "state"), "UNKNOWN").upper()

        status_path = case_dir / "status"
        if status_path.exists():
            line = safe_read_text(status_path, limit=128).splitlines()
            if line:
                head = line[0].split()[0]
                return head.upper()
        return "UNKNOWN"

    def _guess_case_name(self, directory_name: str) -> str:
        if "-" in directory_name:
            parts = directory_name.split("-", 1)
            if len(parts) == 2 and parts[1]:
                return parts[1]
        return directory_name

