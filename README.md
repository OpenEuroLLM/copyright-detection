# filtering_licenses

Pipeline for detecting licenses and copyright-related content in text corpora stored as JSONL, and for filtering out restrictive or copyrighted documents based on that detection. 

The process is split into two stages, each in its own folder:

| Stage | Folder | What it does |
|---|---|---|
|Detection | [`detecting_licenses/`](#1-detecting_licenses) | Analyzes documents and adds metadata about the detected license, whether it looks like a book, and whether it shows copyright indicators |
|Filtering | [`filtering/`](#2-filtering) | Removes documents with a restrictive license, flagged as a book, or flagged with copyright, and cleans up auxiliary columns |

The final result is a filtered, ready-to-use corpus, without the intermediate analysis columns.

> 💡 **TL;DR:** `raw JSONL` → detect → `license_*.jsonl` (+ metadata) → filter → `*.jsonl` (clean corpus)

---

## `licenses_list.txt`

Reference list of the license identifiers the system is able to recognize (**25** in total):

- **Permissive:** `CC0`, `CC_PDM`, `CC_BY`, `CC_BY_2`, `CC_BY_2_5`, `CC_BY_3`, `CC_BY_SA`, `CC_BY_SA_1`, `CC_BY_SA_2_1`, `CC_BY_SA_2_5`, `CC_BY_SA_3`, `PD`, `MIT`, `APACHE_2`, `BSD_2`, `BSD_3`, `ISC`, `ARTISTIC_2`, `GFDL`, `CDLA_P`, `OPL`
- **Restrictive:** `CC_BY_NC`, `CC_BY_NC_SA`, `CC_BY_ND`, `CC_BY_NC_ND`, `GPL`

---

## 1. `detecting_licenses/`

### Main script — `detecting_licenses.py`

Takes a JSONL with a `"text"` field and, for each document:

1. Normalizes the text (lowercase, no accents, homogeneous whitespace) to make pattern matching more consistent.
2. Searches for license patterns (regex) and determines the detected license.
3. If no license is detected (`unknown`), applies heuristics to estimate whether the text is a book and whether it shows copyright indicators (© symbols, "all rights reserved", a valid ISBN, recent copyright dates, etc.).
4. Classifies the license as `permissive`, `restrictive`, or `unknown`.
5. Writes the output JSONL adding these fields to each document.

**Fields added to each JSONL line:**

| Field | Type | Description |
|---|---|---|
|`license` | string | Detected license identifier (see `licenses_list.txt`), or `"unknown"` if none is detected |
|`permit` | string | `"permissive"`, `"restrictive"`, or `"unknown"`, based on the detected license |
|`is_book` | bool | Only computed if `license == "unknown"`. Indicates whether the text looks like a book (based on length, ISBN, narrative symbols, or proper-noun density) |
|`has_copyright` | bool | Only computed if `license == "unknown"`. Indicates copyright indicators (valid ISBN, copyright symbols/keywords, or a recent date associated with copyright) |

**Supported input:** JSONL, one document per line, with at least a `"text"` field (all other original fields are preserved as-is).

**Direct usage:**
```bash
python detecting_licenses.py input.jsonl output.jsonl --workers N --batch_size N
```
- `--workers`: number of parallel worker processes (defaults to all available CPU cores)
- `--batch_size`: lines per batch (default 500)

Processes the file in parallel using `ProcessPoolExecutor`, writing results incrementally to avoid loading everything into memory.

### `detecting_licenses.sh`

Slurm (`sbatch`) script that runs `detecting_licenses.py` on **one** specific JSONL. Takes the input and output file as arguments (`$1` and `$2`), activates the project's virtual environment, and runs the script with as many workers as CPUs assigned to the job (`$SLURM_CPUS_PER_TASK`). This is the script submitted to the queue once per file.

### `orchestrator_licenses.py` — the orchestrator

Automates the mass submission of Slurm jobs for an entire data directory:

1. Recursively searches for all `.jsonl` files in the input directory.
2. Builds the output paths, mirroring the same folder structure, prefixing each filename with `license_` (e.g. `folder/doc.jsonl` → `folder/license_doc.jsonl`).
3. Before submitting each job, checks via `squeue` that the user doesn't have more than 100 active jobs (`MAX_ACTIVE_JOBS`); if that limit is exceeded, it waits 2 minutes and checks again.
4. Submits jobs in batches of 100 files, calling `sbatch detecting_licenses.sh <input> <output>` for each JSONL.
5. Prints the result of each batch to the console (submitted successfully or with an error).

**Usage:**
```bash
python orchestrator_licenses.py <input_directory> <output_directory>
```
The output directory is created automatically if it doesn't exist.

### `launcher.sh`

Slurm script that launches `orchestrator_licenses.py` itself as a job (instead of running it on the login node), with the input/output paths already set inside the script. This is the actual entry point for kicking off the whole detection process over a full directory.

---

## 2. `filtering/`

### Main script — `filtering_restrictions.py`

Takes a JSONL already enriched by `detecting_licenses.py` (i.e. containing the `license`, `permit`, `is_book`, `has_copyright` fields) and produces a clean JSONL:

1. Drops rows with `permit == "restrictive"`.
2. Drops rows with `has_copyright == True`.
3. Drops rows with `is_book == True`.
4. Removes the auxiliary columns (`license`, `permit`, `is_book`, `has_copyright`) from the surviving rows.
5. Writes the result to the output JSONL, keeping only the document's original fields.

**Supported input:** JSONL produced by the previous stage, containing the 4 metadata fields mentioned above (in addition to `"text"` and the rest of the original fields).

**Direct usage:**
```bash
python filtering_restrictions.py input.jsonl output.jsonl --workers N --batch_size N
```
- `--workers`: number of parallel worker processes (defaults to all available CPU cores)
- `--batch_size`: lines per batch (default 1000)

As in the previous stage, processing is parallel and incremental.

### `filtering_restrictions.sh`

Slurm script equivalent to `detecting_licenses.sh`, but for this stage: runs `filtering_restrictions.py` on a single input/output JSONL (`$1`/`$2`), with the environment and worker count matching the job.

### `orchestrator_filtering.py` — the orchestrator

Same logic as `orchestrator_licenses.py`, adapted to this stage:

1. Recursively searches for all `.jsonl` files in the input directory (expected to be the output of the detection stage).
2. Builds the output paths, mirroring the folder structure, **without** any prefix (the filename stays the same).
3. Controls the number of active Slurm jobs the same way as the previous stage (max 100, 2-minute wait if exceeded).
4. Submits jobs in batches of 100, calling `sbatch filtering_restrictions.sh <input> <output>`.
5. Reports the result of each batch.

**Usage:**
```bash
python orchestrator_filtering.py <input_directory> <output_directory>
```

### `launcher.sh`

Slurm script that launches `orchestrator_filtering.py` as a job, with the input path (output of the detection stage) and output path (final filtered corpus) already set.

---

## 🔄 End-to-end workflow

```
1. 🔍 detecting_licenses/launcher.sh
   → orchestrator_licenses.py <raw_dir> <detected_dir>
   → for each .jsonl: sbatch detecting_licenses.sh <input> <output>
   → output: detected_dir/.../license_<name>.jsonl  (with license, permit, is_book, has_copyright)

2. 🧹 filtering/launcher.sh
   → orchestrator_filtering.py <detected_dir> <filtered_dir>
   → for each .jsonl: sbatch filtering_restrictions.sh <input> <output>
   → output: filtered_dir/.../<name>.jsonl  (clean corpus, no metadata columns) ✅
```

> ⚠️ **Note:** input/output paths and the `#SBATCH` headers (partition, account, qos, time, virtual environment) are set for the BSC cluster environment. If this pipeline is reused elsewhere, those paths and parameters need to be adjusted in the `.sh` scripts.
