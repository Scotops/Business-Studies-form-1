"""Build source-PDF word boxes for in-place ADT read-aloud highlighting."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pdfplumber
from lxml import html


ROOT = Path(__file__).resolve().parents[1]
TEXTS_PATH = ROOT / "content/i18n/en/texts.json"
OUTPUT_PATH = ROOT / "content/pdf-word-positions.json"
TOKEN_RE = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
ROMAN_NUMERALS = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(value or "")


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = NON_ALNUM_RE.sub("", folded.lower())
    return ROMAN_NUMERALS.get(normalized, normalized)


def expand_pdf_words(raw_words: list[dict[str, object]]) -> list[dict[str, object]]:
    expanded: list[dict[str, object]] = []
    for raw in raw_words:
        raw_text = str(raw["text"])
        pieces = tokenize(raw_text)
        if not pieces:
            continue
        x0 = float(raw["x0"])
        x1 = float(raw["x1"])
        width = x1 - x0
        total_chars = max(1, sum(len(piece) for piece in pieces))
        consumed = 0
        for piece in pieces:
            piece_start = x0 + width * consumed / total_chars
            consumed += len(piece)
            piece_end = x0 + width * consumed / total_chars
            expanded.append(
                {
                    "norm": normalize(piece),
                    "x0": piece_start,
                    "top": float(raw["top"]),
                    "x1": piece_end,
                    "bottom": float(raw["bottom"]),
                }
            )
    return expanded


def candidate_starts(
    query: list[str], pdf_words: list[dict[str, object]], cursor: int
) -> list[int]:
    starts = list(range(max(0, cursor), len(pdf_words)))
    if cursor > 0:
        starts.extend(range(0, min(cursor, len(pdf_words))))
    return starts


def map_query(
    query: list[str], pdf_words: list[dict[str, object]], cursor: int
) -> tuple[list[list[list[float]]] | None, int]:
    if not query:
        return None, cursor

    # Fast path: one runtime word maps to one PDF word throughout the phrase.
    for start in candidate_starts(query, pdf_words, cursor):
        end = start + len(query)
        if end > len(pdf_words):
            continue
        if [word["norm"] for word in pdf_words[start:end]] != query:
            continue
        mapped = [boxes_for_words(pdf_words[index : index + 1]) for index in range(start, end)]
        return mapped, end

    # PDF extraction sometimes separates ligatures (for example, "fi nance").
    # Compare the phrase without spaces, then project each runtime token back
    # onto every intersecting PDF word box.
    query_joined = "".join(query)
    if not query_joined:
        return None, cursor
    for start in candidate_starts(query, pdf_words, cursor):
        combined = ""
        end = start
        while end < len(pdf_words) and len(combined) < len(query_joined):
            combined += str(pdf_words[end]["norm"])
            end += 1
        if combined != query_joined:
            continue

        pdf_ranges: list[tuple[int, int, dict[str, object]]] = []
        offset = 0
        for word in pdf_words[start:end]:
            next_offset = offset + len(str(word["norm"]))
            pdf_ranges.append((offset, next_offset, word))
            offset = next_offset

        mapped: list[list[list[float]]] = []
        query_offset = 0
        for token in query:
            token_end = query_offset + len(token)
            intersecting = [
                word
                for word_start, word_end, word in pdf_ranges
                if word_end > query_offset and word_start < token_end
            ]
            mapped.append(boxes_for_words(intersecting))
            query_offset = token_end
        return mapped, end

    return None, cursor


def boxes_for_words(words: list[dict[str, object]]) -> list[list[float]]:
    boxes: list[list[float]] = []
    for word in words:
        box = [
            round(float(word["x0"]), 3),
            round(float(word["top"]), 3),
            round(float(word["x1"]), 3),
            round(float(word["bottom"]), 3),
        ]
        if boxes:
            previous = boxes[-1]
            same_line = min(previous[3], box[3]) - max(previous[1], box[1]) > 0
            close = box[0] - previous[2] < 4
            if same_line and close:
                previous[0] = min(previous[0], box[0])
                previous[1] = min(previous[1], box[1])
                previous[2] = max(previous[2], box[2])
                previous[3] = max(previous[3], box[3])
                continue
        boxes.append(box)
    return boxes


def build(pdf_path: Path) -> dict[str, object]:
    texts = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
    output: dict[str, object] = {"version": 1, "pages": {}}
    attempted_ids = mapped_ids = attempted_tokens = mapped_tokens = 0
    unmatched: list[tuple[str, str]] = []

    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) != 48:
            raise ValueError(f"Expected 48 PDF pages, found {len(pdf.pages)}")

        for number in range(7, 49):
            prefix = f"pg{number:03d}"
            page = pdf.pages[number - 1]
            pdf_words = expand_pdf_words(page.extract_words(use_text_flow=True))
            document = html.parse(str(ROOT / f"{prefix}_sec001.html"))
            content_nodes = document.xpath('//*[@id="content"]')
            if len(content_nodes) != 1:
                raise ValueError(f"Expected one #content node for {prefix}")

            cursor = 0
            items: dict[str, list[list[list[float]]]] = {}
            seen: set[str] = set()
            for element in content_nodes[0].xpath('.//*[@data-id]'):
                data_id = element.get("data-id")
                if not data_id or data_id in seen:
                    continue
                seen.add(data_id)
                if str(element.tag).lower() in {"img", "input", "textarea", "select", "option"}:
                    continue
                if "hidden" in (element.get("class") or "").split():
                    continue
                source_text = str(texts.get(data_id, ""))
                query = [normalize(token) for token in tokenize(source_text)]
                query = [token for token in query if token]
                if not query:
                    continue
                attempted_ids += 1
                attempted_tokens += len(query)
                mapped, next_cursor = map_query(query, pdf_words, cursor)
                if mapped is None:
                    unmatched.append((data_id, source_text[:90]))
                    continue
                items[data_id] = mapped
                cursor = next_cursor
                mapped_ids += 1
                mapped_tokens += len(query)

            output["pages"][prefix] = {
                "width": round(float(page.width), 3),
                "height": round(float(page.height), 3),
                "items": items,
            }

    output["coverage"] = {
        "mappedIds": mapped_ids,
        "attemptedIds": attempted_ids,
        "mappedTokens": mapped_tokens,
        "attemptedTokens": attempted_tokens,
    }
    print(
        f"Mapped {mapped_ids}/{attempted_ids} text IDs and "
        f"{mapped_tokens}/{attempted_tokens} words"
    )
    if unmatched:
        print("Unmatched text IDs (first 30):")
        for data_id, preview in unmatched[:30]:
            print(f"  {data_id}: {preview}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, help="Original 48-page source PDF")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    result = build(args.pdf)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
