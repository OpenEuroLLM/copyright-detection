import json
import argparse
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

"""
====================================================
FILTERING RESTRICTIVE LICENSES AND COPYRIGHT CONTENT
====================================================
This script processes a JSONL file that has already been enriched with license and copyright detection metadata. It filters out instances containing restrictive licenses or copyright indicators and removes auxiliary analysis columns, keeping only the clean usable content. 
The output is written as a JSONL file, with the following deleted columns: 

    - "license"
    - "permit"
    - "is_book"
    - "has_copyright"

===Steps===
    1. Read the input JSONL file incrementally. 
    2. Filter out rows with restricive licenses (permit=="restrictive")
    3. Filter out rows flagged with copyright indicators (has_copyright == True). 
    4. Remove auxiliary metadata columns from remaining rows. 
    5. Write cleaned records to the output JSONL file. 

===Parallel execution===
To enable scalable processing of large datasets, the script supports parallel execution using ProcessPoolExecutor: 

    - The input file is read incrementally. 
    - Lines are grouped into batches (default configurable). 
    - Each batch is submitted to a pool of worker processes. 
    - The number of workers defaults to the number of available CPU cores. 
    - A controlled number of pending tasks (worker*3) prevents OOM. 
    - Results are written progressively as tasks complete.

===Usage===
python filter_restrictions.py <input.jsonl> <output.jonl> --workers N --batch_size N

===Arguments===
    input_file          Path to input JSONL file
    output_file         Path to output JSONL file
    --workers           Number of parallel worker processes (default: CPU count)
    --batch_size        Number of lines per batch (default: 1000)

"""

COLUMNS_TO_REMOVE = {"license", "permit", "is_book", "has_copyright"}

# 1. ===FILTERING AND DELETING ===
def process_batch(batch_lines):
    output_lines = []

    for line in batch_lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Filtering
        if row.get("permit") == "restrictive":
            continue
        if row.get("has_copyright") is True:
            continue
        if row.get("is_book") is True: 
            continue

        # Delete columns
        cleaned_row = {
            k: v for k, v in row.items()
            if k not in COLUMNS_TO_REMOVE
        }

        output_lines.append(json.dumps(cleaned_row, ensure_ascii=False))

    return output_lines

#2. === PARALLEL PROCESSING ===
def process_jsonl_parallel(input_path, output_path, batch_size=1000, workers=None):

    if workers is None: #If no worker count is provided, it defaults to the number of available CPU cores
        workers = multiprocessing.cpu_count()

    max_pending = workers * 3 #Maximum number of pending tasks (futures) allowed at a time to prevent OOM

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout, \
         ProcessPoolExecutor(max_workers=workers) as executor:

        futures = [] #List of submited tasks
        batch = [] #Batch: temporary storage for lines before submission

        for line in fin:
            batch.append(line) #Read input line by line and add each line to current batch

            if len(batch) >= batch_size: #When batch reaches size, we submit the batch to the process pool for parallel execution, and store the resulting Future object
                futures.append(executor.submit(process_batch, batch))
                batch = [] #Reset the batch list for the next group of lines

            #Avoid too many "futures" --> OOM: if too many tasks are pending, the program pauses submission to process completed ones
            if len(futures) >= max_pending:
                for fut in as_completed(futures): #Iterates over futures as they complete
                    results = fut.result() #Retrieves the processed results from the completed task
                    for r in results: #Write results
                        fout.write(r + "\n")
                futures = []

        ##Last batch (might be an "incomplete" batch --> lines%batch_size!=0)
        if batch:
            futures.append(executor.submit(process_batch, batch))

        for fut in as_completed(futures):
            results = fut.result()
            for r in results:
                fout.write(r + "\n")

# ========= MAIN =========
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("output_file")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--batch_size", type=int, default=1000)

    args = parser.parse_args()

    print(f"Processing: {args.input_file}")
    print(f"Workers={args.workers}, batch_size={args.batch_size}")

    process_jsonl_parallel(
        args.input_file,
        args.output_file,
        batch_size=args.batch_size,
        workers=args.workers
    )
