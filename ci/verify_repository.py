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
