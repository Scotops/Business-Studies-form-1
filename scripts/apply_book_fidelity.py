"""Apply shared printed-page references and front-matter page metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGES_PATH = ROOT / "content/pages.json"
TEXTS_PATH = ROOT / "content/i18n/en/texts.json"
AUDIOS_PATH = ROOT / "content/i18n/en/audios.json"

NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    21: "twenty-one",
    22: "twenty-two",
    23: "twenty-three",
    24: "twenty-four",
    25: "twenty-five",
    26: "twenty-six",
    27: "twenty-seven",
    28: "twenty-eight",
    29: "twenty-nine",
    30: "thirty",
    31: "thirty-one",
    32: "thirty-two",
    33: "thirty-three",
    34: "thirty-four",
    35: "thirty-five",
    36: "thirty-six",
    37: "thirty-seven",
    38: "thirty-eight",
    39: "thirty-nine",
    40: "forty",
    41: "forty-one",
    42: "forty-two",
}
ROMAN_FRONT_MATTER = {2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi"}


def print_label(pdf_page: int) -> tuple[str | None, int | None]:
    if pdf_page == 1:
        return None, None
    if pdf_page <= 6:
        return ROMAN_FRONT_MATTER[pdf_page], pdf_page
    printed = pdf_page - 6
    return str(printed), printed


pages = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
texts = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
audios = json.loads(AUDIOS_PATH.read_text(encoding="utf-8"))

chapter_summary_continuation = (
    "Chapter summary, continued. "
    "4. Business Studies is an important field as learners acquire basic knowledge, "
    "skills and attitude towards setting up and running an enterprise. "
    "5. The main significance of Business Studies in relation to other disciplines is "
    "the transfer of students’ knowledge, skills, values and attributes into the "
    "formation of businesses that solve community needs. "
    "6. Business Studies allows the students to develop capacity to identify "
    "opportunities in different subjects and transform them into business."
)
texts["pg017_im030"] = chapter_summary_continuation
audios["pg017_im030"] = "pg017_im030_accessible.wav"

matching_exercise_description = (
    "Matching exercise table. Group A: "
    "(i) Transforming inputs to outputs for satisfying human wants and needs. "
    "(ii) Moving goods from where they are produced to where they are consumed. "
    "(iii) Selling and buying goods and services. "
    "(iv) Goods which have short shelf life. "
    "(v) An organisation engaged in producing or buying and selling goods and services "
    "with the aim of earning profit and satisfying customers’ needs. "
    "(vi) Goods which have price element. "
    "(vii) Goods which are used to make other goods. "
    "(viii) Shortage in supply. "
    "Group B: A. Scarcity. B. Opportunity cost. C. Production. D. Consumption. "
    "E. Producer goods. F. Distribution. G. Consumer goods. H. Exchange. "
    "I. Perishable goods. J. Economic goods. K. Business. L. Business Studies. "
    "M. Merit goods. N. Demerit goods."
)
texts["pg018_im009"] = matching_exercise_description
audios["pg018_im009"] = "pg018_im009_accessible.wav"

status_reactions_continuation = "reactions and create four different personality types:"
texts["pg031_n0001"] = status_reactions_continuation
audios["pg031_n0001"] = "pg031_n0001_accessible.wav"

for entry in pages:
    match = re.match(r"pg(\d{3})_", entry["section_id"])
    if not match:
        raise ValueError(f"Cannot determine PDF page for {entry['section_id']}")
    pdf_page = int(match.group(1))
    visible_label, spoken_number = print_label(pdf_page)
    if visible_label is None:
        entry.pop("page_number", None)
    else:
        entry["page_number"] = visible_label if pdf_page <= 6 else int(visible_label)

    html_path = ROOT / entry["href"]
    markup = html_path.read_text(encoding="utf-8")
    markup = markup.replace(
        'href="./content/book-fidelity.css"',
        'href="./content/book-fidelity.css?v=3"',
    )
    markup = markup.replace(
        'href="./content/book-fidelity.css?v=2"',
        'href="./content/book-fidelity.css?v=3"',
    )
    stylesheet = '    <link href="./content/book-fidelity.css?v=3" rel="stylesheet">'
    if stylesheet not in markup:
        markup = markup.replace(
            '    <link href="./content/tailwind_output.css" rel="stylesheet">',
            '    <link href="./content/tailwind_output.css" rel="stylesheet">\n' + stylesheet,
            1,
        )

    markup = markup.replace(
        'src="./assets/offline-preloader.js"',
        'src="./assets/offline-preloader.js?v=2"',
    )

    if visible_label is not None and "adt-print-page-reference" not in markup:
        data_id = f"pg{pdf_page:03d}_page_number"
        spoken_text = f"Printed book page {NUMBER_WORDS[spoken_number]}."
        footer = (
            '    <div class="adt-print-page-reference">\n'
            '      <span class="adt-print-page-reference__label" aria-hidden="true">Book page</span>\n'
            f'      <span class="adt-print-page-reference__number" aria-hidden="true">{visible_label}</span>\n'
            f'      <span class="adt-speech-only" data-id="{data_id}">{spoken_text}</span>\n'
            '    </div>\n\n'
        )
        marker = '    <div class="relative z-50" id="interface-container"></div>'
        if marker not in markup:
            raise ValueError(f"Interface marker missing in {html_path.name}")
        markup = markup.replace(marker, footer + marker, 1)
        texts[data_id] = spoken_text
        audios[data_id] = f"{data_id}.wav"

    html_path.write_text(markup, encoding="utf-8")

PAGES_PATH.write_text(json.dumps(pages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
TEXTS_PATH.write_text(json.dumps(texts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
AUDIOS_PATH.write_text(json.dumps(audios, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
