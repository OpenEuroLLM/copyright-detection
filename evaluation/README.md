# Evaluation

This folder contains a small gold set and a script to score the filtering pipeline against it.

## Files

- `evaluate_finepdfs_pipeline.py`: compares gold labels with detector predictions.
- `finepdfs_test.jsonl`: 100-item gold evaluation set.

## How to run

1. Run the detector on the gold set to produce predictions with the expected metadata fields:

```bash
python ../detecting_licenses/detecting_licenses.py finepdfs_test.jsonl predictions.jsonl
```

2. Evaluate the predictions:

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

