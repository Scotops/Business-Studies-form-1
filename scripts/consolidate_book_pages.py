"""Consolidate split ADT sections into one reader page per source PDF page."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

from lxml import etree, html


ROOT = Path(__file__).resolve().parents[1]
PAGES_PATH = ROOT / "content/pages.json"
TOC_PATH = ROOT / "content/toc.json"
TEXTS_PATH = ROOT / "content/i18n/en/texts.json"

PAGE_PREFIX_RE = re.compile(r"^(pg\d{3})_")
COLUMN_SPLITS = {
    "pg010": 2,
    "pg016": 3,
}


def page_prefix(section_id: str) -> str:
    match = PAGE_PREFIX_RE.match(section_id)
    if not match:
        raise ValueError(f"Cannot determine source page for {section_id}")
    return match.group(1)


def parse_document(path: Path) -> etree._ElementTree:
    parser = html.HTMLParser(encoding="utf-8", remove_comments=False)
    return html.parse(str(path), parser=parser)


def set_query_version(value: str | None, version: int) -> str | None:
    if not value:
        return value
    return re.sub(r"\?v=\d+$", f"?v={version}", value)


def organize_columns(book_body: etree._Element, prefix: str) -> None:
    split = COLUMN_SPLITS.get(prefix)
    existing_columns = book_body.xpath(
        './div[contains(concat(" ", normalize-space(@class), " "), " adt-book-column ")]'
    )
    if split is None:
        if existing_columns:
            frames = []
            for column in existing_columns:
                frames.extend(
                    column.xpath(
                        './div[contains(concat(" ", normalize-space(@class), " "), " adt-source-fragment-frame ")]'
                    )
                )
            for column in existing_columns:
                book_body.remove(column)
            for frame in frames:
                book_body.append(frame)
        return
    if existing_columns:
        return
    frames = book_body.xpath(
        './div[contains(concat(" ", normalize-space(@class), " "), " adt-source-fragment-frame ")]'
    )
    if not frames or split >= len(frames):
        raise ValueError(f"Cannot form source columns for {prefix}")
    left = html.Element("div")
    left.set("class", "adt-book-column adt-book-column--left")
    right = html.Element("div")
    right.set("class", "adt-book-column adt-book-column--right")
    for index, frame in enumerate(frames):
        (left if index < split else right).append(frame)
    book_body.append(left)
    book_body.append(right)


pages = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
toc = json.loads(TOC_PATH.read_text(encoding="utf-8"))
texts = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))

groups: OrderedDict[str, list[dict[str, object]]] = OrderedDict()
for entry in pages:
    groups.setdefault(page_prefix(str(entry["section_id"])), []).append(entry)

if list(groups) != [f"pg{number:03d}" for number in range(1, 49)]:
    raise ValueError("The current manifest does not map cleanly to source PDF pages 1-48")
if len(pages) == 48:
    for entry in pages:
        page_path = ROOT / str(entry["href"])
        tree = parse_document(page_path)
        document = tree.getroot()
        body = document.find("body")
        if body is None:
            raise ValueError(f"Body is missing in {page_path.name}")
        content_nodes = document.xpath('//*[@id="content"]')
        if len(content_nodes) != 1:
            raise ValueError(f"Expected one #content element in {page_path.name}")
        fragment_count = len(
            content_nodes[0].xpath(
                './/*[contains(concat(" ", normalize-space(@class), " "), " adt-source-fragment ")]'
            )
        )
        content_nodes[0].set("data-fragment-count", str(fragment_count))
        current_prefix = page_prefix(str(entry["section_id"]))
        content_nodes[0].set("data-source-page", current_prefix)
        for fragment in content_nodes[0].xpath(
            './/*[contains(concat(" ", normalize-space(@class), " "), " adt-source-fragment ")]'
        ):
            parent = fragment.getparent()
            parent_classes = set((parent.get("class") or "").split()) if parent is not None else set()
            if parent is None or "adt-source-fragment-frame" in parent_classes:
                continue
            position = parent.index(fragment)
            frame = html.Element("div")
            frame.set("class", "adt-source-fragment-frame")
            parent.insert(position, frame)
            frame.append(fragment)
        book_bodies = content_nodes[0].xpath(
            './div[contains(concat(" ", normalize-space(@class), " "), " adt-book-page__body ")]'
        )
        if len(book_bodies) != 1:
            raise ValueError(f"Expected one book body in {page_path.name}")
        organize_columns(book_bodies[0], current_prefix)
        for link in document.xpath('//link[contains(@href, "book-fidelity.css")]'):
            link.set("href", "./content/book-fidelity.css?v=12")
        if not document.xpath('//script[contains(@src, "book-layout.js")]'):
            layout_script = html.Element("script")
            layout_script.set("src", "./assets/book-layout.js?v=1")
            scripts = body.xpath('./script')
            if scripts:
                scripts[0].addprevious(layout_script)
            else:
                body.append(layout_script)
        rendered = etree.tostring(
            document,
            encoding="unicode",
            method="html",
            pretty_print=True,
        )
        page_path.write_text("<!DOCTYPE html>\n" + rendered, encoding="utf-8")
    print("Refreshed the 48 already-consolidated source pages")
    raise SystemExit(0)

consolidated_pages: list[dict[str, object]] = []
canonical_by_prefix: dict[str, str] = {}

for reader_index, (prefix, entries) in enumerate(groups.items(), start=1):
    canonical = entries[0]
    canonical_path = ROOT / str(canonical["href"])
    tree = parse_document(canonical_path)
    document = tree.getroot()

    content_nodes = document.xpath('//*[@id="content"]')
    if len(content_nodes) != 1:
        raise ValueError(f"Expected one #content element in {canonical_path.name}")
    content = content_nodes[0]
    for child in list(content):
        content.remove(child)
    content.text = "\n"
    content.set("class", "adt-book-page opacity-0")
    content.set("data-fragment-count", str(len(entries)))
    content.set("data-source-page", prefix)

    book_body = html.Element("div")
    book_body.set("class", "adt-book-page__body")
    content.append(book_body)

    for entry in entries:
        source_path = ROOT / str(entry["href"])
        source_tree = parse_document(source_path)
        source_contents = source_tree.getroot().xpath('//*[@id="content"]')
        if len(source_contents) != 1:
            raise ValueError(f"Expected one #content element in {source_path.name}")

        fragment = html.Element("div")
        fragment.set("class", "adt-source-fragment")
        fragment.set("data-source-section", str(entry["section_id"]))

        section_count = 0
        for source_child in source_contents[0]:
            if not isinstance(source_child.tag, str):
                continue
            child = deepcopy(source_child)
            if child.tag.lower() == "section":
                section_id = child.get("data-section-id") or str(entry["section_id"])
                child.set("id", section_id)
                section_count += 1
            fragment.append(child)

        if not section_count:
            raise ValueError(f"No section found in {source_path.name}")
        frame = html.Element("div")
        frame.set("class", "adt-source-fragment-frame")
        frame.append(fragment)
        book_body.append(frame)

    organize_columns(book_body, prefix)

    title_meta = document.xpath('//meta[@name="title-id"]')
    index_meta = document.xpath('//meta[@name="page-section-id"]')
    if len(title_meta) != 1 or len(index_meta) != 1:
        raise ValueError(f"Reader metadata is incomplete in {canonical_path.name}")
    title_meta[0].set("content", str(canonical["section_id"]))
    index_meta[0].set("content", str(reader_index))

    body = document.find("body")
    if body is None:
        raise ValueError(f"Body is missing in {canonical_path.name}")
    body.set("class", "adt-reader-shell")
    mains = body.xpath('./main[1]')
    if not mains:
        raise ValueError(f"Main element is missing in {canonical_path.name}")
    main = mains[0]
    main.set("class", "adt-reader-main")

    for reference in body.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " adt-print-page-reference ")]'):
        parent = reference.getparent()
        if parent is not None:
            parent.remove(reference)

    if prefix != "pg001":
        reference = html.Element("div")
        reference.set("class", "adt-print-page-reference")

        label = html.Element("span")
        label.set("class", "adt-print-page-reference__label")
        label.set("aria-hidden", "true")
        label.text = "Book page"
        reference.append(label)

        number = html.Element("span")
        number.set("class", "adt-print-page-reference__number")
        number.set("aria-hidden", "true")
        number.text = str(canonical["page_number"])
        reference.append(number)

        speech = html.Element("span")
        speech.set("class", "adt-speech-only")
        page_number_id = f"{prefix}_page_number"
        if page_number_id not in texts:
            raise ValueError(f"Missing page-number speech text: {page_number_id}")
        speech.set("data-id", page_number_id)
        speech.text = texts[page_number_id]
        reference.append(speech)
        main.addnext(reference)

    for link in document.xpath('//link[contains(@href, "book-fidelity.css")]'):
        link.set("href", "./content/book-fidelity.css?v=12")
    for script in document.xpath('//script[contains(@src, "offline-preloader.js")]'):
        script.set("src", "./assets/offline-preloader.js?v=3")
    if not document.xpath('//script[contains(@src, "book-layout.js")]'):
        layout_script = html.Element("script")
        layout_script.set("src", "./assets/book-layout.js?v=1")
        scripts = body.xpath('./script')
        if scripts:
            scripts[0].addprevious(layout_script)
        else:
            body.append(layout_script)

    rendered = etree.tostring(
        document,
        encoding="unicode",
        method="html",
        pretty_print=True,
    )
    canonical_path.write_text("<!DOCTYPE html>\n" + rendered, encoding="utf-8")

    consolidated = {
        "section_id": canonical["section_id"],
        "href": canonical["href"],
    }
    if "page_number" in canonical:
        consolidated["page_number"] = canonical["page_number"]
    consolidated_pages.append(consolidated)
    canonical_by_prefix[prefix] = str(canonical["href"])

for item in toc:
    prefix = page_prefix(str(item["section_id"]))
    item["href"] = f"{canonical_by_prefix[prefix]}#{item['section_id']}"

PAGES_PATH.write_text(
    json.dumps(consolidated_pages, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
TOC_PATH.write_text(json.dumps(toc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(
    f"Consolidated {len(pages)} section screens into "
    f"{len(consolidated_pages)} source-aligned reader pages"
)
