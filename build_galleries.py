#!/usr/bin/env python3
"""Build web galleries from Lightroom-published photo folders.

Structure:
  photos/<Series>/                 -> a series section on photography.html
  photos/<Series>/<Collection>/    -> a titled collection inside that series
  photos/<Series>/*.jpg            -> loose photos, shown without a sub-heading

The "lot-shots" series renders with its brand block (kicker, wordmark,
description); any other series gets a plain letterspaced heading from its
folder name. Series are ordered alphabetically; collections newest-name-first.

Run after publishing from Lightroom Classic, then commit + push (publish.sh
does all three). photos/ holds full-size exports and stays out of git;
assets/ holds the resized web copies and is committed.
"""

import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PHOTOS = ROOT / "photos"
ASSETS = ROOT / "assets"
PAGE = ROOT / "photography.html"
MARK_START = "<!-- SERIES START -->"
MARK_END = "<!-- SERIES END -->"
MAX_PX = 1600  # longest edge of web copies
EXTS = {".jpg", ".jpeg", ".png"}

LOTSHOTS_BLOCK = """    <p class="kicker" style="text-align:center">A portrait series</p>
    <h2 class="lotshots-mark wordmark" aria-label="Lot Shots">
      <span class="line" aria-hidden="true">L<span class="donut-o"></span>T</span>
      <span class="line" aria-hidden="true">SH<span class="donut-o"></span>TS</span>
    </h2>
    <p class="lede" style="margin:0 auto; text-align:center">
      Portraits made in parking lots — one lot, one light, one frame at a time.
    </p>"""

PLACEHOLDER = "\n".join(
    '      <div class="frame"><span>Coming soon</span></div>' for _ in range(6)
)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "gallery"


def display(name: str) -> str:
    return name.replace("-", " ").title() if name == name.lower() else name


def collections(series_dir: Path):
    """Yield (display_name, [source files]) — subfolders newest-name-first,
    then loose files with no heading."""
    for d in sorted((p for p in series_dir.iterdir() if p.is_dir()), reverse=True):
        files = sorted(f for f in d.iterdir() if f.suffix.lower() in EXTS)
        if files:
            yield d.name, files
    loose = sorted(f for f in series_dir.iterdir() if f.suffix.lower() in EXTS)
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
    kept, sections, total = set(), [], 0

    series_dirs = sorted(
        (p for p in PHOTOS.iterdir() if p.is_dir()),
        key=lambda p: p.name.lower(),
    ) if PHOTOS.is_dir() else []

    for sdir in series_dirs:
        sslug = slug(sdir.name)
        parts = []
        for cname, files in collections(sdir):
            cslug = slug(cname) if cname else "all"
            items = []
            for f in files:
                dest = ASSETS / sslug / cslug / (f.stem + ".jpg")
                rel = dest.relative_to(ROOT).as_posix()
                kept.add(dest)
                if not dest.exists() or dest.stat().st_mtime < f.stat().st_mtime:
                    resize(f, dest)
                    print(f"  resized {f.name} -> {rel}")
                items.append(rel)
            total += len(items)
            grid = "\n".join(
                f'      <a class="frame" href="{p}" target="_blank">'
                f'<img src="{p}" alt="" loading="lazy"></a>'
                for p in items
            )
            heading = (
                f'    <h3 class="collection-title">{html.escape(cname)}</h3>\n'
                if cname else ""
            )
            parts.append(f'{heading}    <div class="gallery">\n{grid}\n    </div>')
        if not parts:
            continue
        if sslug == "lot-shots":
            header = LOTSHOTS_BLOCK
        else:
            header = (f'    <h2 class="series-title wordmark">'
                      f'{html.escape(display(sdir.name))}</h2>')
        body = "\n\n".join([header] + parts)
        sections.append(
            f'  <section class="series" id="{sslug}" '
            f'aria-label="{html.escape(display(sdir.name))}">\n{body}\n  </section>'
        )

    # drop web copies whose originals were unpublished
    if ASSETS.is_dir():
        for old in ASSETS.rglob("*.jpg"):
            if old not in kept:
                old.unlink()
                print(f"  removed {old.relative_to(ROOT)}")
        for d in sorted(ASSETS.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    if sections:
        out = '\n\n  <hr class="rule">\n\n'.join(sections)
        print(f"built {len(sections)} series, {total} photo(s)")
    else:
        out = (f'  <section class="series">\n{LOTSHOTS_BLOCK}\n'
               f'    <div class="gallery">\n{PLACEHOLDER}\n    </div>\n  </section>')
        print("no photos found — placeholders left in place")

    page = PAGE.read_text()
    if MARK_START not in page or MARK_END not in page:
        sys.exit(f"markers not found in {PAGE.name}")
    head, rest = page.split(MARK_START, 1)
    _, tail = rest.split(MARK_END, 1)
    PAGE.write_text(f"{head}{MARK_START}\n{out}\n  {MARK_END}{tail}")
    print(f"updated {PAGE.name}")


if __name__ == "__main__":
    main()
