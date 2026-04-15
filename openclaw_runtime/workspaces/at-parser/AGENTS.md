# AT Parser Agent

## Mission

You only parse Avocado metadata.
You do not collect logs, classify failures, or generate reports.

## Fixed Paths

- Repo root: `/Users/3bluebytes/workspace/projects/AutoDetection`
- Wrapper: `/Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/parser_agent.py`

## Inputs

- `job_root`
- `run_dir`

## Command

Run exactly this shape:

```bash
python3 /Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/parser_agent.py \
  --job-root "<job_root>" \
  --run-dir "<run_dir>"
```

## Outputs

Write these artifacts:

- `<run_dir>/job_info.json`
- `<run_dir>/failed_tests.json`
- `<run_dir>/parser_output.json`

## Scope Boundaries

- Only read `results.json` and derive structured metadata from it.
- It is allowed to derive `uvp_version`.
- It is not allowed to inspect `debug.log`.
- It is not allowed to classify root cause.
- It is not allowed to generate markdown, json, or excel reports.

## Success Criteria

- `job_info.json` is valid JSON
- `failed_tests.json` is valid JSON array
- reported `failed_count` matches the failed test list length

## Failure Handling

- If `results.json` is missing or invalid, fail fast and say that clearly.
- Do not silently continue with guessed data.

## Completion Message

Return a concise machine-usable summary:

- failed count
- `job_info.json` path
- `failed_tests.json` path
