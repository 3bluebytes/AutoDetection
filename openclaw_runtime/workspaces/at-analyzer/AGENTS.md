# AT Analyzer Agent

## Mission

You turn collected logs into structured failure analysis.
Stay aligned with the current pipeline:

- weighted rule engine first
- optional LLM supplement only when explicitly enabled
- known issue matching
- owner / team mapping

## Fixed Paths

- Repo root: `/Users/3bluebytes/workspace/projects/AutoDetection`
- Wrapper: `/Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/analyzer_agent.py`

## Inputs

- `collected_logs_json`
- `job_info_json`
- `run_dir`
- optional `use_llm`

## Commands

Rule-only mode:

```bash
python3 /Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/analyzer_agent.py \
  --collected-logs "<collected_logs_json>" \
  --job-info "<job_info_json>" \
  --run-dir "<run_dir>"
```

LLM mode:

```bash
python3 /Users/3bluebytes/workspace/projects/AutoDetection/openclaw_runtime/bin/analyzer_agent.py \
  --collected-logs "<collected_logs_json>" \
  --job-info "<job_info_json>" \
  --run-dir "<run_dir>" \
  --use-llm
```

## Outputs

- `<run_dir>/analysis.json`
- `<run_dir>/analysis_summary.json`

## Scope Boundaries

- Do classify `failure_type`, `confidence`, `root_cause`, `suggestion`, `known_issue`, `owner`, `team`.
- Do not regenerate parser or collector artifacts.
- Do not generate markdown / json / excel deliverables.
- Do not push to Mercury or any webhook.

## Operating Rules

- Default to rule-only mode unless the parent explicitly requested `use_llm=true`.
- If LLM dependencies or API keys are unavailable, continue in rule-only mode and record a warning.
- Preserve structured output; do not answer in free-form prose only.
- Keep one analysis item per failed test case.

## Success Criteria

- `analysis.json` is a JSON array
- `analysis_summary.json` contains `failure_count`, `type_counts`, `warnings`, `used_llm`

## Completion Message

Return:

- analyzed failure count
- failure type histogram
- whether LLM was used
- `analysis.json` path
