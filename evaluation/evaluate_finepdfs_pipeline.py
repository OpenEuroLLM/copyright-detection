#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Evaluate FinePDFs rule-based filtering predictions against human gold labels.

Inputs:
- Gold JSONL containing `_evaluation_id` and gold fields.
- Prediction JSONL containing `_evaluation_id`, `license`, `permit`,
  `is_book`, and `has_copyright`.

Outputs:
- evaluation_summary.json
- evaluation_report.md
- false_positives.jsonl
- false_negatives.jsonl
- all_errors.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate FinePDFs licence-filter predictions."
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fin:
        for line_number, line in enumerate(fin, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def norm_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def norm_lower(value: Any) -> str:
    return norm_text(value).casefold()


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return norm_lower(value) in {"true", "1", "yes"}


def get_id(row: dict[str, Any]) -> str:
    value = row.get("_evaluation_id") or row.get("evaluation_id") or row.get("id")
    value = norm_text(value)
    if not value:
        raise ValueError("Record without evaluation ID")
    return value


def predicted_decision(row: dict[str, Any]) -> str:
    restrictive = norm_lower(row.get("permit")) == "restrictive"
    is_book = bool_value(row.get("is_book"))
    has_copyright = bool_value(row.get("has_copyright"))
    return "FILTER" if restrictive or is_book or has_copyright else "KEEP"


def safe_div(num: int | float, den: int | float) -> float:
    return float(num) / float(den) if den else 0.0


def binary_metrics(y_true: list[bool], y_pred: list[bool]) -> dict[str, Any]:
    if len(y_true) != len(y_pred):
        raise ValueError("Gold and prediction lengths differ")

    tp = sum(t and p for t, p in zip(y_true, y_pred))
    tn = sum((not t) and (not p) for t, p in zip(y_true, y_pred))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred))

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    accuracy = safe_div(tp + tn, len(y_true))
    specificity = safe_div(tn, tn + fp)

    return {
        "n": len(y_true),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "specificity": specificity,
    }


def language_group(row: dict[str, Any]) -> str:
    value = (
        row.get("_sample_language")
        or row.get("language")
        or row.get("page_average_lid")
        or "UNKNOWN"
    )
    value = norm_text(value)

    if value in {"EN", "ES"}:
        return value
    if value.startswith("eng"):
        return "EN"
    if value.startswith("spa"):
        return "ES"
    return value or "UNKNOWN"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fout:
        for row in rows:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")


def fmt_pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def metric_table(title: str, metrics: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"## {title}",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| N | {metrics['n']} |",
            f"| TP | {metrics['tp']} |",
            f"| TN | {metrics['tn']} |",
            f"| FP | {metrics['fp']} |",
            f"| FN | {metrics['fn']} |",
            f"| Precision | {fmt_pct(metrics['precision'])} |",
            f"| Recall | {fmt_pct(metrics['recall'])} |",
            f"| F1 | {fmt_pct(metrics['f1'])} |",
            f"| Accuracy | {fmt_pct(metrics['accuracy'])} |",
            f"| Specificity | {fmt_pct(metrics['specificity'])} |",
            "",
        ]
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    gold_rows = load_jsonl(args.gold)
    pred_rows = load_jsonl(args.predictions)

    gold_by_id: dict[str, dict[str, Any]] = {}
    pred_by_id: dict[str, dict[str, Any]] = {}

    for row in gold_rows:
        evaluation_id = get_id(row)
        if evaluation_id in gold_by_id:
            raise ValueError(f"Duplicate gold ID: {evaluation_id}")
        gold_by_id[evaluation_id] = row

    for row in pred_rows:
        evaluation_id = get_id(row)
        if evaluation_id in pred_by_id:
            raise ValueError(f"Duplicate prediction ID: {evaluation_id}")
        pred_by_id[evaluation_id] = row

    missing_predictions = sorted(set(gold_by_id) - set(pred_by_id))
    extra_predictions = sorted(set(pred_by_id) - set(gold_by_id))

    if missing_predictions:
        raise ValueError(
            "Missing predictions for: " + ", ".join(missing_predictions)
        )
    if extra_predictions:
        raise ValueError(
            "Predictions without gold records: " + ", ".join(extra_predictions)
        )

    merged: list[dict[str, Any]] = []
    excluded_unclear: list[str] = []

    for evaluation_id, gold in gold_by_id.items():
        pred = pred_by_id[evaluation_id]
        gold_decision = norm_text(gold.get("gold_decision")).upper()
        pred_decision = predicted_decision(pred)

        row = {
            **gold,
            "pred_license": pred.get("license"),
            "pred_permit": pred.get("permit"),
            "pred_is_book": bool_value(pred.get("is_book")),
            "pred_has_copyright": bool_value(pred.get("has_copyright")),
            "pred_decision": pred_decision,
        }

        if gold_decision in {"FILTER", "KEEP"}:
            row["decision_correct"] = gold_decision == pred_decision
        else:
            row["decision_correct"] = None
            excluded_unclear.append(evaluation_id)

        merged.append(row)

    eval_rows = [
        row for row in merged
        if norm_text(row.get("gold_decision")).upper() in {"FILTER", "KEEP"}
    ]

    y_true_filter = [
        norm_text(row["gold_decision"]).upper() == "FILTER"
        for row in eval_rows
    ]
    y_pred_filter = [
        row["pred_decision"] == "FILTER"
        for row in eval_rows
    ]
    decision_metrics = binary_metrics(y_true_filter, y_pred_filter)

    by_language: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eval_rows:
        grouped[language_group(row)].append(row)

    for lang, rows in sorted(grouped.items()):
        by_language[lang] = binary_metrics(
            [
                norm_text(row["gold_decision"]).upper() == "FILTER"
                for row in rows
            ],
            [row["pred_decision"] == "FILTER" for row in rows],
        )

    component_metrics: dict[str, dict[str, Any]] = {}

    # Restrictive-licence detection
    gold_vals: list[bool] = []
    pred_vals: list[bool] = []
    for row in merged:
        gold_value = norm_text(row.get("gold_permit")).upper()
        if not gold_value or gold_value == "UNCLEAR":
            continue
        gold_vals.append(gold_value == "RESTRICTIVE")
        pred_vals.append(norm_lower(row.get("pred_permit")) == "restrictive")
    component_metrics["restrictive_license"] = binary_metrics(gold_vals, pred_vals)

    # Book detection
    gold_vals = []
    pred_vals = []
    for row in merged:
        gold_value = norm_text(row.get("gold_is_book")).upper()
        if gold_value not in {"YES", "NO"}:
            continue
        gold_vals.append(gold_value == "YES")
        pred_vals.append(bool_value(row.get("pred_is_book")))
    component_metrics["is_book"] = binary_metrics(gold_vals, pred_vals)

    # Copyright-restriction detection
    gold_vals = []
    pred_vals = []
    for row in merged:
        gold_value = norm_text(row.get("gold_has_copyright")).upper()
        if gold_value not in {"YES", "NO"}:
            continue
        gold_vals.append(gold_value == "YES")
        pred_vals.append(bool_value(row.get("pred_has_copyright")))
    component_metrics["has_copyright"] = binary_metrics(gold_vals, pred_vals)

    false_positives = [
        row for row in eval_rows
        if norm_text(row["gold_decision"]).upper() == "KEEP"
        and row["pred_decision"] == "FILTER"
    ]
    false_negatives = [
        row for row in eval_rows
        if norm_text(row["gold_decision"]).upper() == "FILTER"
        and row["pred_decision"] == "KEEP"
    ]
    all_errors = false_positives + false_negatives

    error_reason_counts = Counter()
    for row in all_errors:
        if bool_value(row.get("pred_is_book")):
            error_reason_counts["predicted_book"] += 1
        if bool_value(row.get("pred_has_copyright")):
            error_reason_counts["predicted_copyright"] += 1
        if norm_lower(row.get("pred_permit")) == "restrictive":
            error_reason_counts["predicted_restrictive_license"] += 1
        if row["pred_decision"] == "KEEP":
            error_reason_counts["predicted_no_filter_signal"] += 1

    summary = {
        "gold_records": len(gold_rows),
        "prediction_records": len(pred_rows),
        "evaluated_decision_records": len(eval_rows),
        "excluded_unclear_decisions": excluded_unclear,
        "gold_decision_counts": dict(
            Counter(norm_text(row.get("gold_decision")).upper() for row in merged)
        ),
        "predicted_decision_counts": dict(
            Counter(row["pred_decision"] for row in merged)
        ),
        "decision_metrics_filter_positive": decision_metrics,
        "decision_metrics_by_language": by_language,
        "component_metrics": component_metrics,
        "false_positive_count": len(false_positives),
        "false_negative_count": len(false_negatives),
        "error_signal_counts": dict(error_reason_counts),
    }

    with (args.output_dir / "evaluation_summary.json").open(
        "w", encoding="utf-8"
    ) as fout:
        json.dump(summary, fout, ensure_ascii=False, indent=2)

    write_jsonl(args.output_dir / "false_positives.jsonl", false_positives)
    write_jsonl(args.output_dir / "false_negatives.jsonl", false_negatives)
    write_jsonl(args.output_dir / "all_errors.jsonl", all_errors)

    report_parts = [
        "# FinePDFs filtering-pipeline evaluation",
        "",
        f"- Gold records: **{len(gold_rows)}**",
        f"- Prediction records: **{len(pred_rows)}**",
        f"- Evaluated FILTER/KEEP records: **{len(eval_rows)}**",
        f"- Excluded UNCLEAR decisions: **{len(excluded_unclear)}**",
        "",
        metric_table(
            "Overall FILTER decision — FILTER is the positive class",
            decision_metrics,
        ),
    ]

    for lang, metrics in sorted(by_language.items()):
        report_parts.append(metric_table(f"FILTER decision — {lang}", metrics))

    report_parts.extend(
        [
            metric_table(
                "Restrictive-licence detection",
                component_metrics["restrictive_license"],
            ),
            metric_table(
                "Book detection",
                component_metrics["is_book"],
            ),
            metric_table(
                "Copyright-restriction detection",
                component_metrics["has_copyright"],
            ),
            "## Error counts",
            "",
            f"- False positives: **{len(false_positives)}**",
            f"- False negatives: **{len(false_negatives)}**",
            "",
            "### Prediction signals present in errors",
            "",
        ]
    )

    if error_reason_counts:
        for key, count in error_reason_counts.most_common():
            report_parts.append(f"- {key}: **{count}**")
    else:
        report_parts.append("- No errors.")

    report_parts.append("")

    with (args.output_dir / "evaluation_report.md").open(
        "w", encoding="utf-8"
    ) as fout:
        fout.write("\n".join(report_parts))

    print(f"Gold records: {len(gold_rows)}")
    print(f"Prediction records: {len(pred_rows)}")
    print(f"Evaluated decision records: {len(eval_rows)}")
    print(f"Excluded UNCLEAR decisions: {len(excluded_unclear)}")
    print()
    print("Overall FILTER metrics:")
    print(json.dumps(decision_metrics, indent=2))
    print()
    print(f"False positives: {len(false_positives)}")
    print(f"False negatives: {len(false_negatives)}")
    print()
    print(f"Results written to: {args.output_dir}")


if __name__ == "__main__":
    main()
