from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from trading_logic import build_decision


OUTPUT_PATH = Path("data.json")


def load_previous_data() -> dict | None:
    if not OUTPUT_PATH.exists():
        return None

    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


def determine_change(
    prev_scenario: str | None,
    prev_action: str | None,
    current_scenario: str,
    current_action: str,
) -> str:
    if prev_scenario is None and prev_action is None:
        return "NO_CHANGE"

    if prev_scenario != current_scenario:
        return "SCENARIO_CHANGED"

    if prev_action != current_action:
        return "ACTION_CHANGED"

    return "NO_CHANGE"


def main() -> None:
    previous = load_previous_data()
    decision = build_decision()
    payload = asdict(decision)

    prev_scenario = previous.get("scenario") if previous else None
    prev_action = previous.get("action") if previous else None

    payload["prev_scenario"] = prev_scenario
    payload["prev_action"] = prev_action
    payload["change"] = determine_change(
        prev_scenario=prev_scenario,
        prev_action=prev_action,
        current_scenario=decision.scenario,
        current_action=decision.action,
    )

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
