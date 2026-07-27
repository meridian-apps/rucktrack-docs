#!/usr/bin/env python3
"""Structural checks for the docs site. Stdlib only, no deps, ~instant.

Guards the drift classes that actually bit this site on 2026-07-27, all of the
same shape: a page has TWO representations of its own contents (the visible
questions, the table of contents, the JSON-LD schema) and nothing kept them in
step, so editing one silently desynced the others.

  1. JSON-LD PARSES. A malformed block is invisible in the browser and simply
     ignored by search engines, so it fails silently forever.

  2. FAQPage SCHEMA == VISIBLE QUESTIONS. Google's structured-data rules require
     the markup to match what a reader sees. The schema had drifted BOTH ways at
     once: it still advertised two questions that had been deleted, and had
     never gained one that was added. Both halves were invisible on the page.

  3. TOC == HEADINGS. The FAQ's contents list was missing an entry for weeks
     (nobody noticed, because the entry itself rendered fine).

  4. ANCHORS RESOLVE, AND ARE UNIQUE. A '#foo' link to a heading that has been
     renamed or removed is a dead link that no build step would catch.

Usage:
    scripts/check-pages.py                # this repo's *.html
    scripts/check-pages.py path/to/*.html # explicit files
    scripts/check-pages.py --quiet        # only print failures

Exit: 0 all clean · 1 one or more checks failed.

Note for the sibling site: this is deliberately generic (it keys on the
presence of a FAQPage schema and a .toc block, not on RuckTrack specifics), so
packcal-docs can take it verbatim. Copy it there rather than importing across
repos.
"""
import glob
import html as htmllib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(fragment):
    """Visible text of an HTML fragment, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def check_page(path):
    """Returns (errors, notes) for one page."""
    errs, notes = [], []
    src = path.read_text(encoding="utf-8")
    name = path.name

    # --- 1. every JSON-LD block parses -------------------------------------
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', src, re.S)
    schemas = []
    for i, raw in enumerate(blocks):
        try:
            schemas.append(json.loads(raw))
        except json.JSONDecodeError as e:
            errs.append(f"{name}: JSON-LD block {i + 1} is not valid JSON ({e})")

    # --- headings on the page ----------------------------------------------
    heads = [(m.group(1), _text(m.group(2)))
             for m in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', src, re.S)]
    head_ids = [h[0] for h in heads]
    head_txt = [h[1] for h in heads]

    # --- 2. FAQPage schema must match the visible questions ----------------
    for s in schemas:
        if s.get("@type") != "FAQPage":
            continue
        q = [_text(e.get("name", "")) for e in s.get("mainEntity", [])]
        if not head_txt:
            errs.append(f"{name}: FAQPage schema present but no <h2 id> questions found")
            continue
        missing = [x for x in q if x not in head_txt]
        extra = [x for x in head_txt if x not in q]
        for x in missing:
            errs.append(f"{name}: schema advertises a question NOT on the page: {x!r}")
        for x in extra:
            errs.append(f"{name}: page question MISSING from schema: {x!r}")
        if not missing and not extra and q != head_txt:
            notes.append(f"{name}: schema and page agree on content but differ in order")

    # --- 3. a table of contents must list every heading --------------------
    toc = re.search(r'<div class="toc">(.*?)</div>', src, re.S)
    if toc:
        linked = re.findall(r'href="#([^"]+)"', toc.group(1))
        for hid, txt in heads:
            if hid not in linked:
                errs.append(f"{name}: heading #{hid} ({txt[:44]!r}) is missing from the contents")
        for a in linked:
            if a not in head_ids:
                errs.append(f"{name}: contents links #{a}, which is not a heading on the page")

    # --- 4. anchors resolve, and ids are unique ----------------------------
    all_ids = re.findall(r'\sid="([^"]+)"', src)
    dupes = {i for i in all_ids if all_ids.count(i) > 1}
    for d in sorted(dupes):
        errs.append(f"{name}: duplicate id {d!r}")
    for a in set(re.findall(r'href="#([^"]+)"', src)):
        if a and a not in all_ids:
            errs.append(f"{name}: dead in-page link #{a}")

    return errs, notes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    quiet = "--quiet" in sys.argv
    files = ([Path(a) for a in args] if args
             else sorted(Path(p) for p in glob.glob(str(ROOT / "*.html"))))
    if not files:
        print("check-pages: no html files found", file=sys.stderr)
        return 1

    total_err = 0
    for f in files:
        errs, notes = check_page(f)
        total_err += len(errs)
        for e in errs:
            print(f"  FAIL  {e}")
        for n in notes:
            print(f"  note  {n}")
        if not errs and not quiet:
            print(f"  ok    {f.name}")
    print()
    if total_err:
        print(f"check-pages: {total_err} problem(s) across {len(files)} page(s)")
        return 1
    print(f"check-pages: OK — {len(files)} page(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
