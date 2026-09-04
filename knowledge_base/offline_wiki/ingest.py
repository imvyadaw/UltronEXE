"""Offline Wikipedia ingest (Tier A - compact)
=============================================
One-time (or occasional re-run) script that builds knowledge_base/offline_wiki's
local HNSW index from a Simple English Wikipedia XML dump. This is NOT run
automatically by Ultron - it's a deliberate, manual step you run once on
your own machine with real internet access, because:

  1. The dump is ~380MB compressed / ~1GB uncompressed - too big to fetch
     as a side effect of anything Ultron does at runtime.
  2. Embedding ~240k articles locally takes a couple of hours of CPU time
     even with the lightweight all-MiniLM-L6-v2 model - this should run
     once, deliberately, not block a normal Ultron session.

HOW TO GET THE DUMP
--------------------
Download the latest Simple English Wikipedia "articles, template,
media/file descriptions, and primary meta-pages" dump (the file named
like simplewiki-latest-pages-articles.xml.bz2) from:

    https://dumps.wikimedia.org/simplewiki/latest/simplewiki-latest-pages-articles.xml.bz2

Decompress it (bzip2 -d, or 7-Zip on Windows) to get the .xml file, then
run:

    python -m knowledge_base.offline_wiki.ingest --dump path/to/simplewiki-latest-pages-articles.xml

SCOPE (Tier A - "compact")
---------------------------
Only the INTRO paragraph of each article is kept (not the full article
body) - one vector per article, ~240k vectors total, sized to fit
comfortably as a local offline fallback rather than a full local
Wikipedia mirror. This is intentional: this index only needs to answer
"what/who is X" reasonably when there's no internet at all, not replace
live search.

Redirects, disambiguation pages, and very short stub articles (below
MIN_INTRO_CHARS) are skipped since they don't carry a usable summary.
"""

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator, Dict

MIN_INTRO_CHARS = 200
BATCH_SIZE = 500
SAVE_EVERY_BATCHES = 20  # persist the index to disk periodically, not just at the very end

# MediaWiki XML dump namespace (varies by dump version - detected from the
# root element at parse time rather than hardcoded, see _detect_ns()).
_TAG_RE = re.compile(r"^\{(.*)\}")


def _detect_ns(xml_path: Path) -> str:
    for _, elem in ET.iterparse(str(xml_path), events=("start",)):
        m = _TAG_RE.match(elem.tag)
        return m.group(1) if m else ""
    return ""


def _strip_wikitext(text: str) -> str:
    """Very lightweight wikitext -> plain text cleanup for the intro
    paragraph only. Not a full wikitext parser (that's a much bigger
    dependency for marginal gain on just the first paragraph) - strips
    the common noise: templates, refs, bold/italic markup, wikilinks
    (keeping the display text), and external link brackets."""
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.S)  # {{templates}}
    text = re.sub(r"<ref.*?</ref>", "", text, flags=re.S)  # <ref>...</ref>
    text = re.sub(r"<ref[^>]*/>", "", text)  # <ref .../>
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # [[link|text]] -> text
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)  # [url text] -> text
    text = re.sub(r"'''?", "", text)  # bold/italic
    text = re.sub(r"<[^>]+>", "", text)  # stray html tags
    return text.strip()


def _first_paragraph(wikitext: str) -> str:
    for raw_para in wikitext.split("\n\n"):
        cleaned = _strip_wikitext(raw_para)
        if len(cleaned) >= MIN_INTRO_CHARS:
            return cleaned
    return ""


def iter_articles(xml_path: Path) -> Iterator[Dict]:
    """Stream-parse the dump (iterparse, not a full DOM load - the file is
    ~1GB uncompressed) and yield {"title", "text"} for each usable article."""
    ns = _detect_ns(xml_path)
    page_tag = f"{{{ns}}}page" if ns else "page"
    title_tag = f"{{{ns}}}title" if ns else "title"
    ns_tag = f"{{{ns}}}ns" if ns else "ns"
    redirect_tag = f"{{{ns}}}redirect" if ns else "redirect"
    text_tag = f"{{{ns}}}text" if ns else "text"

    for _, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag != page_tag:
            continue
        try:
            ns_elem = elem.find(ns_tag)
            if ns_elem is None or ns_elem.text != "0":
                continue  # only main-namespace articles, skip Talk:/User:/etc.
            if elem.find(redirect_tag) is not None:
                continue  # skip redirect stubs

            title = elem.findtext(title_tag) or ""
            revision = elem.find(f"{{{ns}}}revision" if ns else "revision")
            wikitext = revision.findtext(text_tag) if revision is not None else None
            if not title or not wikitext:
                continue

            intro = _first_paragraph(wikitext)
            if intro:
                yield {"title": title, "text": f"{title}: {intro}"}
        finally:
            elem.clear()  # keep peak memory flat across a ~1GB file


def run(dump_path: str) -> None:
    from knowledge_base.offline_wiki.hnsw_store import OfflineWikiStore, HAS_HNSWLIB

    if not HAS_HNSWLIB:
        print("hnswlib is not installed. Run: pip install hnswlib", file=sys.stderr)
        sys.exit(1)

    xml_path = Path(dump_path)
    if not xml_path.exists():
        print(f"Dump file not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    store = OfflineWikiStore()
    batch = []
    added = 0
    skipped = 0
    batches_since_save = 0
    start = time.time()

    for article in iter_articles(xml_path):
        batch.append({"title": article["title"], "text": article["text"], "url": ""})
        if len(batch) >= BATCH_SIZE:
            result = store.add_batch(batch)
            if "error" in result:
                print(f"  batch failed: {result['error']}", file=sys.stderr)
                skipped += len(batch)
            else:
                added += result["added"]
            batch = []
            batches_since_save += 1
            elapsed = time.time() - start
            print(f"  {added} articles indexed ({elapsed:.0f}s elapsed)", flush=True)
            if batches_since_save >= SAVE_EVERY_BATCHES:
                store.save()
                batches_since_save = 0

    if batch:
        result = store.add_batch(batch)
        if "error" in result:
            skipped += len(batch)
        else:
            added += result["added"]

    store.save()
    elapsed = time.time() - start
    print(f"\nDone. {added} articles indexed, {skipped} skipped, {elapsed:.0f}s total.")
    print(f"Index saved to: {store.__class__.__module__}")
    print("\nSet ULTRON_OFFLINE_KB_ENABLED=true in .env to start using it.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump", required=True, help="Path to the decompressed simplewiki .xml dump")
    args = parser.parse_args()
    run(args.dump)


if __name__ == "__main__":
    main()
