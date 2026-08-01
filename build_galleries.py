#!/usr/bin/env python3
"""Build web galleries from Lightroom-published photo folders.

Workflow:
  1. Lightroom Classic publishes JPEGs into photos/lot-shots/<Collection Name>/
     (or straight into photos/lot-shots/ for an uncategorized gallery).
  2. Run this script. It:
       - resizes each photo to web size into assets/lot-shots/... (via macOS sips)
       - removes web copies whose originals were unpublished
       - rewrites the gallery markup in photography.html between the
         LOTSHOTS-GALLERY markers (placeholders stay if there are no photos)
  3. Commit and push: the live site updates in about a minute.

photos/ holds Lightroom's full-size exports and stays out of git;
assets/ holds the resized web copies and is committed.
"""

import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PHOTOS = ROOT / "photos" / "lot-shots"
ASSETS = ROOT / "assets" / "lot-shots"
PAGE = ROOT / "photography.html"
MARK_START = "<!-- LOTSHOTS-GALLERY START -->"
MARK_END = "<!-- LOTSHOTS-GALLERY END -->"
MAX_PX = 1600  # longest edge of web copies
EXTS = {".jpg", ".jpeg", ".png"}

PLACEHOLDER = "\n".join(
    '      <div class="frame"><span>Coming soon</span></div>' for _ in range(6)
)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "gallery"


def collections():
    """Yield (display_name, [source files]) — subfolders first (newest name
    first, so date-prefixed folders sort naturally), then loose files."""
    if not PHOTOS.is_dir():
        return
    for d in sorted((p for p in PHOTOS.iterdir() if p.is_dir()), reverse=True):
        files = sorted(f for f in d.iterdir() if f.suffix.lower() in EXTS)
        if files:
            yield d.name, files
    loose = sorted(f for f in PHOTOS.iterdir() if f.suffix.lower() in EXTS)
    if loose:
        yield "", loose


def resize(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["sips", "-Z", str(MAX_PX), "-s", "format", "jpeg",
         "-s", "formatOptions", "80", str(src), "--out", str(dest)],
        check=True, capture_output=True,
    )


def main() -> None:
    built, kept = [], set()
    for name, files in collections():
        cslug = slug(name) if name else "all"
        items = []
        for f in files:
            dest = ASSETS / cslug / (f.stem + ".jpg")
            rel = dest.relative_to(ROOT).as_posix()
            kept.add(dest)
            if not dest.exists() or dest.stat().st_mtime < f.stat().st_mtime:
                resize(f, dest)
                print(f"  resized {f.name} -> {rel}")
            items.append(rel)
        built.append((name, items))

    # drop web copies whose originals were unpublished
    if ASSETS.is_dir():
        for old in ASSETS.rglob("*.jpg"):
            if old not in kept:
                old.unlink()
                print(f"  removed {old.relative_to(ROOT)}")
        for d in sorted(ASSETS.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    # render gallery markup
    if built:
        parts = []
        for name, items in built:
            grid = "\n".join(
                f'      <a class="frame" href="{p}" target="_blank">'
                f'<img src="{p}" alt="" loading="lazy"></a>'
                for p in items
            )
            heading = (
                f'    <h3 class="collection-title">{html.escape(name)}</h3>\n'
                if name else ""
            )
            parts.append(f'{heading}    <div class="gallery">\n{grid}\n    </div>')
        body = "\n\n".join(parts)
        total = sum(len(i) for _, i in built)
        print(f"built {len(built)} collection(s), {total} photo(s)")
    else:
        body = f'    <div class="gallery">\n{PLACEHOLDER}\n    </div>'
        print("no photos found — placeholders left in place")

    page = PAGE.read_text()
    if MARK_START not in page or MARK_END not in page:
        sys.exit(f"markers not found in {PAGE.name}")
    head, rest = page.split(MARK_START, 1)
    _, tail = rest.split(MARK_END, 1)
    PAGE.write_text(f"{head}{MARK_START}\n{body}\n    {MARK_END}{tail}")
    print(f"updated {PAGE.name}")


if __name__ == "__main__":
    main()
