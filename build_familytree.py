#!/usr/bin/env python3
"""Build the encrypted family-tree data file.

Usage:
  FT_PASS='the-family-password' python3 build_familytree.py path/to/familysheet.csv

Reads the family contact sheet (CSV export of the Google Sheet), builds the
tree structure (Jack -> 2nd-gen branches -> 3rd-gen households -> 4th-gen
kids), and writes assets/familytree.enc — AES-256-CBC via `openssl enc
-pbkdf2 -iter 200000`, decrypted in the browser with WebCrypto. The plain
data never enters the repo.

Lineage comes from the sheet's generation columns; spouses are joined by
shared street address; 4th-gen kids attach to the 3rd-gen household whose
"Covered With This Email" list mentions their first name (address as
fallback). Unplaceable people land in an "unplaced" bucket per branch.
"""

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "assets" / "familytree.enc"

# people whose own row names a different branch than others reference
BRANCH_ALIAS = {
    "Jan Peck": "Jan McCulloch",       # Jan (McCulloch) Peck
    "Lisa Coakley": "James Coakley",   # Mrs. James F. Coakley
}
BRANCH_ORDER = ["Caren Dalton", "Jan McCulloch", "Denise Hickey",
                "Jake Coakley", "George Coakley", "Peter Coakley",
                "Hank Coakley", "Lisa Coakley", "Dosie Rymond",
                "James Coakley"]

# manual lineage fixes for people the sheet doesn't place: slug -> (branch, gen)
OVERRIDES = {
    "catherine-coakley": ("Hank Coakley", 3),  # daughter of Hank & Cindy
}

# 4th-gen kids the covered-with heuristic can't place: slug -> household id
# (household id = "hh-" + slug of its first-listed member)
KID_OVERRIDES = {
    "millie-currie": "hh-j-nick-currie",   # Camille in the household list
}

# people with no row in the contact sheet
EXTRA_PEOPLE = [
    {"name": "James F. Coakley", "branch": "James Coakley", "gen": 2,
     "note": "JP's dad"},
]

# tile photos: Lightroom publishes into photos/lot-shots/Family Tree/;
# ~/.config/familytree/photomap.csv maps "IMG_xxxx.jpg,Person Name" and the
# matched photos are embedded (256px, base64) in the encrypted payload.
PHOTO_DIR = ROOT / "photos" / "lot-shots" / "Family Tree"
PHOTO_MAP = Path.home() / ".config" / "familytree" / "photomap.csv"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    csv_path = sys.argv[1]
    passfile = Path.home() / ".config" / "familytree" / "pass"
    password = os.environ.get("FT_PASS") or (
        passfile.read_text().strip() if passfile.exists() else "")
    if not password:
        sys.exit(f"set FT_PASS or create {passfile}")
    os.environ["FT_PASS"] = password

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            first = (r.get("1st") or "").strip()
            if first in ("Gen. Total", "Family") or first.startswith("Instructions"):
                break
            if not any((r.get(k) or "").strip() for k in
                       ("2nd First", "3rd First", "4th First")):
                continue
            rows.append({k: (v or "").strip() for k, v in r.items()})

    people, order = {}, []
    for r in rows:
        if r["4th First"]:
            gen, first, last = 4, r["4th First"], r["4th Last"]
        elif r["3rd First"]:
            gen, first, last = 3, r["3rd First"], r["3rd Last"]
        else:
            gen, first, last = 2, r["2nd First"], r["2nd Last"]
        name = f"{first} {last}".strip()
        pid = slug(name) or f"p{len(order)}"
        if pid in people:
            pid = f"{pid}-{len(order)}"
        branch = f'{r["2nd First"]} {r["2nd Last"]}'.strip()
        people[pid] = {
            "id": pid, "name": name, "gen": gen,
            "branch": BRANCH_ALIAS.get(branch, branch) if branch else "",
            "covered": r["Covered With This Email"],
            "salutation": r["Salutation"],
            "address": ", ".join(x for x in (r["Road"], r["City"],
                                             f'{r["State"]} {r["Zip"]}'.strip())
                                 if x).strip(", "),
            "road": r["Road"],
            "email": r["Email"], "phone": r["Cell Phone"],
            "birthday": r["Birthday"],
        }
        order.append(pid)

    def addr_key(p):
        return re.sub(r"[^a-z0-9]", "", p["road"].lower())[:14]

    for extra in EXTRA_PEOPLE:
        pid = slug(extra["name"])
        if pid not in people:
            people[pid] = {
                "id": pid, "name": extra["name"], "gen": extra["gen"],
                "branch": extra["branch"], "covered": "", "salutation": "",
                "address": "", "road": "", "email": "", "phone": "",
                "birthday": "",
            }
            order.append(pid)

    for pid, (br, gen) in OVERRIDES.items():
        if pid in people:
            people[pid]["branch"] = br
            people[pid]["gen"] = gen

    # resolve blank-branch rows by address / salutation match
    for p in people.values():
        if p["branch"]:
            continue
        for q in people.values():
            if q["branch"] and q is not p and addr_key(p) and \
               addr_key(p) == addr_key(q):
                p["branch"] = q["branch"]
                p["gen"] = q["gen"]
                break

    # 2nd-gen couples per branch
    branches = {}
    for b in BRANCH_ORDER:
        branches[b] = {"label": b, "couple": [], "households": [],
                       "unplaced": []}
    for pid in order:
        p = people[pid]
        b = branches.get(p["branch"])
        if b is None:
            b = branches.setdefault(p["branch"] or "Unplaced",
                                    {"label": p["branch"] or "Unplaced",
                                     "couple": [], "households": [],
                                     "unplaced": []})
        if p["gen"] == 2:
            b["couple"].append(pid)

    # fold stray 2nd-gen spouse branches into their partner's real branch
    for key in [k for k in branches if k not in BRANCH_ORDER]:
        stray = branches[key]
        if not stray["couple"] or stray["households"] or stray["unplaced"]:
            continue
        for pid in list(stray["couple"]):
            p = people[pid]
            for real in BRANCH_ORDER:
                mates = branches.get(real, {}).get("couple", [])
                if any(addr_key(people[m]) and
                       addr_key(people[m]) == addr_key(p) for m in mates):
                    branches[real]["couple"].append(pid)
                    p["branch"] = real
                    stray["couple"].remove(pid)
                    break
        if not stray["couple"]:
            del branches[key]

    # 3rd-gen households (couples share an address within a branch)
    hh_by_key = {}
    for pid in order:
        p = people[pid]
        if p["gen"] != 3:
            continue
        key = (p["branch"], addr_key(p) or pid)
        hh = hh_by_key.get(key)
        if hh is None:
            hh = {"id": f"hh-{pid}", "members": [], "kids": []}
            hh_by_key[key] = hh
            branches.setdefault(p["branch"] or "Unplaced", {
                "label": p["branch"] or "Unplaced", "couple": [],
                "households": [], "unplaced": []})["households"].append(hh)
        hh["members"].append(pid)

    # attach 4th-gen kids: covered-with first-name match, then address
    for pid in order:
        p = people[pid]
        if p["gen"] != 4:
            continue
        first = p["name"].split()[0].lower()
        placed = False
        if pid in KID_OVERRIDES:
            for hh in hh_by_key.values():
                if hh["id"] == KID_OVERRIDES[pid]:
                    hh["kids"].append(pid)
                    placed = True
                    break
        if placed:
            continue
        for (br, _), hh in hh_by_key.items():
            if br != p["branch"]:
                continue
            for m in hh["members"]:
                cov = people[m]["covered"].lower()
                if first and re.search(rf"\b{re.escape(first)}\b", cov):
                    hh["kids"].append(pid)
                    placed = True
                    break
            if placed:
                break
        if not placed and addr_key(p):
            for (br, _), hh in hh_by_key.items():
                if br == p["branch"] and any(
                        addr_key(people[m]) == addr_key(p)
                        for m in hh["members"]):
                    hh["kids"].append(pid)
                    placed = True
                    break
        if not placed:
            branches.setdefault(p["branch"] or "Unplaced", {
                "label": p["branch"] or "Unplaced", "couple": [],
                "households": [], "unplaced": []})["unplaced"].append(pid)

    # embed photos as base64 thumbnails.
    # Primary source: filenames like "IMG_1234 Person Name.jpg" (Lightroom
    # export rename). photomap.csv (filename,name-or-slug) overrides, e.g.
    # to disambiguate two people with the same name. Plain IMG_1234.jpg
    # files (no name) are ignored.
    import base64
    import tempfile

    def norm(s):
        return re.sub(r"\s+", " ", s.replace("’", "'").lower()).strip()

    def tokens(s):
        return [t for t in re.split(r"[^a-z']+", norm(s)) if len(t) > 1]

    by_name = {}
    for p in people.values():
        by_name.setdefault(norm(p["name"]), []).append(p["id"])

    def candidates(photo_name):
        exact = by_name.get(norm(photo_name), [])
        if exact:
            return exact
        # widening tiers; take the first tier that produces any hits
        want = tokens(photo_name)

        def tier(fields):
            hits = []
            for p in people.values():
                pool = []
                for f in fields:
                    pool += tokens(p.get(f, ""))
                if all(any(t == w or (len(w) >= 3 and t.startswith(w)) or
                           (len(t) >= 3 and w.startswith(t))
                           for t in pool) for w in want):
                    hits.append(p["id"])
            return hits

        for fields in (["name"], ["name", "salutation"],
                       ["name", "salutation", "covered"]):
            hits = tier(fields)
            if hits:
                return hits
        return []

    assignments = {}   # pid -> source file
    if PHOTO_DIR.is_dir():
        for src in sorted(PHOTO_DIR.glob("*.jpg")):
            m = re.match(r"^IMG_\d+\s+(.+)$", src.stem)
            if not m:
                continue
            pids = candidates(m.group(1))
            if len(pids) == 1:
                if pids[0] in assignments:
                    print(f"  note: multiple photos for {m.group(1)}; "
                          f"using {src.name}")
                assignments[pids[0]] = src
            elif len(pids) > 1:
                print(f"  AMBIGUOUS, skipped: {src.name} "
                      f"(matches {', '.join(pids)})")
            else:
                print(f"  no person match, skipped: {src.name}")
    if PHOTO_MAP.exists():
        for line in PHOTO_MAP.read_text().splitlines():
            if "," not in line:
                continue
            fname, target = [x.strip() for x in line.rsplit(",", 1)]
            pid = target if target in people else slug(target)
            src = PHOTO_DIR / fname
            if pid in people and src.exists():
                for k, v in list(assignments.items()):
                    if v == src and k != pid:   # override wins outright
                        del assignments[k]
                assignments[pid] = src
            else:
                print(f"  photomap skip: {fname} -> {target}")

    photos = {}
    for pid, src in assignments.items():
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tf:
            subprocess.run(
                ["sips", "-Z", "256", "-s", "format", "jpeg",
                 "-s", "formatOptions", "70", str(src), "--out", tf.name],
                check=True, capture_output=True)
            photos[pid] = ("data:image/jpeg;base64," +
                           base64.b64encode(Path(tf.name).read_bytes()).decode())
    print(f"  embedded {len(photos)} photo(s)")

    data = {
        "root": {"name": "John Aloysius Coakley", "nickname": "Jack"},
        "photos": photos,
        "branches": [branches[b] for b in branches if
                     branches[b]["couple"] or branches[b]["households"] or
                     branches[b]["unplaced"]],
        "people": {pid: {k: v for k, v in p.items()
                         if k in ("id", "name", "gen", "address", "email",
                                  "phone", "birthday")}
                   for pid, p in people.items()},
    }

    plain = json.dumps(data, separators=(",", ":")).encode()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
         "-salt", "-base64", "-A", "-pass", "env:FT_PASS"],
        input=plain, capture_output=True, check=True,
        env={**os.environ},
    ).stdout.decode().strip()
    OUT.write_text(enc)
    n_hh = sum(len(b["households"]) for b in data["branches"])
    unplaced_names = [people[pid]["name"] for b in data["branches"]
                      for pid in b["unplaced"]]
    print(f"{len(people)} people, {len(data['branches'])} branches, "
          f"{n_hh} households, unplaced: "
          f"{', '.join(unplaced_names) or 'none'} -> {OUT.name}")


if __name__ == "__main__":
    main()
