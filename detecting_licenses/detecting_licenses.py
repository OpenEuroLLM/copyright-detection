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
This script processes a JSONL containing a "text" field, performing rule-based detection of licensing information. It identifies the license type of the text, classifies it as permissive or restrictive, and only when no license is detected, it applies heuristic methods to determine whether the text corresponds to a book and whether copyright indicators are present. The system is designed for large-scale corpus processing and supports parallel execution using multiprocessing to improve performance on multi-core systems. 
The output is written as a JSONL file where each input has the additional fields: 

    -"license": detected license identifier (e.g.: CC_BY, MIT, GPL)
    -"permit": license category ("permissive", "restrictive", or "unknown")
    -"is_book": boolean flag indicating whether the text is likely a book (computed only if license == "unknown")
    -"has_copyright": boolean flag indicating presence of copyright signals such as ISBNs, copyright keywords, or copyright dates (computed only if license == "unknown")

===Steps===
    1. Normalize the text to improve pattern matching consistency. 
    2. Extract and classify license information using predefined patterns. 
    3. If no license is found, apply heuristics to detect whether the text is a book. 
    4. Detect copyright indicators, including symbols, keywords, ISBNs, and dates. 
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

#1. ===NORMALIZATION=== 
def norm_text(text: str):
    normalized = []

    #Convert characters to lowercase, and remove accents, etc. 
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
    #Replace multiple spaces with single space
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    #Return normalized text
    return normalized_text

#2. ===LICENSES===
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

#3. ===PERMISSIVE/RESTRICTIVE?===
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

#4. ===EXTRACTION OF LICENSES AND ORIGINAL TEXT===
def extract_licenses(text: str):
    normalized_text = norm_text(text)

    # Search restrictive licenses first
    for name, pattern in CREATIVE_COMMONS.items():
        #Find all matches in the normalized text 
        if re.search(pattern, normalized_text):
            return name

    # Search CC BY fallback
    for name, pattern in CC_BY_FALLBACK.items():
        if re.search(pattern, normalized_text):
            return name
        
    # Search Permissive and GPL
    for name, pattern in {**PERMISSIVE_LICENSES, **RESTRICTIVE_LICENSES}.items():
        if re.search(pattern, normalized_text):
            return name
    
    #If not known license, return "unknown"
    return "unknown"

#Map licenses into permissive/restrictive
def get_permit_type(license_name: str) -> str:
    if license_name in PERMISSIVE_LICENSE_NAMES:
        return "permissive"
    elif license_name in RESTRICTIVE_LICENSE_NAMES:
        return "restrictive"
    else:
        return "unknown"

#5. ===ISBN===
#ISBN-10
ISBN10_REGEX = re.compile(r'\b\d{1,5}[- ]?\d{1,7}[- ]?\d{1,7}[- ]?[\dXx]\b')

# ISBN-13
ISBN13_REGEX = re.compile(r'\b97[89][- ]?\d{1,5}[- ]?\d{1,7}[- ]?\d{1,7}[- ]?\d\b')

#Does it have a valid ISBN?
def validate_isbn_10(isbn: str) -> bool:
    isbn = re.sub(r'[-\s]', '', isbn).upper()  # delete spaces and hyphens
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
    # ISBN-10
    for match in ISBN10_REGEX.finditer(text):
        if validate_isbn_10(match.group()):
            return True

    # ISBN-13
    for match in ISBN13_REGEX.finditer(text):
        if validate_isbn_13(match.group()):
            return True

    return False

#6. ===BOOK HEURISTICS===
# #Length
def has_book_length(text, min_caracteres=50_000):
    clean_text = re.sub(r"\s+", " ", text)
    chars = len(clean_text)
    return chars >= min_caracteres

#Narrative symbols (quotation, em dashes)
def has_narrative_symbols(text, ratio_min=0.0035):
    symbols = r'[\"“”‘’—–]'
    total = len(text)

    if total == 0:
        return False

    found  = len(re.findall(symbols, text))
    ratio = found / total

    return ratio >= ratio_min

#Frequent proper nouns
def ratio_proper_nouns(text):
    words = re.findall(r"\b\w+\b", text)

    if not words:
        return 0

    proper = 0

    for i, word in enumerate(words):
        if word[0].isupper():
            if i > 0 and not words[i-1].endswith(('.', '!', '?')):
                proper += 1

    return proper / len(words)

def has_frequent_proper_nouns(text, min_ratio=0.035):
    return ratio_proper_nouns(text) >= min_ratio

#Is it a book?
def is_book(text: str) -> bool:
    if has_valid_isbn(text):
        return True

    if has_book_length(text) and (
        has_narrative_symbols(text) or has_frequent_proper_nouns(text)
    ):
        return True

    return False

#7. ===Copyright===
COPYRIGHT_MAIN_REGEX = re.compile(
    r"""
    (?:©|Ⓒ|\(c\))                         # Symbols
    |(?:all\s+rights\s+reserved)           # All rights reserved
    |copyright(?!\s+exempt)                # Copyright
    |copyright\s+law                       # Copyright law
    |protected\s+by\s+copyright            # Protected by copyright
    |(?:free\s+)?intellectual\s+property(?!\s+free)  # Intellectual property
    """,
    re.IGNORECASE | re.VERBOSE
)

FORBIDDEN_PREFIX_WORDS = re.compile(
    r'\b(?:no|not)\b',
    re.IGNORECASE
)

def has_copyright(text: str) -> bool:
    for match in COPYRIGHT_MAIN_REGEX.finditer(text):
        start = match.start()
        #Check preceding word: if it is no or not, then it is discarded
        words_before = re.findall(r'\b\w+\b', text[:start])
        previous_word = words_before[-1].lower() if words_before else ""

        if FORBIDDEN_PREFIX_WORDS.search(previous_word):
            continue 
        return True
    return False

# 8. ===COPYRIGHT DATE===
def extract_years(text):
    DATE_REGEX = r"""
        # Numeric formats
        (\b(?: (?:18|19|20|21)?\d{2}[-/. ]\d{1,2}[-/. ]\d{1,2} )\b)   # YYYY-MM-DD or similar
        |(\b(?: \d{1,2}[-/. ]\d{1,2}[-/. ](?:\d{2}|\d{4}) )\b)        # DD-MM-YYYY or DD-MM-YY
        |
        # Text format: 18 April 1990, 18th of April 1990, 18-Apr-1990
        (\b\d{1,2}(?:st|nd|rd|th)?(?:[-,\s]*(?:of\s+)?)?(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)[-,\s]*\d{2,4}\b)
        |
        # Inverted text format: April 18, 1990 or Apr 18th 1990
        (\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)[-,\s]*\d{1,2}(?:st|nd|rd|th)?[-,\s]*\d{2,4}\b)
        |
        # ISO datetime
        (\b(?: (?:18|19|20|21)?\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})? )\b)
        |
        # Standalone year
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

    # Copyright keywords
    copyright_keywords = r"(©|Ⓒ|\(c\)|copyright|all\s+rights\s+reserved|no\s+part\s+of\s+this\s+book\s+may\s+be\s+reproduced)"
    
    for year in years:
        if year >= cutoff:
            # Year + keywords (20 characters before or after)
            pattern = re.compile(
                rf"{copyright_keywords}.{{0,20}}{year}|{year}.{{0,20}}{copyright_keywords}",
                re.IGNORECASE | re.DOTALL
            )
            if pattern.search(text):
                return True

    return False

#9. ===JSONL=== (not used, we use 10, with parallel processing)
def process_jsonl(input_path, output_path):

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for line in fin:
            if not line.strip():
                continue

            row = json.loads(line)
            text = row.get("text", "")

            # Check licenses
            license_name = extract_licenses(text)

            # Default values
            is_book_flag = False
            copyright_flag = False

            # If there are no licenses--> check if it's book and if it has copyright
            if license_name == "unknown":
                is_book_flag = is_book(text)
                copyright_flag = has_valid_isbn(text) or has_copyright(text) or has_date_copyright(text)

            permit_type = get_permit_type(license_name)

            row["license"] = license_name
            row["permit"]=permit_type
            row["is_book"] = is_book_flag
            row["has_copyright"] = copyright_flag

            fout.write(json.dumps(row, ensure_ascii=False) + "\n")

#10. ===Parallel processing===
def process_batch(batch_lines):
    output_lines=[]
    for line in batch_lines: 
        if not line.strip(): #Ignores if line is only whitespace
            continue
        try:
            row=json.loads(line)
        except Exception: #If a line has invalid JSONL, the line is ignored and processing continues
            continue
        text=row.get("text","") #We are going to work with the "text" column
        
        #Check licenses
        license_name=extract_licenses(text)

        #Default values 
        is_book_flag=False 
        copyright_flag=False

        if license_name=="unknown": #If no license is detected, then we check if instance is a book and if it has copyright
            is_book_flag=is_book(text)
            copyright_flag=(
                has_valid_isbn(text)
                or has_copyright(text)
                or has_date_copyright(text)
            )
        permit_type=get_permit_type(license_name) #Obtain name of license (if detected)

        #New columns
        row["license"]=license_name
        row["permit"]=permit_type
        row["is_book"]=is_book_flag
        row["has_copyright"]=copyright_flag

        output_lines.append(json.dumps(row,ensure_ascii=False))
    
    return output_lines

def process_jsonl_parallel (input_path, output_path, batch_size=500, workers=None):
    if workers is None: #If no worker count is provided, it defaults to the number of available CPU cores
        workers=multiprocessing.cpu_count()
    
    max_pending=workers*3 #Maximum number of pending tasks (futures) allowed at a time to prevent OOM
    
    with open(input_path,"r",encoding="utf-8") as fin, \
        open(output_path, "w", encoding="utf-8") as fout, \
        ProcessPoolExecutor(max_workers=workers) as executor: 
        futures=[] #List of submited tasks
        batch=[] #Batch: temporary storage for lines before submission
        for line in fin: 
            batch.append(line) #Read input line by line and add each line to current batch

            if len(batch) >= batch_size: #When batch reaches size, we submit the batch to the process pool for parallel execution, and store the resulting Future object
                futures.append(executor.submit(process_batch, batch))
                batch=[] #Reset the batch list for the next group of lines
            
            #Avoid too many "futures" --> OOM: if too many tasks are pending, the program pauses submission to process completed ones
            if len(futures) >= max_pending: 
                for fut in as_completed(futures): #Iterates over futures as they complete
                    results=fut.result() #Retrieves the processed results from the completed task
                    for r in results: #Write results 
                        fout.write(r + "\n")
                futures=[]

        #Last batch (might be an "incomplete" batch --> lines%batch_size!=0)
        if batch: 
            futures.append(executor.submit(process_batch, batch))
            
        for fut in as_completed(futures): 
            results=fut.result()
            for r in results: 
                fout.write(r + "\n")

#11. ===MAIN===
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