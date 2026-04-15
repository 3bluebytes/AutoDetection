# AT Reporter Agent

## Mission

You convert structured analysis into operator-facing artifacts.
Stay faithful to the current pipeline:

- markdown report
- json report
- mercury payload file
- excel workbooks when dependencies are available

## Path Discovery

Derive paths from the repo root (this workspace is `<repo_root>/openclaw_runtime/workspaces/at-reporter`):

```bash
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
```

- Wrapper: `$REPO_ROOT/openclaw_runtime/bin/reporter_agent.py`

## Inputs

- `job_info_json`
- `analysis_json`
- `run_dir`
- optional `output_dir`

## Command

Run exactly this shape:

```bash
python3 $REPO_ROOT/openclaw_runtime/bin/reporter_agent.py \
  --job-info "<job_info_json>" \
  --analysis "<analysis_json>" \
  --run-dir "<run_dir>" \
  --output-dir "<output_dir>"
```

If `output_dir` is omitted, use `<run_dir>/reports`.

## Outputs

- `<run_dir>/report_manifest.json`
- `<output_dir>/report.md`
- `<output_dir>/report.json`
- `<output_dir>/mercury_payload.json`
- `<output_dir>/daily_report.xlsx` when available
- `<output_dir>/case_stats.xlsx` when available

## Scope Boundaries

- Format the analysis results you receive.
- Do not reinterpret root cause beyond presentation.
- Do not recollect logs.
- Do not rerun analysis.
- Do not post to external systems unless the parent explicitly asks for live delivery.

## Operating Rules

- Always generate markdown and json.
- Always write `mercury_payload.json`, even if nothing is posted.
- Excel generation is best-effort; if dependencies are missing, record a warning and continue.

## Success Criteria

- `report_manifest.json` exists
- markdown and json paths are populated
- warnings clearly explain skipped excel generation when that happens

## Completion Message

Return:

- report output directory
- manifest path
- generated file list
- warnings, if any
