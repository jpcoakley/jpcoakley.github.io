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

    data = {
        "root": {"name": "John Aloysius Coakley", "nickname": "Jack"},
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
    n_un = sum(len(b["unplaced"]) for b in data["branches"])
    print(f"{len(people)} people, {len(data['branches'])} branches, "
          f"{n_hh} households, {n_un} unplaced -> {OUT.name}")


if __name__ == "__main__":
    main()
