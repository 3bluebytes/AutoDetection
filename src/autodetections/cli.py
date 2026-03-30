from __future__ import annotations

import argparse
import json
from pathlib import Path

from autodetections.config import load_config
from autodetections.orchestrator import AutoDetectionAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Virtualization AT root-cause triage agent")
    parser.add_argument("--config", required=True, help="Path to the agent JSON config")
    parser.add_argument("--job-root", help="Override Avocado job root")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.job_root:
        config.job_root = str(Path(args.job_root).resolve())

    result = AutoDetectionAgent(config).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
