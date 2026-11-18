"""Build the assessment submission folder (copies only; nothing in the repository is moved or changed).

    python infrastructure/scripts/build_submission.py

Creates ./submission/ (git-ignored) with the presentation, documentation, screenshots, marketing deliverables,
deployment files and a source-code archive of every file git tracks or would track (respecting .gitignore, so
.env, node_modules, virtualenvs and local databases are never included). A secret scan runs over the result.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "submission"

SECTIONS = {
    ".": [("docs/SUBMISSION.md", "README.md")],
    "01-presentation": [("presentation/index.html", None), ("presentation/assets", None), ("presentation/README.md", None),
                        ("presentation/SmartEstate-AI-presentation.pdf", None), ("presentation/SmartEstate-AI-presentation.pptx", None)],
    "03-documentation": [("README.md", "PROJECT_README.md"), ("docs", None)],
    "04-screenshots": [("presentation/assets/shots", "app-screenshots")],
    "05-marketing-deliverables": [("assets/3d/smartestate-villa", "3d-villa-model-source"),
                                  ("apps/marketing/public/images", "website-images"), ("submission-extras/brochures", "brochures")],
    "06-deployment": [("render.yaml", None), ("apps/api/Dockerfile", None), ("apps/api/deploy/start.sh", None),
                      ("docs/DEPLOYMENT.md", None), ("docs/EVALUATOR_GUIDE.md", None), (".env.example", None)],
}

# Patterns that must never appear in shared files (values, not variable names).
SECRET_PATTERNS = [
    re.compile(rb"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(rb"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(rb"postgres(?:ql)?(?:\+psycopg)?://[^\s:@/]+:[^\s@<]{6,}@(?!localhost|127\.0\.0\.1|HOST|host)"),
]


# Deliberately fake keys used by the tests that prove secrets never leak — not credentials.
KNOWN_FAKES = (b"sk-ant-test-0123456789abcdefSECRET", b"sk-ant-ambient-should-not-be-used", b"sk-ant-abcdef1234567890")


def leaks(data: bytes) -> bool:
    for fake in KNOWN_FAKES:
        data = data.replace(fake, b"")
    return any(rx.search(data) for rx in SECRET_PATTERNS)


def copy(src: Path, dest: Path) -> bool:
    if not src.exists():
        print(f"  - missing (skipped): {src.relative_to(ROOT)}")
        return False
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return True


def source_archive(target: Path) -> int:
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    names = [n for n in files.decode().split("\0") if n and not n.startswith(("submission/", "presentation/", ".claude/"))]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            path = ROOT / n
            if path.is_file():
                z.write(path, f"smartestate-ai/{n}")
    return len(names)


def scan(folder: Path) -> list[str]:
    hits = []
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".glb", ".blend", ".woff2", ".ttf"}:
            data = p.read_bytes()
            if p.suffix == ".zip":
                with zipfile.ZipFile(p) as z:
                    for info in z.infolist():
                        if leaks(z.read(info)):
                            hits.append(f"{p.name}:{info.filename}")
                continue
            if leaks(data):
                hits.append(str(p.relative_to(folder)))
    return hits


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for section, items in SECTIONS.items():
        print(section)
        for src, name in items:
            s = ROOT / src
            copy(s, OUT / section / (name or s.name))
    src_dir = OUT / "02-source-code"
    src_dir.mkdir()
    count = source_archive(src_dir / "smartestate-ai-source.zip")
    print(f"02-source-code: {count} files archived")
    hits = scan(OUT)
    if hits:
        print("SECRET SCAN FAILED:", *hits, sep="\n  ")
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
