# Evaluation

This folder contains a small test set based on a FinePDFs dataset sample and a script to score the filtering pipeline against it.

## Files

- `evaluate_finepdfs_pipeline.py`: compares gold labels with detector predictions.
- `finepdfs_test.jsonl`: 100-item gold evaluation set.

## How to run

1. Run the detector as a Slurm job on the test set to produce predictions with the expected metadata fields.

   Use the detector wrapper from `detecting_licenses/` and pass the test file and output path as arguments. If you are not on the BSC paths encoded in that script, adjust the hard-coded locations first or create a small local copy of the job script for the evaluation run.

```bash
sbatch ../detecting_licenses/detecting_licenses.sh finepdfs_test.jsonl predictions.jsonl
```

2. Evaluate the predictions once the Slurm job has finished and written `predictions.jsonl`:

```bash
python evaluate_finepdfs_pipeline.py --gold finepdfs_test.jsonl --predictions predictions.jsonl --output-dir results
```

## Output

The evaluator writes these files into the output directory:

- `evaluation_summary.json`
- `evaluation_report.md`
- `false_positives.jsonl`
- `false_negatives.jsonl`
- `all_errors.jsonl`
