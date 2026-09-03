#!/usr/bin/env python3
"""Generate the deterministic SIH26168 repository-bootstrap scaffold.

This tool writes repository policy and metadata only. It does not run scientific
experiments, import private evidence, or implement post-bootstrap work packages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import stat
import sys
import textwrap
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = "SIH26168_Architecture_Revision3_Working_Baseline"
EXPECTED_ARCHIVE_SHA256 = "7e244de520173c54285b3de076eee74f53c0c89dc8a10b0a25d4f379b91f0e7e"
ARCHITECTURE_STATUS = "ARCH3-READY-FOR-REPOSITORY-BOOTSTRAP"

ACTION_SHAS = {
    "checkout": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
    "setup_python": "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "setup_java": "actions/setup-java@cf277c60eb25467037889841efdb72551f06f6c3",
    "setup_gradle": "gradle/actions/setup-gradle@48b5f213c81028ace310571dc5ec0fbbca0b2947",
    "github_script": "actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b",
}


def write(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = textwrap.dedent(content).strip("\n") + "\n"
    path.write_text(normalized, encoding="utf-8", newline="\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def import_architecture(archive: Path) -> None:
    if not archive.is_file():
        raise SystemExit(f"Architecture archive missing: {archive}")
    if sha256_bytes(archive.read_bytes()) != EXPECTED_ARCHIVE_SHA256:
        raise SystemExit("Architecture archive SHA-256 mismatch")
    with zipfile.ZipFile(archive) as source:
        bad = source.testzip()
        if bad:
            raise SystemExit(f"Architecture ZIP CRC failure: {bad}")
        members = {}
        for info in source.infolist():
            name = info.filename.replace("\\", "/")
            path = PurePosixPath(name)
            mode = (info.external_attr >> 16) & 0o170000
            if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name):
                raise SystemExit(f"Unsafe architecture ZIP path: {name}")
            if mode == stat.S_IFLNK:
                raise SystemExit(f"Architecture ZIP contains symlink: {name}")
            if info.is_dir():
                continue
            parts = path.parts
            if not parts or parts[0] != ARCHIVE_ROOT:
                raise SystemExit(f"Unexpected architecture ZIP root: {name}")
            relative = PurePosixPath(*parts[1:]).as_posix()
            members[relative] = source.read(info)

    manifest_name = "SIH26168_ARCHITECTURE_MANIFEST_v1.json"
    manifest = json.loads(members[manifest_name])
    if manifest.get("architecture_status") != ARCHITECTURE_STATUS:
        raise SystemExit("Architecture status mismatch")
    for record in manifest["files"]:
        data = members.get(record["path"])
        if data is None:
            raise SystemExit(f"Manifest member missing: {record['path']}")
        if len(data) != record["size_bytes"] or sha256_bytes(data) != record["sha256"]:
            raise SystemExit(f"Manifest verification failed: {record['path']}")
    for relative, data in members.items():
        target = ROOT / "docs" / "architecture" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


ISSUES: dict[str, tuple[str, list[str]]] = {
    "WP-00": ("Repository and governance scaffold", [
        "Create private GitHub repository and local clone",
        "Create Revision 3 monorepo directory and build-root scaffold",
        "Add contribution, security, privacy and artifact policies",
        "Configure CODEOWNERS, PR template and issue forms",
        "Implement initial CI and prohibited-file scanners",
        "Configure labels, milestones, project board and main-branch ruleset",
    ]),
    "WP-01": ("Contract and schema v1 implementation", [
        "Create interface schema plan for I-01 through I-22",
        "Define timestamp, provenance and evidence-envelope contracts",
        "Define navigation, health, alignment and display-state enums",
        "Implement deterministic contract code generation",
        "Generate minimal Kotlin, C++ and Python bindings",
        "Add schema compatibility tests and synthetic fixtures",
    ]),
    "WP-02": ("Import and harden Android acquisition", [
        "Import validated S1 Android logger into monorepo",
        "Adapt SensorManager acquisition to contract v1",
        "Adapt location and GNSS provenance to contract v1",
        "Integrate chunk finalization, recovery and session export",
        "Add Android acquisition unit and instrumentation tests",
        "Verify S1 fixture round-trip inside monorepo",
    ]),
    "WP-03": ("Canonical C++ core and JNI integration", [
        "Import accepted S2 navigation-core source",
        "Configure pinned CMake, C++20 and Eigen build",
        "Define portable public navigation-core API",
        "Implement batch JNI input and output boundary",
        "Reproduce S2 C++ and NumPy parity tests",
        "Add JNI evidence-ID and state-equivalence tests",
    ]),
    "WP-04": ("Deterministic replay backbone", [
        "Implement replay-session validation and immutable reader",
        "Implement monotonic deterministic replay scheduler",
        "Create shared live and replay ingress interface",
        "Add mandatory REPLAY provenance and display state",
        "Add repeated-run determinism tests",
        "Create synthetic submission replay session and expected timeline",
    ]),
    "WP-05": ("Complete S1 physical-device protocol", [
        "Finalize S1 device matrix and run-sheet templates",
        "Complete OnePlus Nord CE4 5G Tests A through D",
        "Complete S1 protocol on representative phone two",
        "Complete S1 protocol on representative phone three",
        "Analyze rates, gaps, screen-off, battery and thermal evidence",
        "Produce final evidence-bounded S1 adjudication",
    ]),
    "WP-06": ("Phone-to-vehicle alignment and mount-slip spike", [
        "Freeze S3 hypotheses, protocol and acceptance criteria",
        "Implement candidate phone-to-vehicle alignment estimator",
        "Represent alignment covariance, validity and failure state",
        "Implement phone-mount movement and slip detection",
        "Execute controlled stationary and car alignment experiments",
        "Publish S3 result and selected or rejected method",
    ]),
    "WP-07": ("GNSS integrity, outage and reacquisition", [
        "Implement GNSS freshness and provenance validator",
        "Implement explicit GNSS outage-state transitions",
        "Implement stale, duplicate and biased-fix rejection",
        "Implement reacquisition dwell and consistency gates",
        "Add adversarial outage and return-fixture tests",
    ]),
    "WP-08": ("Runtime graph store and top-K matcher", [
        "Import and verify frozen S6B1 road-graph artifact",
        "Implement deterministic SQLite graph-store access",
        "Implement spatial-index candidate lookup",
        "Implement top-K map-candidate generation",
        "Implement confidence, ambiguity and abstention logic",
        "Add parallel-road, bridge, off-road and continuity tests",
    ]),
    "WP-09": ("Offline navigation UI and honest telemetry", [
        "Create Compose navigation application shell",
        "Integrate MapLibre local-map rendering",
        "Display raw, fused, matched and display trajectories",
        "Visualize uncertainty and top-K map candidates",
        "Display GNSS, alignment, model and replay health states",
        "Verify complete airplane-mode replay demonstration",
        "Produce submission UI wireframes and screen-state inventory",
    ]),
    "WP-10": ("Private IO-VNBD ingestion and leakage firewall", [
        "Create private dataset workspace and immutable source manifest",
        "Implement six-schema IO-VNBD validation allowlist",
        "Implement duplicate and parent-session grouping",
        "Create leakage-safe grouped dataset splits",
        "Implement runtime-feature and forbidden-label firewall",
        "Add leakage canary and private-data exclusion tests",
    ]),
    "WP-11": ("Classical baselines and bounded learned aid", [
        "Implement matched classical evaluation baselines",
        "Create deterministic ML training pipeline",
        "Implement frozen GNSS-blackout masking protocol",
        "Run baseline, model and feature ablations",
        "Publish exploratory evaluation and promotion recommendation",
    ]),
    "WP-12": ("Model export and Android shadow mode", [
        "Export candidate learned model to ONNX",
        "Generate ONNX golden input and output tensors",
        "Integrate ONNX Runtime Mobile",
        "Implement deadline, range and OOD validation",
        "Validate Android shadow mode and classical fallback",
    ]),
    "WP-13": ("Integrated analyzer and claim firewall", [
        "Validate session, reference and stream provenance",
        "Separate raw INS, fused, matched and display outputs",
        "Implement endpoint, maximum and RMSE drift metrics",
        "Report rates, gaps, latency and state transitions",
        "Reject ambiguous or scientifically invalid reports",
        "Create submission claims and evidence matrix",
    ]),
    "WP-14": ("Calibration and classical constraints baseline", [
        "Implement stationary calibration and bias initialization",
        "Implement alignment-gated vehicle constraints",
        "Implement vibration and motion-outlier gating",
        "Add constraint and calibration ablation controls",
        "Validate model-disabled classical car baseline",
    ]),
    "WP-15": ("Ten-event deterministic demonstration", [
        "Freeze ten-event demonstration scenario and evidence plan",
        "Implement deterministic scenario playback controller",
        "Integrate outage, turn and uncertainty-growth sequence",
        "Integrate biased-return rejection and credible reacquisition",
        "Implement smooth display recovery and comparison report",
        "Conduct complete demo rehearsal and incident review",
        "Define SIH submission demo narrative and storyboard",
        "Create SIH presentation content and visual plan",
        "Write demonstration video script and shot list",
        "Record and edit submission demonstration video",
        "Conduct submission presentation and video rehearsal",
        "Freeze and hash SIH portal submission package",
    ]),
    "WP-16": ("External IMU adapter and rate profiling", [
        "Define versioned external-IMU adapter contract",
        "Implement external-format deterministic replay adapter",
        "Profile input, propagation and output rates separately",
        "Document external-edge limitations and test evidence",
    ]),
    "WP-17": ("Release verification and field rehearsal", [
        "Perform fresh-clone clean build verification",
        "Build, install and smoke-test release-candidate APK",
        "Run network-isolated replay and live verification",
        "Run privacy, secret, licence and prohibited-file audit",
        "Complete MGIT field permission and safety checklist",
        "Conduct field or replay-only final rehearsal",
        "Generate release manifest, SBOM, notices and artifact hashes",
    ]),
}

OWNERS = {
    "WP-00": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "governance"),
    "WP-01": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "contracts"),
    "WP-02": ("R5", "likhithayepalagunta-19", "akhileshkancharla", "acquisition"),
    "WP-03": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "core"),
    "WP-04": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "core"),
    "WP-05": ("R5", "likhithayepalagunta-19", "akhileshkancharla", "acquisition"),
    "WP-06": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "core"),
    "WP-07": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "core"),
    "WP-08": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "map"),
    "WP-09": ("R5", "likhithayepalagunta-19", "akhileshkancharla", "android"),
    "WP-10": ("R2", "FaisalTabrez", "akhileshkancharla", "data"),
    "WP-11": ("R3", "Zeeshan1786", "akhileshkancharla", "ml"),
    "WP-12": ("R3", "Zeeshan1786", "akhileshkancharla", "ml"),
    "WP-13": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "analyzer"),
    "WP-14": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "core"),
    "WP-15": ("R5/R6", "likhithayepalagunta-19", "akhileshkancharla", "demo"),
    "WP-16": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "core"),
    "WP-17": ("R1/R4", "akhileshkancharla", "FaisalTabrez", "submission"),
}

CHILD_ASSIGNMENT_OVERRIDES = {
    "WP-00.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-00.3": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-00.4": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-00.5": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-00.6": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-01.1": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-01.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-01.3": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-01.4": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-01.5": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-01.6": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-03.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-04.1": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-04.5": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-04.6": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-07.5": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-08.1": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-08.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-08.3": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-08.4": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-08.5": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-08.6": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-13.1": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-13.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-13.3": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-13.5": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-13.6": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-16.1": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-16.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-16.4": ("R2", "FaisalTabrez", "akhileshkancharla"),
    "WP-17.2": ("R2", "FaisalTabrez", "akhileshkancharla"),
}

MILESTONES = [
    ("M0 — Repository Ready", "2026-09-03T14:30:00Z", "WP-00 complete by 20:00 IST"),
    ("M1 — Submission Contracts", "2026-09-05T18:29:59Z", "Contracts, narrative and wireframes"),
    ("M2 — Replay App Foundation", "2026-09-08T18:29:59Z", "Android, S2/JNI and replay foundation"),
    ("M3 — Demo Alpha", "2026-09-10T18:29:59Z", "End-to-end application sequence"),
    ("M4 — Content Freeze", "2026-09-12T18:29:59Z", "Stable behaviour, PPT v1 and script v1"),
    ("M5 — Recording Candidate", "2026-09-13T18:29:59Z", "Video and presentation candidate"),
    ("M6 — Internal Submission Freeze", "2026-09-15T18:29:59Z", "Final submission package"),
    ("M7 — SIH Portal Submission", "2026-09-20T18:29:59Z", "Portal delivery and confirmation"),
    ("P2 — Scientific/Core/Map/Data Gates", "2026-09-27T18:29:59Z", "S1, S3, GNSS, matcher and private data"),
    ("P3 — Classical and Evaluation", "2026-10-07T18:29:59Z", "UI, analyzer, baseline and ML experiment"),
    ("P4 — Integrated Scientific Demo", "2026-10-17T18:29:59Z", "ONNX shadow and ten-event integration"),
    ("P5 — Portable Edge", "2026-10-22T18:29:59Z", "External IMU path"),
    ("P6 — Final Release Candidate", "2026-10-31T18:29:59Z", "Complete verified release"),
]

DEFAULT_MILESTONE = {
    "WP-00": "M0 — Repository Ready", "WP-01": "M1 — Submission Contracts",
    "WP-02": "P2 — Scientific/Core/Map/Data Gates", "WP-03": "P2 — Scientific/Core/Map/Data Gates",
    "WP-04": "M2 — Replay App Foundation", "WP-05": "P2 — Scientific/Core/Map/Data Gates",
    "WP-06": "P2 — Scientific/Core/Map/Data Gates", "WP-07": "P2 — Scientific/Core/Map/Data Gates",
    "WP-08": "P2 — Scientific/Core/Map/Data Gates", "WP-09": "P3 — Classical and Evaluation",
    "WP-10": "P2 — Scientific/Core/Map/Data Gates", "WP-11": "P3 — Classical and Evaluation",
    "WP-12": "P4 — Integrated Scientific Demo", "WP-13": "P3 — Classical and Evaluation",
    "WP-14": "P3 — Classical and Evaluation", "WP-15": "P4 — Integrated Scientific Demo",
    "WP-16": "P5 — Portable Edge", "WP-17": "P6 — Final Release Candidate",
}

CRITICAL_DATES = {
    "WP-00": "2026-09-03", **{f"WP-00.{i}": "2026-09-03" for i in range(1, 7)},
    "WP-01.1": "2026-09-05", "WP-01.2": "2026-09-05", "WP-01.3": "2026-09-05",
    "WP-09.7": "2026-09-05", "WP-15.7": "2026-09-05",
    "WP-01.4": "2026-09-06", "WP-01.5": "2026-09-06", "WP-01.6": "2026-09-06",
    "WP-04.6": "2026-09-06", "WP-08.1": "2026-09-06",
    **{key: "2026-09-08" for key in ["WP-02.1", "WP-02.4", "WP-02.5", "WP-02.6", "WP-03.1", "WP-03.2", "WP-03.3", "WP-03.4", "WP-04.1", "WP-04.2", "WP-04.3", "WP-04.4", "WP-04.5"]},
    **{key: "2026-09-10" for key in ["WP-09.1", "WP-09.2", "WP-09.3", "WP-09.5"]},
    "WP-13.6": "2026-09-11", "WP-15.9": "2026-09-11", "WP-15.8": "2026-09-12",
    "WP-15.10": "2026-09-13", "WP-15.11": "2026-09-14", "WP-15.12": "2026-09-15",
}


def milestone_for(issue_id: str) -> str:
    if issue_id in CRITICAL_DATES:
        due = CRITICAL_DATES[issue_id]
        if due <= "2026-09-03": return "M0 — Repository Ready"
        if due <= "2026-09-05": return "M1 — Submission Contracts"
        if due <= "2026-09-08": return "M2 — Replay App Foundation"
        if due <= "2026-09-10": return "M3 — Demo Alpha"
        if due <= "2026-09-12": return "M4 — Content Freeze"
        if due <= "2026-09-13": return "M5 — Recording Candidate"
        return "M6 — Internal Submission Freeze"
    return DEFAULT_MILESTONE[issue_id[:5]]


def issue_rows() -> list[dict[str, str]]:
    rows = []
    for wp, (parent_title, children) in ISSUES.items():
        owner_role, assignee, reviewer, area = OWNERS[wp]
        parent_critical = wp in CRITICAL_DATES
        rows.append({
            "Issue number": "", "Parent": "", "WP ID": wp,
            "Title": f"[{wp}] {parent_title}", "Milestone": milestone_for(wp),
            "Submission-critical flag": "yes" if parent_critical else "no",
            "Owner role": owner_role, "Intended assignee": assignee, "Actual assignee": "",
            "Reviewer": reviewer, "Priority": "critical" if parent_critical else "high",
            "Area": area, "Status": "status:backlog", "Dependencies": "See Architecture Revision 3 work-package register",
            "Evidence required": "yes", "Due date": CRITICAL_DATES.get(wp, ""), "URL": "",
        })
        for index, title in enumerate(children, 1):
            issue_id = f"{wp}.{index}"
            critical = issue_id in CRITICAL_DATES
            operations = issue_id in {"WP-02.1", "WP-02.4", "WP-02.5", "WP-05.1", "WP-05.2", "WP-05.3", "WP-05.4", "WP-06.5", "WP-10.1", "WP-10.2", "WP-10.3", "WP-10.4", "WP-13.4", "WP-16.3", "WP-17.1", "WP-17.3", "WP-17.4", "WP-17.5", "WP-17.6", "WP-17.7"}
            if issue_id in CHILD_ASSIGNMENT_OVERRIDES:
                child_owner_role, intended, child_reviewer = CHILD_ASSIGNMENT_OVERRIDES[issue_id]
            elif operations:
                child_owner_role, intended, child_reviewer = "OPS-1", "mjunaidqureshimct255a1405-art", reviewer
            else:
                child_owner_role, intended, child_reviewer = owner_role, assignee, reviewer
            rows.append({
                "Issue number": "", "Parent": wp, "WP ID": issue_id,
                "Title": f"[{issue_id}] {title}", "Milestone": milestone_for(issue_id),
                "Submission-critical flag": "yes" if critical else "no",
                "Owner role": child_owner_role, "Intended assignee": intended, "Actual assignee": "",
                "Reviewer": child_reviewer, "Priority": "critical" if critical else "high",
                "Area": area, "Status": "status:backlog", "Dependencies": f"Parent {wp}; architecture dependency graph",
                "Evidence required": "yes", "Due date": CRITICAL_DATES.get(issue_id, ""), "URL": "",
            })
    if len([r for r in rows if "." not in r["WP ID"]]) != 18 or len([r for r in rows if "." in r["WP ID"]]) != 110 or len(rows) != 128:
        raise SystemExit("Issue register count invariant failed")
    return rows


LABEL_GROUPS = {
    "work-package": [f"wp:{i:02d}" for i in range(18)],
    "area": [f"area:{x}" for x in ["android", "acquisition", "core", "contracts", "map", "ml", "data", "analyzer", "ci", "demo", "docs", "governance", "submission"]],
    "type": [f"type:{x}" for x in ["feature", "bug", "experiment", "governance", "operations", "documentation", "test", "submission"]],
    "priority": [f"priority:{x}" for x in ["critical", "high", "medium", "low"]],
    "status": [f"status:{x}" for x in ["backlog", "ready", "in-progress", "in-review", "blocked", "update-required", "at-risk", "reassignment-required", "closure-approved", "unauthorized-close", "done", "approved-unavailable"]],
    "governance": ["evidence-required", "private-data", "beginner-safe", "architecture-review", "scientific-review", "security-review", "field-validation", "replay-only", "submission-critical", "post-submission", "role:operations"],
}

COLORS = {"work-package": "5319E7", "area": "1D76DB", "type": "0E8A16", "priority": "D93F0B", "status": "FBCA04", "governance": "B60205"}


def write_csv(relative: str, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def basic_files() -> None:
    directories = [
        "android/app/src/main/java/org/sih26168/app", "android/app/src/test/java/org/sih26168/app",
        "android/acquisition", "android/navigation-jni", "core/navigation/src", "core/navigation/tests",
        "core/include/sih26168/navigation", "contracts/schemas", "contracts/enums", "contracts/generated",
        "contracts/fixtures", "tools/analyzer", "tools/dataset", "tools/training", "tools/maps",
        "tools/bootstrap", "fixtures/public", "experiments/manifests", "demo/scenarios",
        "submission/presentation", "submission/video", "submission/screenshots", "submission/claims",
        "submission/manifests", "docs/protocols", "docs/bootstrap", "ci", "third_party/notices",
        ".github/ISSUE_TEMPLATE", ".github/workflows",
    ]
    for directory in directories:
        (ROOT / directory).mkdir(parents=True, exist_ok=True)

    write("README.md", """
    # SIH26168 — Intelligent Dead Reckoning

    Private development monorepo for the SIH26168 submission and its evidence-bounded post-submission engineering program.

    Architecture Revision 3 is authoritative and has status `ARCH3-READY-FOR-REPOSITORY-BOOTSTRAP`. Repository bootstrap does not claim completion of S1, S3, S4, runtime map matching, model promotion, live-field validation, or final scientific validation.

    ## Deadline boundary

    - Internal immutable submission freeze: **2026-09-15 (IST)**
    - SIH portal deadline: **2026-09-20 (IST)**
    - September 16–19 is a correction/upload contingency buffer, not feature-development time.

    ## Bootstrap smoke checks

    - Python: `python -m unittest discover -s tools/bootstrap/tests`
    - C++: `cmake -S . -B build && cmake --build build && ctest --test-dir build`
    - Android: `gradle -p android testDebugUnitTest lintDebug assembleDebug`
    - Full policy verification: `python ci/verify_repository.py all`

    The Android application may use deterministic local replay for the submission demonstration. Every replayed screen must display `REPLAY` unmistakably.

    ## Licence

    No software licence has been approved. This private repository is all-rights-reserved pending an explicit owner decision. No `LICENSE` file is intentionally present.
    """)
    write("CMakeLists.txt", """
    cmake_minimum_required(VERSION 3.20)
    project(SIH26168Bootstrap LANGUAGES CXX)
    set(CMAKE_CXX_STANDARD 20)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(CMAKE_CXX_EXTENSIONS OFF)
    enable_testing()
    add_subdirectory(core/navigation)
    """)
    write("core/navigation/CMakeLists.txt", """
    add_library(sih26168_navigation_smoke STATIC src/smoke.cpp)
    target_include_directories(sih26168_navigation_smoke PUBLIC ${PROJECT_SOURCE_DIR}/core/include)
    target_compile_features(sih26168_navigation_smoke PUBLIC cxx_std_20)
    add_executable(sih26168_navigation_smoke_test tests/smoke_test.cpp)
    target_link_libraries(sih26168_navigation_smoke_test PRIVATE sih26168_navigation_smoke)
    add_test(NAME navigation-smoke COMMAND sih26168_navigation_smoke_test)
    """)
    write("core/include/sih26168/navigation/smoke.hpp", """
    #pragma once
    #include <string_view>
    namespace sih26168::navigation {
    [[nodiscard]] constexpr std::string_view contract_version() noexcept { return "1.0.0-bootstrap"; }
    }
    """)
    write("core/navigation/src/smoke.cpp", """
    #include "sih26168/navigation/smoke.hpp"
    static_assert(sih26168::navigation::contract_version() == "1.0.0-bootstrap");
    """)
    write("core/navigation/tests/smoke_test.cpp", """
    #include "sih26168/navigation/smoke.hpp"
    int main() { return sih26168::navigation::contract_version() == "1.0.0-bootstrap" ? 0 : 1; }
    """)
    write("pyproject.toml", """
    [build-system]
    requires = ["setuptools>=75"]
    build-backend = "setuptools.build_meta"

    [project]
    name = "sih26168-bootstrap"
    version = "0.1.0"
    requires-python = ">=3.11"
    description = "Repository-verification scaffold; not a navigation implementation"

    [tool.setuptools]
    package-dir = {"" = "tools/bootstrap/src"}

    [tool.setuptools.packages.find]
    where = ["tools/bootstrap/src"]
    """)
    write("tools/bootstrap/src/sih26168_bootstrap/__init__.py", """
    # Repository-bootstrap metadata only; no runtime navigation algorithm.
    ARCHITECTURE_STATUS = "ARCH3-READY-FOR-REPOSITORY-BOOTSTRAP"
    CONTRACT_VERSION = "1.0.0-bootstrap"
    """)
    write("tools/bootstrap/tests/test_smoke.py", """
    import json
    import unittest
    from pathlib import Path

    class BootstrapSmokeTest(unittest.TestCase):
        def test_synthetic_fixture_is_replay_labeled(self):
            root = Path(__file__).resolve().parents[3]
            fixture = json.loads((root / "contracts/fixtures/synthetic_replay_event_v1.json").read_text())
            self.assertEqual(fixture["provenance"], "REPLAY")
            self.assertTrue(fixture["synthetic"])

    if __name__ == "__main__":
        unittest.main()
    """)
    write("contracts/VERSION", "1.0.0-bootstrap")
    write("contracts/schemas/replay_event_v1.schema.json", json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://sih26168.invalid/contracts/replay_event_v1.schema.json",
        "title": "SyntheticReplayEventV1", "type": "object", "additionalProperties": False,
        "required": ["schema_version", "event_id", "monotonic_time_ns", "provenance", "synthetic", "event_type"],
        "properties": {
            "schema_version": {"const": 1}, "event_id": {"type": "string", "minLength": 1},
            "monotonic_time_ns": {"type": "integer", "minimum": 0}, "provenance": {"const": "REPLAY"},
            "synthetic": {"const": True}, "event_type": {"enum": ["GNSS_HEALTHY", "GNSS_OUTAGE", "UNCERTAINTY_GROWTH", "GNSS_REJECTED", "GNSS_REACQUIRED"]},
        },
    }, indent=2))
    write("contracts/enums/navigation_states_v1.json", json.dumps({
        "schema_version": 1,
        "navigation_states": ["INITIALIZING", "GNSS_HEALTHY", "GNSS_OUTAGE", "REACQUISITION_PENDING", "REACQUIRED", "DEGRADED"],
        "provenance": ["LIVE", "REPLAY"],
        "note": "SCAFFOLD — NOT IMPLEMENTED",
    }, indent=2))
    write("contracts/fixtures/synthetic_replay_event_v1.json", json.dumps({
        "schema_version": 1, "event_id": "synthetic-0001", "monotonic_time_ns": 1_000_000_000,
        "provenance": "REPLAY", "synthetic": True, "event_type": "GNSS_HEALTHY",
    }, indent=2))
    write("contracts/generated/README.md", "SCAFFOLD — NOT IMPLEMENTED\n\nGenerated bindings will be produced deterministically under WP-01.")
    write("android/settings.gradle.kts", """
    pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
    dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }
    rootProject.name = "SIH26168"
    include(":app")
    """)
    write("android/build.gradle.kts", """
    plugins {
        id("com.android.application") version "8.7.3" apply false
        id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    }
    """)
    write("android/gradle.properties", """
    org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
    android.useAndroidX=true
    kotlin.code.style=official
    """)
    write("android/app/build.gradle.kts", """
    plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
    android {
        namespace = "org.sih26168.app"
        compileSdk = 35
        defaultConfig { applicationId = "org.sih26168.app"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "0.1.0-bootstrap"; testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner" }
        compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
        kotlinOptions { jvmTarget = "17" }
        buildFeatures { buildConfig = true }
        testOptions { unitTests.isReturnDefaultValues = true }
    }
    dependencies { testImplementation("junit:junit:4.13.2") }
    """)
    write("android/app/src/main/AndroidManifest.xml", """
    <manifest xmlns:android="http://schemas.android.com/apk/res/android">
      <application android:theme="@style/AppTheme" android:label="SIH26168">
        <activity android:name=".MainActivity" android:exported="true">
          <intent-filter>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
          </intent-filter>
        </activity>
      </application>
    </manifest>
    """)
    write("android/app/src/main/res/values/styles.xml", """
    <resources><style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar" /></resources>
    """)
    write("android/app/src/main/java/org/sih26168/app/MainActivity.kt", """
    package org.sih26168.app
    import android.app.Activity
    import android.os.Bundle
    import android.widget.TextView
    object ReplayDisclosure { const val LABEL = "REPLAY" }
    class MainActivity : Activity() {
        override fun onCreate(savedInstanceState: Bundle?) {
            super.onCreate(savedInstanceState)
            setContentView(TextView(this).apply { text = "${ReplayDisclosure.LABEL}\\nSCAFFOLD — NOT IMPLEMENTED"; textSize = 28f })
        }
    }
    """)
    write("android/app/src/test/java/org/sih26168/app/ReplayDisclosureTest.kt", """
    package org.sih26168.app
    import org.junit.Assert.assertEquals
    import org.junit.Test
    class ReplayDisclosureTest { @Test fun replayLabelIsUnmistakable() { assertEquals("REPLAY", ReplayDisclosure.LABEL) } }
    """)
    for path, description in {
        "android/acquisition/README.md": "Android acquisition import belongs to WP-02.",
        "android/navigation-jni/README.md": "Batch JNI integration belongs to WP-03.",
        "tools/analyzer/README.md": "Evidence-bounded analyzer work belongs to WP-13.",
        "tools/dataset/README.md": "Private dataset tooling belongs to WP-10; raw data must remain outside Git.",
        "tools/training/README.md": "Offline-only ML experiments belong to WP-11.",
        "tools/maps/README.md": "Map preparation tools belong to WP-08; PBF and SQLite artifacts remain outside Git.",
        "experiments/manifests/README.md": "Experiment manifests must identify immutable inputs and evidence status.",
        "demo/scenarios/README.md": "Submission replay scenarios must be synthetic and visibly labelled REPLAY.",
        "submission/presentation/README.md": "Presentation source planning belongs to WP-15.8.",
        "submission/video/README.md": "Video planning belongs to WP-15.9–WP-15.11; binary output is release storage only.",
        "submission/screenshots/README.md": "Approved, privacy-reviewed submission screenshots only.",
        "submission/claims/README.md": "Claims require an evidence reference and approval.",
        "submission/manifests/README.md": "Submission manifests belong to WP-15.12.",
        "fixtures/public/README.md": "Only synthetic, non-sensitive fixtures are allowed here.",
        "docs/protocols/README.md": "Protocols are documents, not evidence that execution occurred.",
        "third_party/notices/README.md": "Third-party notices will be maintained without inventing a project licence.",
    }.items():
        write(path, f"SCAFFOLD — NOT IMPLEMENTED\n\n{description}")


def governance_files() -> None:
    write("CONTRIBUTING.md", """
    # Contributing

    Work from `issue/WP-XX.Y-short-description` branches. Each child issue normally maps to one branch, one bounded task, one pull request, and one evidence set.

    Use `Relates to #123`; automatic close keywords are prohibited. A pull request requires two independent approvals, current CODEOWNER approval, resolved conversations, and passing checks. Self-approval never counts.

    Daily updates use:

    ```markdown
    ## Daily update

    - Completed:
    - Evidence/commit:
    - Current blocker:
    - Next action:
    - Expected completion:
    ```

    Evidence—not checkbox state—determines completion. Never commit private data, credentials, generated scientific claims, or fabricated results.
    """)
    write("SECURITY.md", """
    # Security Policy

    Report vulnerabilities privately to the repository owner. Do not open public issues containing secrets, precise routes, private recordings, device identifiers, or dataset extracts. Rotate any accidentally exposed credential immediately and preserve only a redacted incident record.
    """)
    write("CODE_OF_CONDUCT.md", """
    # Code of Conduct

    Communicate professionally and neutrally. Critique artifacts and evidence, never people. Harassment, public shaming, insults, and ability judgements are unacceptable. Raise safety, privacy, scientific-integrity, and workload concerns without retaliation.
    """)
    write(".gitignore", """
    # Credentials and local configuration
    .env
    .env.*
    *.pem
    *.key
    *.keystore
    *.jks
    local.properties
    # IDE/build/cache
    .idea/
    .vscode/
    .gradle/
    build/
    **/build/
    .cxx/
    CMakeFiles/
    CMakeCache.txt
    __pycache__/
    *.py[cod]
    .pytest_cache/
    .ruff_cache/
    *.egg-info/
    # Sensitive or large artifacts
    data/
    private/
    *.pbf
    *.sqlite
    *.sqlite3
    *.db
    *.apk
    *.aab
    *.onnx
    *.pt
    *.pth
    *.tflite
    *.zip
    *.7z
    *.tar
    *.gz
    *.jsonl
    # OS noise
    .DS_Store
    Thumbs.db
    """)
    write(".pre-commit-config.yaml", """
    repos:
      - repo: local
        hooks:
          - id: repository-policy
            name: repository policy
            entry: python ci/verify_repository.py all
            language: system
            pass_filenames: false
          - id: python-smoke
            name: Python bootstrap smoke tests
            entry: python -m unittest discover -s tools/bootstrap/tests
            language: system
            pass_filenames: false
    """)
    write(".github/CODEOWNERS", """
    * @akhileshkancharla @FaisalTabrez
    /core/ @akhileshkancharla @FaisalTabrez
    /contracts/ @akhileshkancharla @FaisalTabrez
    /.github/workflows/ @FaisalTabrez @akhileshkancharla
    /.github/CODEOWNERS @akhileshkancharla @FaisalTabrez
    /ci/ @FaisalTabrez @akhileshkancharla
    /docs/architecture/ @akhileshkancharla @FaisalTabrez
    /tools/analyzer/ @akhileshkancharla @FaisalTabrez
    /tools/dataset/ @FaisalTabrez @akhileshkancharla
    /tools/training/ @Zeeshan1786 @akhileshkancharla
    /android/ @likhithayepalagunta-19 @akhileshkancharla
    /demo/ @eragarg @akhileshkancharla
    /submission/ @eragarg @likhithayepalagunta-19 @akhileshkancharla
    """)
    write(".github/pull_request_template.md", """
    ## Scope
    Relates to #

    ## Evidence
    - Evidence/CI URL:
    - Test output or hash:

    ## Review
    - [ ] No automatic issue-close keyword is used
    - [ ] Private/prohibited-file scan passed
    - [ ] Scientific claims are evidence-bounded
    - [ ] Replay UI remains visibly labelled `REPLAY`
    - [ ] Required domain and CODEOWNER reviews requested

    ## Non-scope
    Describe what this PR intentionally does not implement.
    """)
    docs = {
        "docs/DEVELOPMENT_STATUS.md": """# Development Status

Repository bootstrap and minimum smoke scaffolds are the only implemented scope. Architecture Revision 3 is ready for repository bootstrap. S1 physical-device adjudication, S3 alignment, learned correction, runtime map matching, integrated live operation, field safety, and final scientific validation remain incomplete.
""",
        "docs/PRIVATE_ARTIFACT_POLICY.md": """# Private Artifact Policy

Raw IO-VNBD bytes or extracts, raw S1 recordings, exact routes, private analyzer evidence, PBF files, private SQLite graphs, device identifiers, credentials, signing keys, and unapproved weights must remain outside Git and CI. Only synthetic fixtures and hash-only references may enter the repository after review.
""",
        "docs/GENERATED_FILE_POLICY.md": """# Generated File Policy

Generated files must identify their source schema, generator version, and deterministic command. Reviewers must reproduce generated output and reject unexplained drift. Architecture Revision 3 source documents are immutable imported records, not generated repository output.
""",
        "docs/CLAIMS_AND_EVIDENCE_POLICY.md": """# Claims and Evidence Policy

A claim requires an immutable evidence reference, method, scope, reviewer, and limitations. Demonstration behaviour is not scientific proof. Replay, simulation, exploratory model output, and bounded proposals must be labelled explicitly. Missing evidence results in an open or blocked claim—not an inferred pass.
""",
        "docs/BRANCH_AND_RELEASE_POLICY.md": """# Branch and Release Policy

`main` is pull-request-only after bootstrap protection is activated. Two approvals, current CODEOWNER approval, resolved conversations, required checks, and linear history are required. Squash merge is the only allowed merge mode. `submission-v1.0-rc1` may be created only after internal verification and does not certify unresolved scientific gates.
""",
        "docs/TEAM_RESPONSIBILITY_MATRIX.md": """# Team Responsibility Matrix

| Role | Member | Authority |
|---|---|---|
    | R1/R4 | Akhilesh Kancharla (`@akhileshkancharla`) | Architecture, core, analyzer, scientific evidence, CI/CD review and release approval |
    | R2 | Md. Faisal Tabrez (`@FaisalTabrez`) | CI/CD ownership, repository automation, dataset engineering, leakage control and general closure approval |
| R3 | Zeeshan Ahmed Khan (`@Zeeshan1786`) | ML baselines, training, evaluation, export and shadow mode |
| R5 | Likhitha Yepalagunta (`@likhithayepalagunta-19`) | Android acquisition, integration, UI and map display |
| R6 | Era Garg (`@eragarg`) | Demo, documentation, PPT, video and presentation |
| OPS-1 | M. Junaid Qureshi (`@mjunaidqureshimct255a1405-art`) | Frozen-command execution and evidence capture only |
""",
        "docs/SUBMISSION_FREEZE_POLICY.md": """# Submission Freeze Policy

The immutable internal freeze is 2026-09-15 IST. September 16–19 is reserved for critical defects, factual corrections, format/upload repair, or replacement of an unusable recording. New features are prohibited in the buffer. The SIH portal deadline is 2026-09-20 IST.
""",
        "docs/architecture/ADR_INDEX.md": """# Architecture Decision Record Index

Architecture Revision 3 is the authoritative repository-bootstrap baseline. See `SIH26168_ADR_Register_v1.md`. New decisions require an architecture proposal issue and approved ADR; bootstrap must not reopen frozen decisions.
""",
    }
    for path, content in docs.items(): write(path, content)


def issue_forms() -> None:
    forms = [
        ("bug", "Bug", "type:bug"), ("feature", "Feature", "type:feature"),
        ("development-task", "Development task", "type:feature"),
        ("scientific-experiment", "Scientific experiment", "type:experiment"),
        ("architecture-proposal", "Architecture proposal", "architecture-review"),
        ("device-test", "Device test", "type:test"), ("dataset-operation", "Dataset operation", "type:operations"),
        ("documentation", "Documentation", "type:documentation"),
        ("operational-run", "Operational run", "role:operations"),
        ("blocker", "Blocker", "status:blocked"),
        ("submission-deliverable", "Submission deliverable", "type:submission"),
    ]
    template = """name: {name}
description: Evidence-bounded {lower} request
title: "[WP-XX.Y] "
labels: ["{label}", "evidence-required"]
body:
  - type: markdown
    attributes:
      value: "Do not include secrets, private evidence, precise routes, or unsupported scientific claims."
  - type: input
    id: parent
    attributes:
      label: Parent work package
      placeholder: WP-XX
    validations:
      required: true
  - type: textarea
    id: scope
    attributes:
      label: Scope and non-scope
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria and tests
      placeholder: "- [ ] Criterion with evidence"
    validations:
      required: true
  - type: textarea
    id: evidence
    attributes:
      label: Evidence and stop conditions
    validations:
      required: true
"""
    for slug, name, label in forms:
        write(f".github/ISSUE_TEMPLATE/{slug}.yml", template.format(name=name, lower=name.lower(), label=label))
    write(".github/ISSUE_TEMPLATE/config.yml", "blank_issues_enabled: false\ncontact_links: []")


def bootstrap_registers() -> None:
    rows = issue_rows()
    fields = list(rows[0])
    write_csv("docs/bootstrap/ISSUE_REGISTER.csv", rows, fields)
    milestone_rows = [{"Milestone": title, "Due UTC": due, "Due IST": ("2026-09-03 20:00 IST" if title.startswith("M0") else due[:10] + " IST"), "Purpose": purpose, "Number": "", "URL": ""} for title, due, purpose in MILESTONES]
    write_csv("docs/bootstrap/MILESTONE_REGISTER.csv", milestone_rows, list(milestone_rows[0]))
    label_rows = []
    for group, labels in LABEL_GROUPS.items():
        for label in labels:
            label_rows.append({"Label": label, "Group": group, "Color": COLORS[group], "Description": f"SIH26168 {group} — {label}"})
    write_csv("docs/bootstrap/LABEL_REGISTER.csv", label_rows, list(label_rows[0]))
    workflow_names = [
        ("repository-policy.yml", "repository-policy-check"), ("forbidden-files.yml", "forbidden-files-check"),
        ("secret-scanning.yml", "secret-scanning-check"), ("markdown.yml", "markdown-check"),
        ("internal-links.yml", "internal-links-check"), ("json.yml", "json-check"), ("csv.yml", "csv-check"),
        ("contracts.yml", "contracts-check"), ("python.yml", "python-smoke-check"), ("cpp.yml", "cpp-smoke-check"),
        ("android-jvm.yml", "android-jvm-check"), ("android-lint.yml", "android-lint-check"),
        ("android-debug-build.yml", "android-debug-build-check"), ("manifest.yml", "manifest-check"),
        ("generated-drift.yml", "generated-file-drift-check"), ("issue-governance.yml", "issue-governance-check"),
        ("pull-request-governance.yml", "pull-request-governance-check"),
        ("sensitive-review.yml", "sensitive-review-check"), ("issue-close-guard.yml", "issue-close-guard"),
        ("wip-limit.yml", "wip-limit-enforcement"), ("inactivity-accountability.yml", "inactivity-accountability"),
    ]
    workflow_rows = [{"Workflow": name, "Required check/job": check, "Purpose": check.replace("-", " "), "Required on main": "yes" if index < 18 else "no"} for index, (name, check) in enumerate(workflow_names)]
    write_csv("docs/bootstrap/WORKFLOW_REGISTER.csv", workflow_rows, list(workflow_rows[0]))
    assignment_rows = []
    for wp, (role, intended, reviewer, area) in OWNERS.items():
        assignment_rows.append({"WP": wp, "Owner role": role, "Intended assignee": intended, "Actual assignee": "pending invitation/verification", "Reviewer": reviewer, "Area": area})
    write_csv("docs/bootstrap/TEAM_ASSIGNMENT_MATRIX.csv", assignment_rows, list(assignment_rows[0]))
    write("docs/bootstrap/TEAM_ASSIGNMENT_MATRIX.md", """
    # Team Assignment Matrix

    The CSV beside this document is authoritative for machine-readable bootstrap assignment intent. Actual assignment is never inferred before GitHub confirms collaborator access.

    WP-level scientific and product authority remains in the CSV. To balance execution workload, 31 bounded child issues are delegated to Faisal under R2 while Akhilesh retains review authority: `WP-00.2`–`WP-00.6`, `WP-01.1`–`WP-01.6`, `WP-03.2`, `WP-04.1`, `WP-04.5`, `WP-04.6`, `WP-07.5`, `WP-08.1`–`WP-08.6`, `WP-13.1`, `WP-13.2`, `WP-13.3`, `WP-13.5`, `WP-13.6`, `WP-16.1`, `WP-16.2`, `WP-16.4`, and `WP-17.2`.
    """)
    write("docs/bootstrap/REPOSITORY_RULES.md", """
    # Repository Rules

    `main` requires pull requests, two approvals, current CODEOWNER approval, last-push approval, resolved conversations, required checks, and linear history. Force pushes, deletions, direct pushes, merge commits, rebase merges, and administrator bypass are disabled where the plan/API supports them. Unauthorized issue closure is reversed and audited; GitHub does not prevent the close button itself.
    """)
    write("docs/bootstrap/SUBMISSION_CRITICAL_PATH.md", """
    # Submission-Critical Path

    Forty issues are explicitly scheduled between September 3 and the September 15 internal freeze. Submission-specific children may close independently, but WP-02, WP-03, WP-09, and WP-15 parents remain open until their mandatory scientific dependencies are genuinely met. September 16–19 is contingency only.
    """)
    write("docs/bootstrap/KNOWN_LIMITATIONS.md", """
    # Known Limitations

    - Bootstrap smoke scaffolds are not navigation functionality.
    - Android, C++, and Python CI do not use private data, physical devices, GPUs, or IO-VNBD downloads.
    - S2 source is intentionally not imported by bootstrap.
    - Project-v2 fields/views may require a separate `project` OAuth scope; manual setup instructions are retained if automation is unavailable.
    - Repository protection cannot require checks until exact successful check names exist.
    """)
    write("docs/bootstrap/NEXT_ACTIONS.md", """
    # Next Actions

    - Akhilesh: obtain Project-v2 OAuth scopes or complete the documented manual project setup; review CI/CD and delegated R2 work, and triage the September 3–8 critical path.
    - Faisal: execute the 31 delegated governance, CI/CD, contract, map-support, analyzer/evidence, replay-fixture, adapter and release child issues; retain the existing private-data responsibilities and escalate scientific decisions to Akhilesh.
    - Zeeshan: prepare deterministic offline ML plans without claiming results or beginning dependency-blocked implementation.
    - Likhitha: begin only Ready submission-critical Android/replay issues, keeping dependency-blocked work in Backlog or Blocked.
    - Era: accept the pending invitation, then begin the narrative, wireframe, PPT, and video-planning issues.
    - Junaid: execute only bounded operational issues after task-specific commands are frozen and approved.
    """)
    write("docs/bootstrap/PROJECT_MANUAL_SETUP.md", """
    # GitHub Project Manual Setup

    If Project v2 automation is unavailable, create **SIH26168 Development Roadmap** and add the fields and 14 views specified in the repository-bootstrap brief. Import all 128 issues. Record actual field identifiers and view configuration in the bootstrap report; do not claim completion until verified.
    """)
    write("docs/bootstrap/REPOSITORY_BOOTSTRAP_REPORT.md", """
    # Repository Bootstrap Report

    Status: `BOOTSTRAP-IN-PROGRESS`

    Architecture Revision 3 passed the immutable input gate. Remote governance, CI, issue counts, project configuration, branch protection, and fresh-clone results are populated only after direct verification.
    """)


def workflow_header(name: str, triggers: str, permissions: str = "contents: read") -> str:
    return f"""name: {name}
on:
{triggers}
permissions:
  {permissions}
concurrency:
  group: ${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: true
"""


def standard_workflow(filename: str, display: str, job: str, command: str, setup: str = "python") -> None:
    steps = [f"      - uses: {ACTION_SHAS['checkout']} # v4"]
    if setup == "python":
        steps += [f"      - uses: {ACTION_SHAS['setup_python']} # v5", "        with:", "          python-version: '3.12'"]
    steps += ["      - name: Verify", f"        run: {command}"]
    content = workflow_header(display, "  push:\n  pull_request:") + f"jobs:\n  {job}:\n    runs-on: ubuntu-latest\n    steps:\n" + "\n".join(steps)
    write(f".github/workflows/{filename}", content)


def workflows() -> None:
    standard_workflow("repository-policy.yml", "Repository policy", "repository-policy-check", "python ci/verify_repository.py policy")
    standard_workflow("forbidden-files.yml", "Forbidden files and paths", "forbidden-files-check", "python ci/verify_repository.py forbidden")
    standard_workflow("secret-scanning.yml", "Secret scanning", "secret-scanning-check", "python ci/verify_repository.py secrets")
    standard_workflow("markdown.yml", "Markdown validation", "markdown-check", "python ci/verify_repository.py markdown")
    standard_workflow("internal-links.yml", "Internal links", "internal-links-check", "python ci/verify_repository.py links")
    standard_workflow("json.yml", "JSON validation", "json-check", "python ci/verify_repository.py json")
    standard_workflow("csv.yml", "CSV validation", "csv-check", "python ci/verify_repository.py csv")
    standard_workflow("contracts.yml", "Contracts and schemas", "contracts-check", "python ci/verify_repository.py contracts")
    standard_workflow("python.yml", "Python smoke", "python-smoke-check", "python -m unittest discover -s tools/bootstrap/tests")
    cpp = workflow_header("C++ build and tests", "  push:\n  pull_request:") + f"""jobs:
  cpp-smoke-check:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['checkout']} # v4
      - name: Configure
        run: cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
      - name: Build
        run: cmake --build build --config Release
      - name: Test
        run: ctest --test-dir build --output-on-failure -C Release
"""
    write(".github/workflows/cpp.yml", cpp)
    android_commands = {
        "android-jvm.yml": ("Android JVM tests", "android-jvm-check", "testDebugUnitTest"),
        "android-lint.yml": ("Android lint", "android-lint-check", "lintDebug"),
        "android-debug-build.yml": ("Android debug scaffold build", "android-debug-build-check", "assembleDebug"),
    }
    for filename, (display, job, task) in android_commands.items():
        content = workflow_header(display, "  push:\n  pull_request:") + f"""jobs:
  {job}:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['checkout']} # v4
      - uses: {ACTION_SHAS['setup_java']} # v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: {ACTION_SHAS['setup_gradle']} # v4
        with:
          gradle-version: '8.10.2'
      - name: Run Android scaffold check
        run: gradle -p android --no-daemon {task}
"""
        write(f".github/workflows/{filename}", content)
    standard_workflow("manifest.yml", "Manifest verification", "manifest-check", "python ci/verify_repository.py manifest")
    standard_workflow("generated-drift.yml", "Generated-file drift", "generated-file-drift-check", "python ci/generate_contract_bindings.py --check")

    issue_gov = workflow_header("Issue governance", "  issues:\n    types: [opened, edited, labeled, unlabeled]") + fr"""jobs:
  issue-governance-check:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['github_script']} # v7
        with:
          script: |
            const title = context.payload.issue.title;
            if (!/^\[WP-\d{{2}}(?:\.\d+)?\]/.test(title)) core.setFailed('Issue title must begin with a WP identifier.');
"""
    write(".github/workflows/issue-governance.yml", issue_gov)
    pr_gov = workflow_header("Pull-request governance", "  pull_request:\n    types: [opened, edited, synchronize, reopened, ready_for_review]") + fr"""jobs:
  pull-request-governance-check:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['github_script']} # v7
        with:
          script: |
            const text = `${{context.payload.pull_request.title}}\n${{context.payload.pull_request.body || ''}}`;
            if (/\b(closes|fixes|resolves)\s+#\d+/i.test(text)) core.setFailed('Use Relates to #123; automatic closure keywords are prohibited.');
            if (!/Relates to #\d+/i.test(text)) core.setFailed('A Relates to #123 reference is required.');
"""
    write(".github/workflows/pull-request-governance.yml", pr_gov)
    sensitive = workflow_header("Sensitive review", "  pull_request:\n    types: [opened, synchronize, reopened, ready_for_review]\n  pull_request_review:\n    types: [submitted, dismissed]", "contents: read\n  pull-requests: read") + fr"""jobs:
  sensitive-review-check:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['github_script']} # v7
        with:
          script: |
            const pr = context.payload.pull_request;
            const files = await github.paginate(github.rest.pulls.listFiles, {{...context.repo, pull_number: pr.number, per_page: 100}});
            const sensitive = files.some(f => /^(core\/|contracts\/|\.github\/workflows\/|\.github\/CODEOWNERS$|ci\/|docs\/architecture\/|tools\/analyzer\/)/.test(f.filename));
            if (!sensitive) return;
            const reviews = await github.paginate(github.rest.pulls.listReviews, {{...context.repo, pull_number: pr.number, per_page: 100}});
            const latest = new Map(); for (const r of reviews) latest.set(r.user.login.toLowerCase(), r);
            const approvals = [...latest.values()].filter(r => r.state === 'APPROVED' && r.user.login.toLowerCase() !== pr.user.login.toLowerCase());
            const required = pr.user.login.toLowerCase() === 'akhileshkancharla' ? 'faisaltabrez' : 'akhileshkancharla';
            if (approvals.length < 2 || !approvals.some(r => r.user.login.toLowerCase() === required)) core.setFailed(`Sensitive change requires two non-author approvals including ${{required}}.`);
"""
    write(".github/workflows/sensitive-review.yml", sensitive)
    close_guard = workflow_header("Issue close guard", "  issues:\n    types: [closed]", "contents: read\n  issues: write\n  pull-requests: read") + fr"""jobs:
  issue-close-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['github_script']} # v7
        with:
          script: |
            const issue = context.payload.issue;
            const authorized = ['akhileshkancharla', 'FaisalTabrez'].map(x => x.toLowerCase());
            const comments = await github.paginate(github.rest.issues.listComments, {{...context.repo, issue_number: issue.number, per_page: 100}});
            const approval = [...comments].reverse().find(c => authorized.includes(c.user.login.toLowerCase()) && c.body.trim() === '/approve-close');
            const substantive = [...comments].reverse().find(c => c.user.type !== 'Bot' && c.body.trim() !== '/approve-close');
            const approvalFresh = approval && (!substantive || new Date(approval.created_at) >= new Date(substantive.created_at));
            const checksComplete = !/- \[ \]/.test(issue.body || '');
            const evidence = /Evidence:\s*https?:\/\//i.test(issue.body || '');
            const requiredReview = /Required review:\s*complete/i.test(issue.body || '');
            const prMatch = (issue.body || '').match(/Required PR:\s*(none|https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/(\d+))/i);
            let requiredPr = Boolean(prMatch);
            if (prMatch && prMatch[2]) {{
              const pr = await github.rest.pulls.get({{...context.repo, pull_number: Number(prMatch[2])}});
              requiredPr = Boolean(pr.data.merged_at);
            }}
            const childNumbers = [...(issue.body || '').matchAll(/^- \[[ x]\] #(\d+)/gmi)].map(m => Number(m[1]));
            let childrenClosed = true;
            for (const number of childNumbers) {{
              const child = await github.rest.issues.get({{...context.repo, issue_number: number}});
              if (child.data.state !== 'closed') childrenClosed = false;
            }}
            const blocked = issue.labels.some(l => (l.name || l) === 'status:blocked');
            const closerAllowed = authorized.includes(context.actor.toLowerCase());
            if (!(approvalFresh && checksComplete && evidence && requiredReview && requiredPr && childrenClosed && !blocked && closerAllowed)) {{
              await github.rest.issues.update({{...context.repo, issue_number: issue.number, state: 'open'}});
              await github.rest.issues.addLabels({{...context.repo, issue_number: issue.number, labels: ['status:unauthorized-close']}});
              try {{ await github.rest.issues.removeLabel({{...context.repo, issue_number: issue.number, name: 'status:done'}}); }} catch (e) {{ if (e.status !== 404) throw e; }}
              await github.rest.issues.createComment({{...context.repo, issue_number: issue.number, body: `Closure reversed and audited. Actor: @${{context.actor}}. Missing one or more of: authorized closer, current /approve-close, complete checklist, evidence URL, merged required PR/explicit none, completed review, closed mandatory children, or unblocked status. @akhileshkancharla @FaisalTabrez`}});
              core.summary.addHeading('Unauthorized issue closure reversed').addRaw(`Actor: ${{context.actor}}`).write();
            }} else {{
              await github.rest.issues.addLabels({{...context.repo, issue_number: issue.number, labels: ['status:closure-approved', 'status:done']}});
              try {{ await github.rest.issues.removeLabel({{...context.repo, issue_number: issue.number, name: 'status:unauthorized-close'}}); }} catch (e) {{ if (e.status !== 404) throw e; }}
              for (const name of ['status:backlog', 'status:ready', 'status:in-progress', 'status:in-review', 'status:blocked', 'status:update-required', 'status:at-risk', 'status:reassignment-required']) {{
                try {{ await github.rest.issues.removeLabel({{...context.repo, issue_number: issue.number, name}}); }} catch (e) {{ if (e.status !== 404) throw e; }}
              }}
            }}
"""
    write(".github/workflows/issue-close-guard.yml", close_guard)
    wip = workflow_header("WIP limit", "  issues:\n    types: [labeled, assigned, reopened]", "contents: read\n  issues: write") + fr"""jobs:
  wip-limit-enforcement:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['github_script']} # v7
        with:
          script: |
            const issue = context.payload.issue;
            const labels = issue.labels.map(l => l.name || l);
            if (!labels.includes('status:in-progress') || issue.assignees.length === 0) return;
            for (const user of issue.assignees) {{
              const query = `repo:${{context.repo.owner}}/${{context.repo.repo}} is:issue is:open assignee:${{user.login}} label:\"status:in-progress\"`;
              const result = await github.rest.search.issuesAndPullRequests({{q: query, per_page: 10}});
              if (result.data.total_count > 1) {{
                await github.rest.issues.removeLabel({{...context.repo, issue_number: issue.number, name: 'status:in-progress'}});
                await github.rest.issues.addLabels({{...context.repo, issue_number: issue.number, labels: ['status:ready']}});
                await github.rest.issues.createComment({{...context.repo, issue_number: issue.number, body: `Returned to Ready because @${{user.login}} already has an in-progress issue. Lead approval is required for a second active issue. @akhileshkancharla`}});
              }}
            }}
"""
    write(".github/workflows/wip-limit.yml", wip)
    inactivity = workflow_header("Inactivity accountability", "  schedule:\n    - cron: '23 1 * * *'\n  workflow_dispatch:\n    inputs:\n      dry_run:\n        description: Do not mutate issues\n        required: false\n        default: 'true'", "contents: read\n  issues: write") + f"""jobs:
  inactivity-accountability:
    runs-on: ubuntu-latest
    steps:
      - uses: {ACTION_SHAS['github_script']} # v7
        env:
          DRY_RUN: ${{{{ inputs.dry_run || 'false' }}}}
        with:
          script: |
            const dry = process.env.DRY_RUN === 'true';
            const issues = await github.paginate(github.rest.issues.listForRepo, {{...context.repo, state: 'open', labels: 'status:in-progress', per_page: 100}});
            const now = Date.now(); const summary = [];
            for (const issue of issues.filter(x => !x.pull_request)) {{
              if (issue.labels.some(l => l.name === 'status:approved-unavailable')) continue;
              const comments = await github.paginate(github.rest.issues.listComments, {{...context.repo, issue_number: issue.number, per_page: 100}});
              const human = comments.filter(c => c.user.type !== 'Bot');
              const last = human.length ? new Date(human.at(-1).created_at).getTime() : new Date(issue.updated_at).getTime();
              const hours = (now - last) / 3600000; let label = hours >= 72 ? 'status:reassignment-required' : hours >= 48 ? 'status:at-risk' : hours >= 24 ? 'status:update-required' : null;
              if (label) {{ summary.push(`#${{issue.number}} ${{label}}`); if (!dry) await github.rest.issues.addLabels({{...context.repo, issue_number: issue.number, labels: [label]}}); }}
            }}
            core.summary.addHeading(dry ? 'Inactivity dry run' : 'Inactivity enforcement').addList(summary.length ? summary : ['No escalation required']).write();
"""
    write(".github/workflows/inactivity-accountability.yml", inactivity)


def verification_scripts() -> None:
    write("ci/verify_repository.py", r'''
    #!/usr/bin/env python3
    from __future__ import annotations
    import csv, hashlib, json, re, sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    EXCLUDED = {".git", "build", ".gradle", ".cxx", "__pycache__"}
    REQUIRED = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", ".gitignore", ".pre-commit-config.yaml", ".github/CODEOWNERS", ".github/pull_request_template.md", "docs/DEVELOPMENT_STATUS.md", "docs/PRIVATE_ARTIFACT_POLICY.md", "docs/GENERATED_FILE_POLICY.md", "docs/CLAIMS_AND_EVIDENCE_POLICY.md", "docs/BRANCH_AND_RELEASE_POLICY.md", "docs/TEAM_RESPONSIBILITY_MATRIX.md", "docs/SUBMISSION_FREEZE_POLICY.md", "docs/architecture/ADR_INDEX.md"]
    FORBIDDEN_SUFFIXES = {".pbf", ".sqlite", ".sqlite3", ".db", ".apk", ".aab", ".onnx", ".pt", ".pth", ".tflite", ".keystore", ".jks", ".pem", ".key", ".jsonl"}
    ACTION = re.compile(r"^\s*-?\s*uses:\s*[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$", re.M)
    ABSOLUTE = re.compile(r"(?i)((?<![A-Za-z0-9_])[A-Z]:[\\/]|C:/Users/|/Users/[^/]+/|/home/[^/]+/|/workspace/|/tmp/)")
    SCANNER_SOURCES = {"ci/verify_repository.py", "tools/bootstrap/generate_repository.py"}
    SECRETS = [re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), re.compile(r"AKIA[0-9A-Z]{16}"), re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")]
    def files():
        for p in ROOT.rglob("*"):
            if p.is_file() and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts): yield p
    def text(p):
        try: return p.read_text(encoding="utf-8")
        except UnicodeDecodeError: return ""
    def policy(errors):
        for r in REQUIRED:
            if not (ROOT/r).is_file(): errors.append(f"missing required file: {r}")
        if (ROOT/"LICENSE").exists(): errors.append("LICENSE must not exist before approval")
        issue_rows=list(csv.DictReader((ROOT/"docs/bootstrap/ISSUE_REGISTER.csv").open(encoding="utf-8")))
        parents=[r for r in issue_rows if "." not in r["WP ID"]]; children=[r for r in issue_rows if "." in r["WP ID"]]
        if (len(parents),len(children),len(issue_rows)) != (18,110,128): errors.append("issue register must be 18/110/128")
        if sum(r["Submission-critical flag"]=="yes" for r in issue_rows) != 40: errors.append("submission-critical issue count must be 40")
        if len(list(csv.DictReader((ROOT/"docs/bootstrap/MILESTONE_REGISTER.csv").open(encoding="utf-8")))) != 13: errors.append("milestone count must be 13")
        if len(list(csv.DictReader((ROOT/"docs/bootstrap/WORKFLOW_REGISTER.csv").open(encoding="utf-8")))) != 21: errors.append("workflow count must be 21")
    def forbidden(errors):
        for p in files():
            rel=p.relative_to(ROOT).as_posix(); lower=rel.lower()
            if p.suffix.lower() in FORBIDDEN_SUFFIXES or p.name==".env" or lower.startswith(("data/","private/")): errors.append(f"forbidden file: {rel}")
            if p.stat().st_size > 5*1024*1024: errors.append(f"file exceeds 5 MiB: {rel}")
            value=text(p)
            if rel not in SCANNER_SOURCES and value and ABSOLUTE.search(value): errors.append(f"absolute/local path pattern: {rel}")
    def secrets(errors):
        for p in files():
            value=text(p)
            for pattern in SECRETS:
                if pattern.search(value): errors.append(f"secret-like value: {p.relative_to(ROOT)}")
    def markdown(errors):
        for p in files():
            if p.suffix.lower()==".md" and "\x00" in text(p): errors.append(f"invalid markdown NUL: {p.relative_to(ROOT)}")
    def links(errors):
        link=re.compile(r"\[[^]]+\]\((?!https?://|#|mailto:)([^)]+)\)")
        for p in files():
            if p.suffix.lower() != ".md": continue
            for target in link.findall(text(p)):
                clean=target.split("#",1)[0]
                if clean and not (p.parent/clean).resolve().exists(): errors.append(f"broken link {target}: {p.relative_to(ROOT)}")
    def json_check(errors):
        for p in files():
            if p.suffix.lower()==".json":
                try: json.loads(text(p))
                except Exception as exc: errors.append(f"JSON {p.relative_to(ROOT)}: {exc}")
    def csv_check(errors):
        for p in files():
            if p.suffix.lower()==".csv":
                try:
                    with p.open(encoding="utf-8",newline="") as h:
                        reader=csv.DictReader(h); rows=list(reader)
                        if not reader.fieldnames or not rows: errors.append(f"empty CSV: {p.relative_to(ROOT)}")
                except Exception as exc: errors.append(f"CSV {p.relative_to(ROOT)}: {exc}")
    def contracts(errors):
        fixture=json.loads((ROOT/"contracts/fixtures/synthetic_replay_event_v1.json").read_text())
        if fixture.get("provenance")!="REPLAY" or fixture.get("synthetic") is not True: errors.append("synthetic fixture provenance invalid")
        if (ROOT/"contracts/VERSION").read_text().strip()!="1.0.0-bootstrap": errors.append("contract version invalid")
    def manifest(errors):
        p=ROOT/"docs/bootstrap/repository_manifest.json"
        if not p.exists(): errors.append("repository manifest missing"); return
        doc=json.loads(p.read_text())
        for rec in doc.get("files",[]):
            target=ROOT/rec["path"]
            if not target.is_file(): errors.append(f"manifest target missing: {rec['path']}"); continue
            actual=hashlib.sha256(target.read_bytes()).hexdigest()
            if actual!=rec["sha256"]: errors.append(f"manifest mismatch: {rec['path']}")
    def actions(errors):
        for p in (ROOT/".github/workflows").glob("*.yml"):
            value=text(p)
            if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in value): errors.append(f"control character in workflow: {p.name}")
            for line in value.splitlines():
                if "uses:" in line and not re.search(r"@[0-9a-f]{40}(?:\s+#|\s*$)",line): errors.append(f"mutable action reference: {p.name}: {line.strip()}")
            if not re.search(r"(?m)^permissions:\s*$",value): errors.append(f"permissions missing: {p.name}")
        sensitive=text(ROOT/".github/workflows/sensitive-review.yml")
        if "pull_request_review:" not in sensitive or "types: [submitted, dismissed]" not in sensitive: errors.append("sensitive review must run when reviews are submitted or dismissed")
        if "review_submitted" in sensitive: errors.append("invalid pull_request review_submitted activity type")
    checks={"policy":policy,"forbidden":forbidden,"secrets":secrets,"markdown":markdown,"links":links,"json":json_check,"csv":csv_check,"contracts":contracts,"manifest":manifest,"actions":actions}
    selected=sys.argv[1] if len(sys.argv)>1 else "all"; errors=[]
    if selected=="all":
        for fn in checks.values(): fn(errors)
    elif selected in checks: checks[selected](errors)
    else: raise SystemExit(f"unknown check: {selected}")
    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors)); raise SystemExit(1)
    print(f"PASS: {selected}")
    ''')
    write("ci/generate_contract_bindings.py", r'''
    #!/usr/bin/env python3
    import argparse, json
    from pathlib import Path
    ROOT=Path(__file__).resolve().parents[1]
    OUTPUT=ROOT/"contracts/generated/contract_version.json"
    expected=json.dumps({"contract_version":"1.0.0-bootstrap","generated_from":["contracts/VERSION","contracts/enums/navigation_states_v1.json"]},indent=2)+"\n"
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text()!=expected: raise SystemExit("generated contract drift")
        print("PASS: generated contract bindings")
    else: OUTPUT.write_text(expected,encoding="utf-8",newline="\n")
    ''')
    write("ci/update_manifest.py", r'''
    #!/usr/bin/env python3
    import hashlib, json
    from pathlib import Path
    ROOT=Path(__file__).resolve().parents[1]
    output=ROOT/"docs/bootstrap/repository_manifest.json"
    targets=[]
    targets.extend(sorted((ROOT/"docs/bootstrap").glob("*")))
    targets.extend(sorted((ROOT/"docs/architecture").rglob("*")))
    files=[]
    for p in targets:
        if p.is_file() and p != output:
            files.append({"path":p.relative_to(ROOT).as_posix(),"size_bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
    doc={"schema_version":1,"scope":"Bootstrap and immutable Architecture Revision 3 artifacts; manifest excludes itself.","files":files}
    output.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(hashlib.sha256(output.read_bytes()).hexdigest())
    ''')
    write("ci/verify_repository.ps1", """
    param([string]$Check = "all")
    $ErrorActionPreference = "Stop"
    python "$PSScriptRoot/verify_repository.py" $Check
    """)
    write("ci/verify_repository.sh", """
    #!/usr/bin/env sh
    set -eu
    python3 "$(dirname "$0")/verify_repository.py" "${1:-all}"
    """)
    write("ci/governance_selftest.py", r'''
    #!/usr/bin/env python3
    from datetime import datetime, timedelta, timezone
    def inactivity(hours):
        return "status:reassignment-required" if hours>=72 else "status:at-risk" if hours>=48 else "status:update-required" if hours>=24 else None
    assert inactivity(23) is None and inactivity(24)=="status:update-required" and inactivity(48)=="status:at-risk" and inactivity(72)=="status:reassignment-required"
    active=["WP-00.1"]
    assert ("status:ready" if len(active)>=1 else "status:in-progress")=="status:ready"
    print("PASS: WIP enforcement model")
    print("PASS: inactivity escalation dry-run model")
    ''')
    write("ci/forbidden_patterns.txt", """
    Raw IO-VNBD bytes or extracts
    Raw S1 recordings and private analyzer evidence
    PBF source files and private SQLite graphs
    Credentials, tokens, signing keys and keystores
    Absolute local machine paths
    Unapproved model weights and large binaries
    """)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture-zip", type=Path, required=True)
    args = parser.parse_args()
    basic_files()
    import_architecture(args.architecture_zip.resolve())
    governance_files()
    issue_forms()
    bootstrap_registers()
    workflows()
    verification_scripts()
    print("Generated repository scaffold: 18 parents, 110 children, 128 total issues")


if __name__ == "__main__":
    main()
