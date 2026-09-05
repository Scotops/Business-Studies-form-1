"""Validate ADT structure, text/audio coverage, and source-PDF text coverage."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import wave
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path

import pdfplumber


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?")
PAGE_ID_RE = re.compile(r"^pg(\d{3})_")


class AdtHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.data_ids: list[str] = []
        self.inline_text: dict[str, list[str]] = defaultdict(list)
        self.meta: dict[str, str] = {}
        self._id_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        data_id = values.get("data-id")
        if data_id:
            self.data_ids.append(data_id)
            if tag == "img" and values.get("alt"):
                self.inline_text[data_id].append(values["alt"] or "")
        self._id_stack.append(data_id)
        if tag == "meta" and values.get("name") and values.get("content"):
            self.meta[values["name"] or ""] = values["content"] or ""

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self._id_stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if self._id_stack:
            self._id_stack.pop()

    def handle_data(self, data: str) -> None:
        active_id = next((item for item in reversed(self._id_stack) if item), None)
        if active_id and data.strip():
            self.inline_text[active_id].append(data)


def normalize_text(value: str) -> str:
    value = html.unescape(value).replace("’", "'")
    return " ".join(value.split())


def tokens(value: str) -> list[str]:
    return [token.lower().replace("’", "'") for token in WORD_RE.findall(value)]


def mp3_duration(path: Path) -> tuple[float, int, int]:
    data = path.read_bytes()
    index = 0
    duration = 0.0
    frames = 0
    skipped = 0
    v1_l3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    v2_l3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    sample_rates = {
        3: [44100, 48000, 32000],
        2: [22050, 24000, 16000],
        0: [11025, 12000, 8000],
    }

    while index + 4 <= len(data):
        header = int.from_bytes(data[index : index + 4], "big")
        if (header & 0xFFE00000) != 0xFFE00000:
            index += 1
            skipped += 1
            continue
        version = (header >> 19) & 0b11
        layer = (header >> 17) & 0b11
        bitrate_index = (header >> 12) & 0b1111
        sample_index = (header >> 10) & 0b11
        padding = (header >> 9) & 0b1
        if version == 1 or layer != 1 or sample_index == 3:
            index += 1
            skipped += 1
            continue
        bitrate_table = v1_l3 if version == 3 else v2_l3
        bitrate = bitrate_table[bitrate_index]
        sample_rate = sample_rates.get(version, [0, 0, 0])[sample_index]
        if not bitrate or not sample_rate:
            index += 1
            skipped += 1
            continue
        samples = 1152 if version == 3 else 576
        coefficient = 144 if version == 3 else 72
        frame_length = math.floor(coefficient * bitrate * 1000 / sample_rate) + padding
        if frame_length < 24 or index + frame_length > len(data):
            index += 1
            skipped += 1
            continue
        duration += samples / sample_rate
        frames += 1
        index += frame_length
    return duration, frames, skipped


def audio_duration(path: Path) -> tuple[float, int, int]:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            frame_rate = audio.getframerate()
            return (frames / frame_rate if frame_rate else 0.0), frames, 0
    return mp3_duration(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    texts = json.loads((root / "content/i18n/en/texts.json").read_text(encoding="utf-8"))
    audios = json.loads((root / "content/i18n/en/audios.json").read_text(encoding="utf-8"))
    pages = json.loads((root / "content/pages.json").read_text(encoding="utf-8"))
    audio_dir = root / "content/i18n/en/audio"

    missing_html: list[str] = []
    section_mismatches: list[dict[str, object]] = []
    missing_text_ids: set[str] = set()
    missing_audio_ids: set[str] = set()
    missing_audio_files: set[str] = set()
    inline_mismatches: list[dict[str, str]] = []
    ids_by_page: dict[int, set[str]] = defaultdict(set)
    page_number_mismatches: list[dict[str, object]] = []
    duplicate_data_ids: list[dict[str, object]] = []
    missing_local_resources: set[str] = set()
    roman_pages = {2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi"}

    for index, entry in enumerate(pages, start=1):
        html_path = root / entry["href"]
        if not html_path.exists():
            missing_html.append(entry["href"])
            continue
        markup = html_path.read_text(encoding="utf-8")
        doc = AdtHtmlParser()
        doc.feed(markup)
        expected_meta = {
            "title-id": entry["section_id"],
            "page-section-id": str(index),
        }
        actual_meta = {key: doc.meta.get(key) for key in expected_meta}
        if actual_meta != expected_meta:
            section_mismatches.append(
                {"href": entry["href"], "expected": expected_meta, "actual": actual_meta}
            )
        page_match = re.match(r"pg(\d{3})_", entry["section_id"])
        if page_match:
            pdf_page = int(page_match.group(1))
            expected_number: str | int | None
            if pdf_page == 1:
                expected_number = None
            elif pdf_page <= 6:
                expected_number = roman_pages[pdf_page]
            else:
                expected_number = pdf_page - 6
            if entry.get("page_number") != expected_number:
                page_number_mismatches.append(
                    {
                        "href": entry["href"],
                        "expected": expected_number,
                        "actual": entry.get("page_number"),
                    }
                )
        decoded_markup = html.unescape(markup)
        resource_urls = re.findall(r'''(?:src|href)=["']([^"'#]+)''', decoded_markup)
        resource_urls += re.findall(r'''url\(["']?([^"')]+)''', decoded_markup)
        for resource_url in resource_urls:
            clean_url = resource_url.split("?", 1)[0]
            if not clean_url or clean_url.startswith(("http:", "https:", "data:", "mailto:")):
                continue
            if clean_url.startswith("/"):
                resource_path = root / clean_url.lstrip("/")
            else:
                resource_path = html_path.parent / clean_url
            if not resource_path.resolve().is_file():
                missing_local_resources.add(f"{entry['href']}: {resource_url}")
        for data_id in doc.data_ids:
            match = PAGE_ID_RE.match(data_id)
            if match:
                ids_by_page[int(match.group(1))].add(data_id)
            if data_id not in texts:
                missing_text_ids.add(data_id)
            if data_id not in audios:
                missing_audio_ids.add(data_id)
            elif not (audio_dir / audios[data_id]).is_file():
                missing_audio_files.add(audios[data_id])
        duplicates = sorted(
            data_id for data_id, count in Counter(doc.data_ids).items() if count > 1
        )
        if duplicates:
            duplicate_data_ids.append({"href": entry["href"], "ids": duplicates})
        for data_id, parts in doc.inline_text.items():
            if data_id not in texts:
                continue
            inline = normalize_text(" ".join(parts))
            localized = normalize_text(texts[data_id])
            if inline and inline != localized:
                inline_mismatches.append(
                    {"href": entry["href"], "id": data_id, "html": inline, "json": localized}
                )

    mapped_missing_files = sorted(
        filename for filename in audios.values() if not (audio_dir / filename).is_file()
    )
    audio_assets = list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav"))
    orphan_audio_files = sorted(
        path.name for path in audio_assets if path.name not in set(audios.values())
    )
    audio_errors: list[dict[str, object]] = []
    speech_rate_outliers: list[dict[str, object]] = []
    duration_total = 0.0
    for data_id, filename in audios.items():
        audio_path = audio_dir / filename
        if not audio_path.is_file():
            continue
        duration, frames, skipped = audio_duration(audio_path)
        duration_total += duration
        if frames == 0 or duration <= 0:
            audio_errors.append({"id": data_id, "file": filename, "reason": "no valid MP3 frames"})
            continue
        skip_ratio = skipped / max(1, audio_path.stat().st_size)
        if skip_ratio > 0.01:
            audio_errors.append(
                {"id": data_id, "file": filename, "reason": f"{skip_ratio:.1%} unparsed bytes"}
            )
        word_count = len(tokens(texts.get(data_id, "")))
        if word_count >= 8 and duration > 0:
            words_per_minute = word_count / duration * 60
            if words_per_minute < 85 or words_per_minute > 260:
                speech_rate_outliers.append(
                    {
                        "id": data_id,
                        "words": word_count,
                        "duration_seconds": round(duration, 2),
                        "wpm": round(words_per_minute, 1),
                    }
                )

    pdf_coverage: list[dict[str, object]] = []
    source_page_count_mismatches: list[dict[str, int]] = []
    if args.pdf:
        with pdfplumber.open(args.pdf) as pdf:
            if len(pdf.pages) != len(pages):
                source_page_count_mismatches.append(
                    {"source_pdf_pages": len(pdf.pages), "reader_pages": len(pages)}
                )
            for page_number, page in enumerate(pdf.pages, start=1):
                source_tokens = set(tokens(page.extract_text(layout=True) or ""))
                adt_tokens: set[str] = set()
                for data_id in ids_by_page.get(page_number, set()):
                    adt_tokens.update(tokens(texts.get(data_id, "")))
                meaningful_source = {token for token in source_tokens if len(token) >= 3}
                missing = sorted(meaningful_source - adt_tokens)
                coverage = (
                    1.0 - len(missing) / len(meaningful_source) if meaningful_source else 1.0
                )
                pdf_coverage.append(
                    {
                        "pdf_page": page_number,
                        "coverage": round(coverage, 4),
                        "missing_token_count": len(missing),
                        "sample_missing_tokens": missing[:30],
                    }
                )

    offline_preloader_mismatches: list[str] = []
    preloader_path = root / "assets/offline-preloader.js"
    preloader_source = preloader_path.read_text(encoding="utf-8")
    inline_match = re.search(
        r"  var INLINE = (.*?);\n  var BASE_DIR",
        preloader_source,
        flags=re.DOTALL,
    )
    if not inline_match:
        offline_preloader_mismatches.append("INLINE payload is missing")
    else:
        inline_payload = json.loads(inline_match.group(1))
        for key, embedded_value in inline_payload.items():
            relative = key[2:] if key.startswith("./") else key
            source_path = root / relative
            if not source_path.is_file():
                offline_preloader_mismatches.append(f"missing source: {key}")
                continue
            if source_path.suffix.lower() == ".json":
                current_value = json.loads(source_path.read_text(encoding="utf-8"))
            else:
                current_value = source_path.read_text(encoding="utf-8")
            if embedded_value != current_value:
                offline_preloader_mismatches.append(key)

    report = {
        "summary": {
            "manifest_sections": len(pages),
            "html_files": len(list(root.glob("*.html"))),
            "text_entries": len(texts),
            "audio_mappings": len(audios),
            "audio_files": len(audio_assets),
            "audio_duration_hours": round(duration_total / 3600, 2),
            "lowest_pdf_page_token_coverage": min(
                (item["coverage"] for item in pdf_coverage), default=None
            ),
        },
        "errors": {
            "missing_html": missing_html,
            "section_meta_mismatches": section_mismatches,
            "page_number_mismatches": page_number_mismatches,
            "source_page_count_mismatches": source_page_count_mismatches,
            "duplicate_data_ids": duplicate_data_ids,
            "missing_local_resources": sorted(missing_local_resources),
            "offline_preloader_mismatches": offline_preloader_mismatches,
            "html_ids_missing_text": sorted(missing_text_ids),
            "html_ids_missing_audio_mapping": sorted(missing_audio_ids),
            "html_ids_missing_audio_file": sorted(missing_audio_files),
            "mapped_missing_audio_files": mapped_missing_files,
            "inline_text_mismatches": inline_mismatches,
            "invalid_audio_files": audio_errors,
        },
        "warnings": {
            "orphan_audio_files": orphan_audio_files,
            "speech_rate_outliers": speech_rate_outliers,
        },
        "pdf_page_text_coverage": pdf_coverage,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

    failures = sum(len(value) for value in report["errors"].values())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
