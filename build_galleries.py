#!/usr/bin/env python3
"""Build web galleries from Lightroom-published photo folders.

Structure — everything lives under the single Lightroom publish root
photos/lot-shots/ (one Hard Drive publish service in Lightroom Classic):

  photos/lot-shots/<YYYY-MM-DD Name>/  -> a dated collection inside the
                                          branded Lot Shots series
  photos/lot-shots/<Other Name>/       -> its own series
  photos/lot-shots/*.jpg               -> loose photos in the Lot Shots series

Output:
  photography.html  -> a tile per series (cover photo, name, count) between
                       the SERIES markers
  <series-slug>.html -> one generated page per series with its galleries
                        (marked with GENERATED_TAG; stale ones are removed)

Cover photo: first image whose filename contains "cover", else the first
image. Series are ordered alphabetically; collections newest-name-first.

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
ASSETS = ROOT / "assets"
PAGE = ROOT / "photography.html"
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}")
MARK_START = "<!-- SERIES START -->"
MARK_END = "<!-- SERIES END -->"
GENERATED_TAG = "<!-- generated-series-page -->"
RESERVED = {"index", "photography", "projects", "about", "media"}
MAX_PX = 1600  # longest edge of web copies
EXTS = {".jpg", ".jpeg", ".png"}

# Logo removed for now per JP — plain heading + description.
LOTSHOTS_BLOCK = """  <h1 class="series-title wordmark">Lot Shots</h1>
  <p class="lede" style="margin:0 auto; text-align:center">
    Portraits made in parking lots — one lot, one light, one frame at a time.
  </p>"""

SERIES_PAGE = """<!DOCTYPE html>
{tag}
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — JP Coakley</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css?v=9">
<script src="gallery.js?v=2" defer></script>
</head>
<body>

<header>
  <a class="site-name" href="index.html">JP&nbsp;Coakley</a>
  <nav>
    <a href="index.html">Home</a>
    <a href="photography.html" class="active">Photography</a>
    <a href="about.html">About Me</a>
  </nav>
</header>

<main>
  <p class="kicker" style="margin-top:4rem"><a class="crumb" href="photography.html">&larr; Photography</a></p>

{header}

{body}
</main>

<footer>
  <span>JP Coakley</span>
  <a class="contact-link" href="mailto:jpcoakley@gmail.com">Contact</a>
</footer>

</body>
</html>
"""

PLACEHOLDER_TILES = "\n".join(
    '    <div class="frame"><span>Coming soon</span></div>' for _ in range(3)
)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "gallery"


def display(name: str) -> str:
    return name.replace("-", " ").title() if name == name.lower() else name


def photo_files(d: Path):
    return sorted(f for f in d.iterdir() if f.suffix.lower() in EXTS)


def gather_series():
    """[(display_name, slug, [(collection_name, files), ...])], alphabetical.
    Dated folders and loose files form "Lot Shots"; other folders are their
    own series."""
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


def page_name(sslug: str) -> str:
    return (f"series-{sslug}" if sslug in RESERVED else sslug) + ".html"


def main() -> None:
    kept, tiles, total = set(), [], 0
    current_pages = set()

    for sname, sslug, colls in gather_series():
        parts, all_items = [], []
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
            all_items.extend(items)
            grid = "\n".join(
                f'      <a class="frame" href="{p}" target="_blank">'
                f'<img src="{p}" alt="" loading="lazy"></a>'
                for p in items
            )
            heading = (
                f'  <h3 class="collection-title">{html.escape(cname)}</h3>\n'
                if cname else ""
            )
            parts.append(f'{heading}  <div class="gallery">\n{grid}\n  </div>')
        if not parts:
            continue

        if sslug == "lot-shots":
            header = LOTSHOTS_BLOCK
        else:
            header = (f'  <h1 class="series-title wordmark">'
                      f'{html.escape(sname)}</h1>')

        fname = page_name(sslug)
        current_pages.add(fname)
        (ROOT / fname).write_text(SERIES_PAGE.format(
            tag=GENERATED_TAG, title=html.escape(sname),
            header=header, body="\n\n".join(parts),
        ))
        print(f"wrote {fname}")

        cover = next((p for p in all_items if "cover" in Path(p).stem.lower()),
                     all_items[0])
        count = len(all_items)
        tiles.append(
            f'    <a class="tile" href="{fname}">\n'
            f'      <img src="{cover}" alt="" loading="lazy">\n'
            f'      <span class="tile-name">{html.escape(sname)}</span>\n'
            f'      <span class="tile-count">{count} photo'
            f'{"s" if count != 1 else ""}</span>\n'
            f'    </a>'
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

    # drop generated pages for series that no longer exist
    for old_page in ROOT.glob("*.html"):
        if old_page.name in current_pages:
            continue
        try:
            head = old_page.read_text()[:200]
        except UnicodeDecodeError:
            continue
        if GENERATED_TAG in head:
            old_page.unlink()
            print(f"  removed {old_page.name}")

    if tiles:
        out = '  <div class="tiles">\n' + "\n".join(tiles) + "\n  </div>"
        print(f"built {len(tiles)} series page(s), {total} photo(s)")
    else:
        out = f'  <div class="tiles">\n{PLACEHOLDER_TILES}\n  </div>'
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
