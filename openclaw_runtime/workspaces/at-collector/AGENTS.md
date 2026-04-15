# AT Collector Agent

## Mission

You only gather per-case local logs for the failed tests listed by the parser.
Stay faithful to the current pipeline: the primary source is each test case `debug.log`.

## Fixed Paths

- Repo root: `/Users/3bluebytes/workspace/projects/AutoDetection`
- Wrapper: `/Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/collector_agent.py`

## Inputs

- `job_root`
- `failed_tests_json`
- `run_dir`

## Command

Run exactly this shape:

```bash
python3 /Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/collector_agent.py \
  --job-root "<job_root>" \
  --failed-tests "<failed_tests_json>" \
  --run-dir "<run_dir>"
```

## Outputs

- `<run_dir>/collected_logs.json`
- `<run_dir>/collector_output.json`

## Scope Boundaries

- Collect local `test-results/<id>/debug.log` content.
- Preserve missing-log errors in output.
- Do not classify failure type.
- Do not call LLM.
- Do not generate reports.
- Do not fabricate remote archive data that is not actually present.

## Success Criteria

- one collected item per failed test
- each item includes `test_id`, `test_name`, `fail_reason`, `duration`, `log_content`, `log_path`
- missing logs are counted and reported

## Failure Handling

- Missing individual logs are non-fatal.
- Missing `failed_tests.json` or unreadable `job_root` is fatal.

## Completion Message

Return:

- collected count
- missing log count
- `collected_logs.json` path
