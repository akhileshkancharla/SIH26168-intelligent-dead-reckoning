#!/usr/bin/env python3
"""Conservative CI selection from the complete, pinned PR merge tree diff."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

LANES = ("dataset", "python", "cpp", "android")
ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")


def full_plan(reason: str) -> dict:
    return {"selected": dict.fromkeys(LANES, True), "reason": reason}


def select_paths(paths: list[str]) -> dict:
    selected = dict.fromkeys(LANES, False)
    if not paths:
        return full_plan("Empty diff: full validation")
    for path in paths:
        parts = PurePosixPath(path).parts
        if (not parts or path.startswith("/") or "\\" in path
                or any(part in (".", "..") for part in path.split("/"))
                or ":" in path or any(ord(char) < 32 for char in path)):
            return full_plan("Unrecognized path: full validation")
        # These artifacts are covered by the always-running policy group.
        if path.startswith("docs/architecture/dependency-graph/"):
            continue
        if path == "docs/bootstrap/repository_manifest.json":
            continue
        # Architecture is governing input, including Markdown and machine data.
        if path.startswith("docs/architecture/"):
            return full_plan("Architecture changed")
        if path.startswith("docs/") and path.endswith(".md"):
            continue
        if path in {"README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md"}:
            continue
        if path == "tools/bootstrap/generate_repository.py":
            return full_plan("Repository generator changed")
        if path.startswith("tools/dataset/"):
            selected["dataset"] = True
        elif path.startswith(("tools/bootstrap/", "tools/acquisition/")):
            selected["python"] = True
        elif path.startswith("android/"):
            # JVM/resources/manifests/JNI and placed bindings can affect consumers.
            for lane in ("android", "cpp", "python"):
                selected[lane] = True
        elif path.startswith("core/") or path == "CMakeLists.txt":
            for lane in ("cpp", "android", "python"):
                selected[lane] = True
        else:
            # Includes CI, shared contracts/fixtures/bindings, package metadata,
            # new modules and configuration. Never infer independence from Graphify.
            return full_plan("Shared or unclassified input changed")
    return {"selected": selected, "reason": "Complete PR diff classified"}


def git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True,
    ).stdout


def plan_for_event(event_name: str, event: dict, checkout_sha: str, root: Path = ROOT) -> dict:
    if event_name != "pull_request":
        return full_plan("Push or manual run: full validation")
    try:
        base = event["pull_request"]["base"]["sha"]
        head = event["pull_request"]["head"]["sha"]
        if not all(isinstance(value, str) and SHA.fullmatch(value) for value in (base, head, checkout_sha)):
            return full_plan("Missing or invalid comparison identity")
        actual = git(root, "rev-parse", "HEAD").decode("ascii").strip()
        parents = git(root, "show", "-s", "--format=%P", "HEAD").decode("ascii").split()
        if actual != checkout_sha or parents != [base, head]:
            return full_plan("Checkout is not the expected PR merge commit")
        # --no-renames deliberately emits both the deleted and added path of a
        # rename. NUL separation avoids quoting, whitespace and 300-file API limits.
        changed = git(root, "diff", "--no-ext-diff", "--name-only", "-z", "--no-renames", base, actual, "--")
        paths = [value.decode("utf-8", errors="strict") for value in changed.split(b"\0") if value]
        return select_paths(paths)
    except (KeyError, TypeError, ValueError, UnicodeError, OSError, subprocess.CalledProcessError):
        return full_plan("Comparison unavailable: full validation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="+", help="Preview selection locally without GitHub")
    args = parser.parse_args()
    if args.paths is not None:
        plan = select_paths(args.paths)
    else:
        try:
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8-sig"))
        except (KeyError, OSError, ValueError):
            event = {}
        plan = plan_for_event(os.getenv("GITHUB_EVENT_NAME", ""), event, os.getenv("GITHUB_SHA", ""))
    print(json.dumps(plan, indent=2))
    if output := os.getenv("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8", newline="\n") as stream:
            for lane, selected in plan["selected"].items():
                stream.write(f"{lane}={str(selected).lower()}\n")
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8", newline="\n") as stream:
            stream.write("## CI selection\n\n" + plan["reason"] + "\n\nPolicy: always\n\n")
            for lane, selected in plan["selected"].items():
                stream.write(f"- {lane}: {'run' if selected else 'unaffected'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
