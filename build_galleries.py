#!/usr/bin/env python3
"""Build web galleries from Lightroom-published photo folders.

Structure — everything lives under the single Lightroom publish root
photos/lot-shots/ (one Hard Drive publish service in Lightroom Classic):

  photos/lot-shots/<YYYY-MM-DD Name>/  -> a dated collection under the
                                          branded Lot Shots series section
  photos/lot-shots/<Other Name>/       -> its own top-level series section
  photos/lot-shots/*.jpg               -> loose photos in the Lot Shots section

So in Lightroom: date-prefix a published folder to file it under Lot Shots;
any other folder name becomes its own section on the Photography page.
Series are ordered alphabetically; collections newest-name-first.

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
PHOTOS = ROOT / "photos" / "lot-shots"   # Lightroom's publish root
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}")
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


def photo_files(d: Path):
    return sorted(f for f in d.iterdir() if f.suffix.lower() in EXTS)


def gather_series():
    """Map the Lightroom publish root onto site series.

    Returns [(display_name, slug, [(collection_name, files), ...])], sorted
    alphabetically. Dated folders and loose files form the "Lot Shots"
    series; every other folder is a series of its own.
    """
    if not PHOTOS.is_dir():
        return []
    lotshots, others = [], []
    for d in sorted((p for p in PHOTOS.iterdir() if p.is_dir()), reverse=True):
        files = photo_files(d)
        if not files:
            continue
        if DATED.match(d.name):
            lotshots.append((d.name, files))
        else:
            others.append((display(d.name), slug(d.name), [("", files)]))
    loose = photo_files(PHOTOS)
    if loose:
        lotshots.append(("", loose))
    series = list(others)
    if lotshots:
        series.append(("Lot Shots", "lot-shots", lotshots))
    series.sort(key=lambda s: s[0].lower())
    return series


def resize(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["sips", "-Z", str(MAX_PX), "-s", "format", "jpeg",
         "-s", "formatOptions", "80", str(src), "--out", str(dest)],
        check=True, capture_output=True,
    )


def main() -> None:
    kept, sections, total = set(), [], 0

    for sname, sslug, colls in gather_series():
        parts = []
        for cname, files in colls:
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
                      f'{html.escape(sname)}</h2>')
        body = "\n\n".join([header] + parts)
        sections.append(
            f'  <section class="series" id="{sslug}" '
            f'aria-label="{html.escape(sname)}">\n{body}\n  </section>'
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
