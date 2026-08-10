import argparse
import json
import multiprocessing
import re
import unicodedata
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
"""
=============================
LICENSES AND COPYRIGHT SCRIPT
=============================
This script processes a JSONL containing a "text" field, performing rule-based detection of licensing information. It identifies the license type of the text, classifies it as permissive or restrictive, and applies heuristic methods to determine whether the text corresponds to a book. Copyright heuristics are applied when no explicit licence is detected. The system is designed for large-scale corpus processing and supports parallel execution using multiprocessing to improve performance on multi-core systems.
The output is written as a JSONL file where each input has the additional fields:

    -"license": detected license identifier (e.g.: CC_BY, MIT, GPL)
    -"permit": license category ("permissive", "restrictive", or "unknown")
    -"is_book": boolean flag indicating whether the text is likely a book
    -"has_copyright": boolean flag indicating explicit copyright/reproduction-restriction signals (computed when license == "unknown")

===Steps===
    1. Normalize the text to improve pattern matching consistency. 
    2. Extract and classify license information using predefined patterns. 
    3. Apply document-level heuristics to detect whether the text is a book.
    4. If no explicit license is found, detect explicit copyright/reproduction restrictions.
    5. Assign permissive/restrictive categories based on the detected license.
    6. Append the analysis results to each JSON record and save the output file.

===Parallel execution===
To enable scalable processing of large datasets, the script supports parallel execution using ProcessPoolExecutor: 

    - The input file is read incrementally. 
    - Lines are grouped into batches (default: 500 lines per batch). 
    - Each batch is submitted to a pool of worker processes. 
    - The number of workers defaults to the number of available CPU cores. 
    - A controlled number of pending tasks (workers x 3) prevents excessive memory usage (avoiding OOM). 
    - Results are written progressively as tasks complete. 

===Usage===
python orchestrator_licenses.py input.jsonl output.jsonl --workers N --batch_size N

===Arguments===
    input_file      Path to input JSONL file 
    output_file     Path to output JSONL file 
    --workers       Number of parallel worker processes (default: CPU count)
    --batch_size    Number of lines per batch (default: 500)
"""

def norm_text(text: str):
    normalized = []

    for i, ch in enumerate(text):
        ch_low = ch.lower()
        ch_norm = unicodedata.normalize("NFKD", ch_low)
        ch_norm = "".join(c for c in ch_norm if not unicodedata.combining(c))

        for c in ch_norm:
            if c in "_-":
                c = " "
            if re.match(r"[^\w\s:/\.]", c):
                c = " "

            normalized.append(c)

    normalized_text = "".join(normalized)
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    return normalized_text

CC_BY_FALLBACK = {
"CC_BY": r"(?:https?://)?\S*/licenses/by/4\.0(?:/legalcode)?/?|\bcc\s*by\s*4\.0\b(?!\s*(?:nc|sa|nd))|creative\s+commons\s+(?:attribution|by)\s+4\.0(?:\s+international)?",
}
CREATIVE_COMMONS = {
"CC0": r"(?:https?://)?\S*/publicdomain/zero/1\.0/?|\bcc0\b(?:\s*1\.0)?|creative\s+commons\s+zero(?:\s+1\.0)?",
"CC_PDM": r"(?:https?://)?\S*/publicdomain/mark/1\.0/?|\bcc[-_\s]*pdm\b|public\s+domain\s+mark",
"CC_BY_2": r"(?:https?://)?\S*/licenses/by/2\.0(?:/legalcode)?/?|\bcc\s*by\s*2\.0\b|creative\s+commons\s+(?:attribution|by)\s+2\.0",
"CC_BY_2_5": r"(?:https?://)?\S*/licenses/by/2\.5(?:/legalcode)?/?|\bcc\s*by\s*2\.5\b|creative\s+commons\s+(?:attribution|by)\s+2\.5",
"CC_BY_3": r"(?:https?://)?\S*/licenses/by/3\.0(?:/legalcode)?/?|\bcc\s*by\s*3\.0\b|creative\s+commons\s+(?:attribution|by)\s+3\.0",
"CC_BY_SA": r"(?:https?://)?\S*/licenses/by[-_\s]*sa/4\.0(/legalcode)?/?|\bcc[-_\s]*by[-_\s]*sa[-_\s]*4\.0\b|creative\s+commons\s+(?:(?:attribution|by)[-_\s]+share[-_\s]+alike|by[-_\s]*sa)\s+4\.0(?:\s+international)?",
"CC_BY_SA_1": r"(?:https?://)?\S*/licenses/by[-_\s]*sa/1\.0(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*sa[-_\s]*1\.0\b|creative\s+commons\s+(?:(?:attribution|by)[-_\s]+share[-_\s]*alike|by[-_\s]*sa)\s+1\.0",
"CC_BY_SA_2_1": r"(?:https?://)?\S*/licenses/by[-_\s]*sa/2\.1(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*sa[-_\s]*2\.1\b|creative\s+commons\s+(?:(?:attribution|by)[-_\s]+share[-_\s]*alike|by[-_\s]*sa)\s+2\.1",
"CC_BY_SA_2_5": r"(?:https?://)?\S*/licenses/by[-_\s]*sa/2\.5(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*sa[-_\s]*2\.5\b|creative\s+commons\s+(?:(?:attribution|by)[-_\s]+share[-_\s]*alike|by[-_\s]*sa)\s+2\.5",
"CC_BY_SA_3": r"(?:https?://)?\S*/licenses/by[-_\s]*sa/3\.0(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*sa[-_\s]*3\.0\b|creative\s+commons\s+(?:(?:attribution|by)[-_\s]+share[-_\s]*alike|by[-_\s]*sa)\s+3\.0",
"CC_BY_NC": r"(?:https?://)?\S*/licenses/by[-_\s]*nc/4\.0(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*nc[-_\s]*4\.0\b|creative\s+commons\s+(?:attribution|by)[-_\s]+non[-_\s]*commercial\s+4\.0(?:\s+international)?",
"CC_BY_NC_SA": r"(?:https?://)?\S*/licenses/by[-_\s]*nc[-_\s]*sa/4\.0(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*nc[-_\s]*sa[-_\s]*4\.0\b|creative\s+commons\s+(?:(?:attribution|by)[-_\s]+non[-_\s]*commercial[-_\s]+share[-_\s]*alike|by[-_\s]*nc[-_\s]*sa)\s+4\.0(?:\s+international)?",
"CC_BY_ND": r"(?:https?://)?\S*/licenses/by[-_\s]*nd/4\.0(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*nd[-_\s]*4\.0\b|creative\s+commons\s+(?:attribution|by)[-_\s]+no[-_\s]*derivatives\s+4\.0(?:\s+international)?",
"CC_BY_NC_ND": r"(?:https?://)?\S*/licenses/by[-_\s]*nc[-_\s]*nd/4\.0(?:/legalcode)?/?|\bcc[-_\s]*by[-_\s]*nc[-_\s]*nd[-_\s]*4\.0\b|creative\s+commons\s+(?:attribution|by)[-_\s]+non[-_\s]*commercial[-_\s]+no[-_\s]*derivatives\s+4\.0(?:\s+international)?"
}

PERMISSIVE_LICENSES = {
"PD": r"\bpublic\s+domain\b(?!/zero|/mark)",
"MIT": r"\bmit\s+license\b|\blicense\s+mit\b|https?://\S*opensource\.org/licenses/mit",
"APACHE_2": r"\bapache\s+(?:license\s*)?(?:version\s*)?2(?:\.0)?\b|(?:https?://)?\S*apache\.org/licenses/license[-\s]?2\.0(?:\.html)?",
"BSD_2": r"\bbsd\b.*?\b2\b.*?\bclause\b|\bbsd\s*2\s+license\b",
"BSD_3": r"\bbsd\b.*?\b3\b.*?\bclause\b|\bbsd\s*3\s+license\b",
"ISC": r"\bisc\s+license\b",
"ARTISTIC_2": r"\bartistic\s+license\s*2(?:\.0)?\b",
"GFDL": r"\bgfdl\b|\bgnu\s+free\s+documentation\s+license\b",
"CDLA_P": r"\bcommunity\s+data\s+license\s+agreement\b|\bcdla\s+permissive\b",
"OPL": r"\bopen\s+parliament\s+licen[sc]e\b"
}

RESTRICTIVE_LICENSES = {
"GPL": r"\bgpl\s*(?:v|version)?\s*\d(?:\.\d)?\+?\b|\bgpl[-\s]*\d(?:\.\d)?\b|\bgnu\s+general\s+public\s+license\b|https?://\S*gnu\.org/licenses/gpl"
}

PERMISSIVE_LICENSE_NAMES = set([
    "CC0", "CC_PDM",
    "CC_BY", "CC_BY_2", "CC_BY_2_5", "CC_BY_3",
    "CC_BY_SA", "CC_BY_SA_1", "CC_BY_SA_2_1", "CC_BY_SA_2_5", "CC_BY_SA_3",
    "PD",
    "MIT", "APACHE_2", "BSD_2", "BSD_3",
    "ISC", "ARTISTIC_2",
    "GFDL", "CDLA_P", "OPL"
])

RESTRICTIVE_LICENSE_NAMES = set([
    "CC_BY_NC", "CC_BY_NC_SA", "CC_BY_ND", "CC_BY_NC_ND",
    "GPL"
])

def extract_licenses(text: str):
    normalized_text = norm_text(text)

    for name, pattern in CREATIVE_COMMONS.items():
        if re.search(pattern, normalized_text):
            return name

    for name, pattern in CC_BY_FALLBACK.items():
        if re.search(pattern, normalized_text):
            return name

    for name, pattern in {**PERMISSIVE_LICENSES, **RESTRICTIVE_LICENSES}.items():
        if re.search(pattern, normalized_text):
            return name

    return "unknown"

def get_permit_type(license_name: str) -> str:
    if license_name in PERMISSIVE_LICENSE_NAMES:
        return "permissive"
    elif license_name in RESTRICTIVE_LICENSE_NAMES:
        return "restrictive"
    else:
        return "unknown"

ISBN10_REGEX = re.compile(r'\b\d{1,5}[- ]?\d{1,7}[- ]?\d{1,7}[- ]?[\dXx]\b')

ISBN13_REGEX = re.compile(r'\b97[89][- ]?\d{1,5}[- ]?\d{1,7}[- ]?\d{1,7}[- ]?\d\b')

def validate_isbn_10(isbn: str) -> bool:
    isbn = re.sub(r'[-\s]', '', isbn).upper()
    if len(isbn) != 10:
        return False

    total = 0
    for i in range(9):
        if not isbn[i].isdigit():
            return False
        total += int(isbn[i]) * (10 - i)

    checksum = (11 - (total % 11)) % 11
    check_char = 'X' if checksum == 10 else str(checksum)
    return isbn[-1] == check_char

def validate_isbn_13(isbn: str) -> bool:
    isbn = re.sub(r'[-\s]', '', isbn)
    if len(isbn) != 13 or not isbn.isdigit():
        return False

    total = 0
    for i in range(12):
        factor = 1 if i % 2 == 0 else 3
        total += int(isbn[i]) * factor

    checksum = (10 - total % 10) % 10
    return int(isbn[-1]) == checksum

def has_valid_isbn(text: str) -> bool:
    for match in ISBN10_REGEX.finditer(text):
        if validate_isbn_10(match.group()):
            return True

    for match in ISBN13_REGEX.finditer(text):
        if validate_isbn_13(match.group()):
            return True

    return False

#
# A book must be identified from document-level structure, not from a single
# weak signal. In particular:
#   - an ISBN can occur in a bibliography, catalogue, or report;
#   - quotation marks and dashes are common in articles and reports;
#   - capitalised words are not reliable proper-noun evidence in PDF text.
#
# The detector therefore combines several independent signals and requires a
# minimum score. Strong non-book structure (article/report/thesis markers)
# reduces the score but does not automatically veto genuinely book-like text.

BOOK_MIN_CHARS = 20_000
BOOK_LONG_CHARS = 80_000
BOOK_VERY_LONG_CHARS = 120_000

ISBN_LABEL_REGEX = re.compile(r"\bisbn(?:-1[03])?\b", re.IGNORECASE)

CHAPTER_HEADING_REGEX = re.compile(
    r"""
    ^\s*
    (?:chapter|cap[ií]tulo|capitol|chapitre|part|parte|book|libro)
    \s+
    (?:\d{1,3}|[ivxlcdm]{1,8}|one|two|three|four|five|six|seven|eight|nine|ten|
       uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)
    (?:\b|\s*[:.\-–—])
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)

BOOK_FRONT_MATTER_PATTERNS = {
    "contents": re.compile(
        r"^\s*(?:table\s+of\s+contents|contents|índice|indice|sumario)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "preface": re.compile(
        r"^\s*(?:preface|foreword|prologue|pr[oó]logo|introducci[oó]n\s+del\s+autor)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "acknowledgements": re.compile(
        r"^\s*(?:acknowledg(?:e)?ments|agradecimientos)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "author_bio": re.compile(
        r"^\s*(?:about\s+the\s+author|sobre\s+el\s+autor|sobre\s+la\s+autora)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "edition": re.compile(
        r"\b(?:first|second|third|revised|primera|segunda|tercera)\s+edition\b|"
        r"\b(?:primera|segunda|tercera)\s+edici[oó]n\b",
        re.IGNORECASE,
    ),
    "published": re.compile(
        r"\b(?:first\s+published|published\s+by|publicado\s+por|editado\s+por)\b",
        re.IGNORECASE,
    ),
    "cataloguing": re.compile(
        r"\b(?:library\s+of\s+congress\s+catalog|cataloging[- ]in[- ]publication|"
        r"catalogaci[oó]n\s+en\s+la\s+publicaci[oó]n)\b",
        re.IGNORECASE,
    ),
}

NON_BOOK_PATTERNS = {
    "academic_article": re.compile(
        r"^\s*abstract\s*$|^\s*(?:keywords?|palabras\s+clave)\s*[:.]|"
        r"^\s*(?:references|referencias|bibliograf[ií]a)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "report": re.compile(
        r"\b(?:annual|technical|research|evaluation|progress|policy|market|"
        r"impact|sustainability)\s+report\b|"
        r"\b(?:informe\s+(?:anual|t[eé]cnico|de\s+investigaci[oó]n|de\s+evaluaci[oó]n|"
        r"de\s+progreso|de\s+mercado|de\s+impacto))\b",
        re.IGNORECASE,
    ),
    "thesis": re.compile(
        r"\b(?:doctoral|master(?:'s)?|phd)\s+(?:thesis|dissertation)\b|"
        r"\b(?:tesis\s+doctoral|trabajo\s+fin\s+de\s+(?:grado|m[aá]ster))\b",
        re.IGNORECASE,
    ),
    "proceedings": re.compile(
        r"\b(?:conference|workshop)\s+proceedings\b|\bactas\s+del?\s+(?:congreso|taller)\b",
        re.IGNORECASE,
    ),
    "manual_or_guide": re.compile(
        r"\b(?:user|installation|training|reference|style)\s+manual\b|"
        r"\bmanual\s+de\s+(?:usuario|instalaci[oó]n|formaci[oó]n|referencia|estilo)\b|"
        r"\b(?:implementation|technical|practical)\s+guide\b|"
        r"\bgu[ií]a\s+(?:t[eé]cnica|pr[aá]ctica|de\s+implementaci[oó]n)\b",
        re.IGNORECASE,
    ),
}


def text_length(text: str) -> int:
    """Return document length after collapsing extraction whitespace."""
    return len(re.sub(r"\s+", " ", text).strip())


def has_book_length(text: str, min_characters: int = BOOK_LONG_CHARS) -> bool:
    return text_length(text) >= min_characters


def narrative_symbol_ratio(text: str) -> float:
    """Ratio of dialogue/quotation punctuation to all characters."""
    if not text:
        return 0.0
    found = len(re.findall(r'["“”‘’—–]', text))
    return found / len(text)


def has_narrative_symbols(text: str, ratio_min: float = 0.0035) -> bool:
    return narrative_symbol_ratio(text) >= ratio_min


def valid_isbn_matches(text: str):
    """Yield valid ISBN matches with their positions."""
    for regex, validator in (
        (ISBN10_REGEX, validate_isbn_10),
        (ISBN13_REGEX, validate_isbn_13),
    ):
        for match in regex.finditer(text):
            if validator(match.group()):
                yield match


def has_contextual_book_isbn(text: str, label_window: int = 40) -> bool:
    """
    Detect an ISBN that behaves like publication metadata.

    The ISBN must be explicitly labelled and occur near the beginning or end of
    the document. This avoids treating ISBNs in body text or bibliographies as
    proof that the complete document is a book.
    """
    if not text:
        return False

    edge_size = max(4_000, int(len(text) * 0.20))
    for match in valid_isbn_matches(text):
        near_edge = match.start() <= edge_size or match.end() >= len(text) - edge_size
        if not near_edge:
            continue

        context_start = max(0, match.start() - label_window)
        context_end = min(len(text), match.end() + label_window)
        if ISBN_LABEL_REGEX.search(text[context_start:context_end]):
            return True

    return False


def count_chapter_headings(text: str) -> int:
    """Count explicit numbered chapter/part/book headings."""
    return len(CHAPTER_HEADING_REGEX.findall(text))


def count_front_matter_signals(text: str) -> int:
    return sum(bool(pattern.search(text)) for pattern in BOOK_FRONT_MATTER_PATTERNS.values())


def count_non_book_signals(text: str) -> int:
    return sum(bool(pattern.search(text)) for pattern in NON_BOOK_PATTERNS.values())


def book_signal_score(text: str) -> int:
    """Compute a conservative document-level score for book structure."""
    length = text_length(text)
    if length < BOOK_MIN_CHARS:
        return 0

    chapter_count = count_chapter_headings(text)
    front_matter_count = count_front_matter_signals(text)
    non_book_count = count_non_book_signals(text)

    score = 0

    if has_contextual_book_isbn(text):
        score += 3

    if chapter_count >= 3:
        score += 4
    elif chapter_count == 2:
        score += 3
    elif chapter_count == 1:
        score += 1

    if front_matter_count >= 3:
        score += 3
    elif front_matter_count == 2:
        score += 2
    elif front_matter_count == 1:
        score += 1

    if length >= BOOK_VERY_LONG_CHARS:
        score += 2
    elif length >= BOOK_LONG_CHARS:
        score += 1

    if length >= BOOK_LONG_CHARS and has_narrative_symbols(text):
        score += 1

    score -= min(non_book_count * 2, 4)

    return score


def is_book(text: str) -> bool:
    """
    Return True only when multiple independent signals support that the record
    contains a complete or substantial book.
    """
    return book_signal_score(text) >= 5

#
# Detect explicit document-level copyright restrictions. Avoid broad mentions
# such as the word "copyright" by itself, "copyright law", or "intellectual
# property", since those can appear in ordinary academic/legal discussion.
# Also avoid standalone "(c)", which is frequently an enumeration marker.

COPYRIGHT_MAIN_REGEX = re.compile(
    r"""
    # Explicit copyright symbols
    (?:©|Ⓒ)

    # English restrictive notices
    |\bcopyright\b(?!\s+(?:law|laws|code|codes|policy|policies|act|acts|legislation|infringement|exceptions?|issues?|questions?|discussion|research|study|studies))
    |\ball\s+rights\s+reserved\b
    |\bprotected\s+by\s+copyright\b
    |\bcopyright\s+(?:©\s*)?(?:18|19|20|21)\d{2}\b
    |\breproduction\s+(?:is\s+)?prohibited\b
    |\bunauthori[sz]ed\s+reproduction\s+(?:is\s+)?prohibited\b
    |\bmay\s+not\s+be\s+reproduced\b
    |\bno\s+part\s+of\s+this\s+(?:book|publication|document)\b
       .{0,120}?\bmay\s+be\s+reproduced\b
    |\bno\s+part\b.{0,120}?\bmay\s+be\s+copied\b

    # Spanish restrictive notices
    |\btodos\s+los\s+derechos\s+reservados\b
    |\bprotegid[ao]\s+por\s+derechos\s+de\s+autor\b
    |\bprohibid[ao]\s+(?:la|su)\s+reproducci[oó]n\b
    |\bqueda\s+prohibida\s+la\s+reproducci[oó]n\b
    |\bno\s+se\s+permite\s+la\s+reproducci[oó]n\b
    |\bninguna\s+parte\b.{0,120}?\bpuede\s+ser\s+reproducida\b
    |\bninguna\s+parte\b.{0,120}?\bpodr[aá]\s+ser\s+reproducida\b
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL
)

FORBIDDEN_PREFIX_WORDS = re.compile(
    r'\b(?:no|not)\b',
    re.IGNORECASE
)

def has_copyright(text: str) -> bool:
    for match in COPYRIGHT_MAIN_REGEX.finditer(text):
        start = match.start()
        words_before = re.findall(r'\b\w+\b', text[:start])
        previous_word = words_before[-1].lower() if words_before else ""

        if FORBIDDEN_PREFIX_WORDS.fullmatch(previous_word):
            continue
        return True
    return False

def extract_years(text):
    DATE_REGEX = r"""
        (\b(?: (?:18|19|20|21)?\d{2}[-/. ]\d{1,2}[-/. ]\d{1,2} )\b)
        |(\b(?: \d{1,2}[-/. ]\d{1,2}[-/. ](?:\d{2}|\d{4}) )\b)
        |
        (\b\d{1,2}(?:st|nd|rd|th)?(?:[-,\s]*(?:of\s+)?)?(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)[-,\s]*\d{2,4}\b)
        |
        (\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)[-,\s]*\d{1,2}(?:st|nd|rd|th)?[-,\s]*\d{2,4}\b)
        |
        (\b(?: (?:18|19|20|21)?\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})? )\b)
        |
        (\b(?:18|19|20|21)\d{2}\b)
    """
    matches = re.findall(DATE_REGEX, text, re.IGNORECASE | re.VERBOSE)

    years = []
    for match_group in matches:
        match = next(m for m in match_group if m)
        year_match = re.search(r'\b((?:18|19|20|21)\d{2})\b', match)
        if year_match:
            years.append(int(year_match.group(1)))

    return years

      
def has_date_copyright(text: str) -> bool:
    current_year = datetime.now().year
    cutoff = current_year - 75
    years = extract_years(text)

    if not years:
        return False

    copyright_keywords = r"(©|Ⓒ|all\s+rights\s+reserved|todos\s+los\s+derechos\s+reservados|protected\s+by\s+copyright|protegido\s+por\s+derechos\s+de\s+autor|protegida\s+por\s+derechos\s+de\s+autor|no\s+part\s+of\s+this\s+(?:book|publication|document)\s+may\s+be\s+reproduced|prohibid[ao]\s+(?:la|su)\s+reproducci[oó]n)"
    
    for year in years:
        if year >= cutoff:
            pattern = re.compile(
                rf"{copyright_keywords}.{{0,20}}{year}|{year}.{{0,20}}{copyright_keywords}",
                re.IGNORECASE | re.DOTALL
            )
            if pattern.search(text):
                return True

    return False

def process_jsonl(input_path, output_path):

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for line in fin:
            if not line.strip():
                continue

            row = json.loads(line)
            text = row.get("text", "")

            license_name = extract_licenses(text)

            is_book_flag = False
            copyright_flag = False

            is_book_flag = is_book(text)

            if license_name == "unknown":
                copyright_flag = has_copyright(text) or has_date_copyright(text)
            else:
                copyright_flag = False

            permit_type = get_permit_type(license_name)

            row["license"] = license_name
            row["permit"]=permit_type
            row["is_book"] = is_book_flag
            row["has_copyright"] = copyright_flag

            fout.write(json.dumps(row, ensure_ascii=False) + "\n")

def process_batch(batch_lines):
    output_lines=[]
    for line in batch_lines: 
        if not line.strip():
            continue
        try:
            row=json.loads(line)
        except Exception:
            continue
        text=row.get("text","")
        
        license_name=extract_licenses(text)

        is_book_flag=False 
        copyright_flag=False

        is_book_flag = is_book(text)

        if license_name == "unknown":
            copyright_flag=(
                has_copyright(text)
                or has_date_copyright(text)
            )
        else:
            copyright_flag = False
        permit_type=get_permit_type(license_name)

        row["license"]=license_name
        row["permit"]=permit_type
        row["is_book"]=is_book_flag
        row["has_copyright"]=copyright_flag

        output_lines.append(json.dumps(row,ensure_ascii=False))
    
    return output_lines

def process_jsonl_parallel (input_path, output_path, batch_size=500, workers=None):
    if workers is None:
        workers=multiprocessing.cpu_count()
    
    max_pending=workers*3
    
    with open(input_path,"r",encoding="utf-8") as fin, \
        open(output_path, "w", encoding="utf-8") as fout, \
        ProcessPoolExecutor(max_workers=workers) as executor: 
        futures=[]
        batch=[]
        for line in fin: 
            batch.append(line)

            if len(batch) >= batch_size:
                futures.append(executor.submit(process_batch, batch))
                batch=[]
            
            if len(futures) >= max_pending: 
                for fut in as_completed(futures):
                    results=fut.result()
                    for r in results:
                        fout.write(r + "\n")
                futures=[]

        if batch: 
            futures.append(executor.submit(process_batch, batch))
            
        for fut in as_completed(futures): 
            results=fut.result()
            for r in results: 
                fout.write(r + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Input JSONL")
    parser.add_argument("output_file", help="Output JSONL")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--batch_size", type=int, default=500)
    args = parser.parse_args()
    
    print(f"Analysing {args.input_file}")
    print(f"Workers= {args.workers}, batch_size= {args.batch_size}")

    process_jsonl_parallel(args.input_file, args.output_file, batch_size=args.batch_size, workers=args.workers)
