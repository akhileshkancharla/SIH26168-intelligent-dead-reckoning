#!/usr/bin/env python3
"""Fail the required gate unless every selected group actually succeeded."""
from __future__ import annotations

import json
import os

LANES = ("dataset", "python", "cpp", "android")


def validate(needs: dict) -> list[str]:
    errors = []
    if not isinstance(needs, dict):
        return ["Missing job results"]
    for job in ("changes", "policy", *LANES):
        if not isinstance(needs.get(job), dict):
            errors.append(f"Missing result: {job}")
    if errors:
        return errors
    for job in ("changes", "policy"):
        if needs[job].get("result") != "success":
            errors.append(f"{job} did not succeed")
    outputs = needs["changes"].get("outputs", {})
    if not isinstance(outputs, dict):
        return errors + ["Missing selector outputs"]
    for lane in LANES:
        flag = outputs.get(lane)
        result = needs[lane].get("result")
        if flag not in ("true", "false"):
            errors.append(f"Invalid selector output: {lane}")
        elif flag == "true" and result != "success":
            errors.append(f"Selected group {lane} did not succeed: {result}")
        elif flag == "false" and result not in ("skipped", "success"):
            errors.append(f"Unaffected group {lane} has an unexpected result: {result}")
    return errors


def main() -> int:
    try:
        needs = json.loads(os.environ["NEEDS_JSON"])
    except (KeyError, ValueError):
        print("FAIL: missing or malformed job results")
        return 1
    errors = validate(needs)
    for error in errors:
        print(f"FAIL: {error}")
    if not errors:
        print("PASS: policy and every selected test group succeeded")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
