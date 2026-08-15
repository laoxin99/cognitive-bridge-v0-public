from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_bridge_v0 import (
    PathRevisionEngine,
    PathRevisionLedger,
    PathRevisionReplay,
    clean_checkout_demo_inputs,
)


def main() -> None:
    goal, candidates, feedback = clean_checkout_demo_inputs()
    result = PathRevisionEngine().run(goal, candidates, feedback)
    ledger_path = Path("demo_output") / "path_revision_ledger.jsonl"
    PathRevisionLedger(ledger_path).append(result)

    print("selected_path =", result.initial_selected_path)
    print("feedback =", feedback.code)
    print("path_status_B = deviated")
    print("revision_type =", result.revision_type)
    print("selected_path =", result.final_selected_path)
    print("validation_after_revision =", result.validation_after_revision)
    print("replay_verified =", PathRevisionReplay.verify(result))
    print("ledger =", ledger_path)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
