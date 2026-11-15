"""One predeclared, read-only prospective prediction research protocol.

Training examples come ONLY from previously frozen scanner candidates paired
with independently verified, already-matured forward outcomes. No fabricated
historical scans, backfilled features, forward-price lookups or in-sample
performance claims. This is a selective research cohort, NOT the entire market.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.analysis.forward_evaluation import load_checkpoint
from app.analysis.forward_outcomes import _read_existing, outcome_status
from app.analysis.forward_performance import _verified_observation
from app.analysis.forward_record import SCANNER_RULE_ID

MODEL_VERSION = "prospective-conditional-logit-v1"
HORIZON = 20
FEATURES = (
    "return_20d_pct", "return_60d_pct", "annualized_volatility_pct",
    "drawdown_60d_pct", "approx_daily_dollar_volume", "research_score",
)
MIN_TRAIN_WINDOWS = 30
MIN_TRAIN_ROWS = 200
VALIDATION_CALENDAR_STRIDE = 5
MIN_OOS_WINDOWS = 20
MIN_OOS_ROWS = 200
MIN_DISJOINT_WINDOWS = 8
MIN_BRIER_GAIN = 0.002
MIN_STOCK_PROBABILITY = 0.55
MIN_PRIOR_LIFT = 0.03
MAX_JOURNAL_WINDOWS = 3000


class PredictionEvidenceError(ValueError):
    """Inconsistent recorded evidence must not publish a prediction."""


@dataclass(frozen=True)
class Observation:
    symbol: str
    signal: date
    entry: date
    exit: date
    features: tuple[float, ...]
    beat_spy: int
    excess_pp: float


@dataclass(frozen=True)
class Window:
    signal: date
    exit: date
    observations: tuple[Observation, ...]
    checkpoint_sha256: str
    outcome_sha256: str


def _safe_number(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise PredictionEvidenceError(f"Frozen {label} is missing or nonfinite")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise PredictionEvidenceError(f"Frozen {label} is outside numeric bounds") from exc
    if not math.isfinite(number):
        raise PredictionEvidenceError(f"Frozen {label} is missing or nonfinite")
    if abs(number) > 1e15:
        raise PredictionEvidenceError(f"Frozen {label} is outside supported bounds")
    return number


def _features(row: Mapping[str, Any]) -> tuple[float, ...]:
    fields = [_safe_number(row.get(key), key) for key in FEATURES]
    if fields[4] <= 0 or fields[2] < 0 or fields[3] > 0:
        raise PredictionEvidenceError("Frozen candidate contains implausible research metrics")
    r20, r60, vol, drawdown, volume, score = fields
    # Fixed scales and clipping are declared BEFORE evaluating future outcomes.
    raw = (r20 / 20, r60 / 50, vol / 80, drawdown / 30,
           math.log1p(volume) / 20, score)
    return tuple(max(-3.0, min(3.0, x)) for x in raw)


def _net_pct(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise PredictionEvidenceError(f"{label} must be an audited decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise PredictionEvidenceError(f"{label} is not numerical") from exc
    if not number.is_finite():
        raise PredictionEvidenceError(f"{label} is not finite")
    return number


def _unique_json_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in items:
        if key in seen:
            raise PredictionEvidenceError("Frozen scanner input contains a duplicate JSON key")
        seen[key] = value
    return seen


def _reject_nonfinite_json(_value: str) -> None:
    raise PredictionEvidenceError("Frozen scanner input contains a nonfinite JSON number")


def load_verified_windows(root: Path, *, now: datetime | None = None) -> tuple[list[Window], dict[str, int]]:
    """Verify the entire journal; never silently omit a corrupted COMPLETE audit."""
    states = outcome_status(root, now=now)
    if len(states) > MAX_JOURNAL_WINDOWS:
        raise PredictionEvidenceError("Research journal exceeds prediction audit capacity")
    counts = {name: sum(s.state == name for s in states) for name in
              ("PENDING", "READY", "COMPLETE", "INCOMPLETE", "NO_SELECTION")}
    windows: list[Window] = []
    for item in states:
        cp = item.row.entry.checkpoint
        if cp.research_rule != SCANNER_RULE_ID or cp.horizon != HORIZON:
            continue  # Never pool incompatible research protocols or horizons.
        if item.state != "COMPLETE":
            continue
        validated = _verified_observation(item)  # Independently rechecks price arithmetic.
        path = item.row.entry.record_path
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
            raise PredictionEvidenceError("Unsafe frozen source record")
        try:
            body = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_json_pairs,
                parse_constant=_reject_nonfinite_json,
            )
        except (ValueError, UnicodeError) as exc:
            raise PredictionEvidenceError("Frozen candidate record is unreadable") from exc
        if not isinstance(body, dict):
            raise PredictionEvidenceError("Frozen scanner record must be an object")
        unsigned = {key: value for key, value in body.items() if key != "content_sha256"}
        digest = hashlib.sha256(json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        if (body.get("content_sha256") != item.row.entry.expected_sha256
                or digest != item.row.entry.expected_sha256):
            raise PredictionEvidenceError("Frozen scanner SHA-256 mismatch")
        load_checkpoint(path, expected_checksum=item.row.entry.expected_sha256)
        frozen = body.get("shortlist")
        if not isinstance(frozen, list) or len(frozen) != len(cp.shortlist):
            raise PredictionEvidenceError("Incomplete frozen scanner features")
        audited = _read_existing(item.audit_path, item.row.entry)
        benchmark = _net_pct(audited["benchmark_outcome"]["net_return_pct"], "SPY net return")
        selected = audited["selected_outcomes"]
        data: list[Observation] = []
        for index, ticker in enumerate(cp.shortlist):
            candidate, actual = frozen[index], selected[index]
            if not isinstance(candidate, dict) or candidate.get("symbol") != ticker:
                raise PredictionEvidenceError("Frozen feature order differs from registered shortlist")
            if actual.get("symbol") != ticker or actual.get("status") != "complete":
                raise PredictionEvidenceError("Outcome order or completion does not match frozen input")
            observed = _net_pct(actual.get("net_return_pct"), f"{ticker} net return")
            data.append(Observation(
                ticker, cp.signal_session, validated.entry, validated.exit,
                _features(candidate), int(observed > benchmark), float(observed - benchmark),
            ))
        if not data:
            raise PredictionEvidenceError("Complete checkpoint has no training candidates")
        windows.append(Window(
            cp.signal_session, validated.exit, tuple(data),
            item.row.entry.expected_sha256, audited["content_sha256"],
        ))
    windows.sort(key=lambda row: row.signal)
    if len({row.signal for row in windows}) != len(windows):
        raise PredictionEvidenceError("Multiple compatible outcomes share one signal date")
    return windows, counts


def _sigmoid(value: float) -> float:
    value = min(30.0, max(-30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _probability(weights: Sequence[float], features: Sequence[float]) -> float:
    return _sigmoid(weights[0] + sum(a * b for a, b in zip(weights[1:], features, strict=True)))


def _training_rows(windows: Sequence[Window]) -> list[Observation]:
    return [item for window in windows for item in window.observations]


def _fit(training: Sequence[Observation]) -> list[float]:
    """Deterministic, fixed-regularization logistic regression; no hyperparameter search."""
    if len(training) < MIN_TRAIN_ROWS or len({row.signal for row in training}) < MIN_TRAIN_WINDOWS:
        raise PredictionEvidenceError("Insufficient independent signal dates for training")
    weights = [0.0] * (len(FEATURES) + 1)
    # Each frozen DAILY scan gets equal weight, even if its shortlist is shorter.
    counts: dict[date, int] = {}
    for row in training:
        counts[row.signal] = counts.get(row.signal, 0) + 1
    number = len(counts)
    for _iteration in range(250):
        gradients = [0.0] * len(weights)
        for row in training:
            error = (_probability(weights, row.features) - row.beat_spy) / (number * counts[row.signal])
            gradients[0] += error
            for index, value in enumerate(row.features, start=1):
                gradients[index] += error * value
        weights[0] -= 0.25 * gradients[0]
        for index in range(1, len(weights)):
            weights[index] -= 0.25 * (gradients[index] + 0.15 * weights[index])
    return weights


def _can_fit(windows: Sequence[Window]) -> bool:
    rows = _training_rows(windows)
    targets = sum(row.beat_spy for row in rows)
    return (
        len(windows) >= MIN_TRAIN_WINDOWS
        and len(rows) >= MIN_TRAIN_ROWS
        and targets >= 20
        and len(rows) - targets >= 20
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _disjoint_windows(windows: Sequence[Window]) -> int:
    previous_exit: date | None = None
    result = 0
    for item in sorted(windows, key=lambda window: (window.exit, window.signal)):
        if previous_exit is None or item.signal > previous_exit:
            result += 1
            previous_exit = item.exit
    return result


def _round(value: float) -> float:
    return round(value, 6)


def evaluate_walk_forward(windows: Sequence[Window]) -> dict[str, Any]:
    """Test sequentially; training outcomes must EXIT before test SIGNAL.

    No random shuffled train/test splits. Horizon-overlapping test windows stay
    visible and are not asserted to be statistically independent.
    """
    oos: list[Window] = []
    model_errors: list[float] = []
    prior_errors: list[float] = []
    top2_excess: list[float] = []
    scanner_top2_excess: list[float] = []
    higher_than_spy = 0
    predicted_rows = 0
    for tested in windows:
        # Predeclared date-only fold sampling bounds read-only web latency.
        # The selection is independent of prices, model output, or future labels.
        if tested.signal.toordinal() % VALIDATION_CALENDAR_STRIDE:
            continue
        trained = [row for row in windows if row.exit < tested.signal]
        if not _can_fit(trained):
            continue
        examples = _training_rows(trained)
        weights = _fit(examples)
        prior = _mean([float(row.beat_spy) for row in examples])
        scored = [(item, _probability(weights, item.features)) for item in tested.observations]
        for item, probability in scored:
            model_errors.append((probability - item.beat_spy) ** 2)
            prior_errors.append((prior - item.beat_spy) ** 2)
        ranked = sorted(scored, key=lambda row: (-row[1], row[0].symbol))[:2]
        historic_rank = tested.observations[:2]
        selected_excess = _mean([row.excess_pp for row, _prob in ranked])
        top2_excess.append(selected_excess)
        scanner_top2_excess.append(_mean([row.excess_pp for row in historic_rank]))
        higher_than_spy += int(selected_excess > 0)
        predicted_rows += len(scored)
        oos.append(tested)
    disjoint = _disjoint_windows(oos)
    brier = _mean(model_errors) if model_errors else None
    prior_brier = _mean(prior_errors) if prior_errors else None
    mean_excess = _mean(top2_excess) if top2_excess else None
    vs_scanner = _mean([a - b for a, b in zip(top2_excess, scanner_top2_excess, strict=True)]) if oos else None
    gates = {
        "at_least_20_walk_forward_windows": len(oos) >= MIN_OOS_WINDOWS,
        "at_least_200_tested_candidates": predicted_rows >= MIN_OOS_ROWS,
        "at_least_8_nonoverlapping_holding_windows": disjoint >= MIN_DISJOINT_WINDOWS,
        "better_brier_than_expanding_training_prior": (
            brier is not None and prior_brier is not None
            and prior_brier - brier >= MIN_BRIER_GAIN
        ),
        "positive_average_top_two_excess_vs_spy": mean_excess is not None and mean_excess > 0,
        "not_worse_than_original_scan_top_two": vs_scanner is not None and vs_scanner >= 0,
    }
    return {
        "validation_windows": len(oos),
        "validation_candidates": predicted_rows,
        "nonoverlapping_validation_windows": disjoint,
        "brier_score": _round(brier) if brier is not None else None,
        "expanding_prior_brier_score": _round(prior_brier) if prior_brier is not None else None,
        "brier_improvement": _round(prior_brier - brier) if brier is not None and prior_brier is not None else None,
        "top_two_mean_excess_vs_spy_pp": _round(mean_excess) if mean_excess is not None else None,
        "top_two_mean_vs_original_scan_pp": _round(vs_scanner) if vs_scanner is not None else None,
        "top_two_windows_beating_spy": higher_than_spy,
        "checks": gates,
        "research_gate_passed": all(gates.values()),
    }


def report_from_verified_windows(
    windows: Sequence[Window], counts: Mapping[str, int],
) -> dict[str, Any]:
    """Compute a reproducible report over one immutable audited snapshot."""
    validation = evaluate_walk_forward(windows)
    rows = _training_rows(windows)
    # Canonical digest ties each model report to its exact known input audit set.
    provenance = hashlib.sha256(json.dumps([
        [row.signal.isoformat(), row.checkpoint_sha256, row.outcome_sha256]
        for row in windows
    ], separators=(",", ":")).encode()).hexdigest()
    return {
        "version": MODEL_VERSION,
        "target": "Selected stock beats SPY, net of the same assumed costs, over 20 exchange sessions",
        "research_rule": SCANNER_RULE_ID,
        "holding_sessions": HORIZON,
        "status": (
            "research_gate_passed" if validation["research_gate_passed"]
            else "not_validated" if validation["validation_windows"] else "insufficient_evidence"
        ),
        "source_sha256": provenance,
        "completed_compatible_windows": len(windows),
        "completed_candidate_outcomes": len(rows),
        "journal_status_counts": counts,
        "walk_forward": validation,
        "method": (
            "Fixed-feature L2-regularized logistic regression. Expanding walk-forward folds "
            "fit only using outcomes with exit before each test signal. Fixed 20-session target, "
            "10-bps cost each side, no hyperparameter search and no historical-data backfill."
        ),
        "warnings": [
            "Frozen scanner selections are a selected cohort, not a representative sample of the entire US market.",
            "Research-gate passage is not statistical proof of future profit, model calibration or recommendation suitability.",
            "Walk-forward evaluation uses every fifth calendar-ordinal date, selected before seeing outcomes; test holding windows can still overlap.",
            "Eight date-disjoint evaluation windows are a minimum coverage gate, not eight independent proof events.",
            "Predictive probabilities concern beating SPY only, not rising in price or producing a dollar return.",
            "Survivorship, corporate actions, missing outcomes, transaction friction, and regime change remain risks.",
            "Only audited completed outcomes enter training. Pending and incomplete records are never treated as wins or losses.",
            "The tool is read-only; the local journal has no independent cryptographic timestamp attestation.",
        ],
    }


def build_prediction_report(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    windows, counts = load_verified_windows(root, now=now)
    return report_from_verified_windows(windows, counts)


def unavailable_prediction(symbols: Sequence[str], *, status: str = "unavailable") -> dict[str, Any]:
    return {
        "version": MODEL_VERSION,
        "status": status,
        "requested_symbols": list(symbols),
        "proposed_slot_count": min(2, len(symbols)),
        "approved_symbols": [],
        "scores": [],
        "excluded": [{"symbol": symbol, "reason": "no_published_predictive_evidence"} for symbol in symbols],
        "validation": None,
        "caveat": "No prospectively validated model evidence; proposed individual-stock dollars remain cash.",
    }


def review_prediction(
    candidates: Sequence[Mapping[str, Any]], source_session: str | None,
    windows: Sequence[Window], report: Mapping[str, Any],
) -> dict[str, Any]:
    """For already quality-screened candidates, publish ONLY if research gate passes.

    A fresh model uses labels exited before the proposed signal. No re-ranking
    of unvetted equities or extra provider calls occurs.
    """
    symbols = [row["symbol"] for row in candidates if isinstance(row.get("symbol"), str)]
    if not symbols or source_session is None:
        return unavailable_prediction(symbols, status="not_applicable")
    try:
        signal = date.fromisoformat(source_session)
    except ValueError:
        return unavailable_prediction(symbols)
    # The global dashboard report may know outcomes unavailable at this scan's
    # signal. Reassess the fixed validation gates using ONLY earlier labels.
    training = [window for window in windows if window.exit < signal]
    if not _can_fit(training):
        return unavailable_prediction(symbols, status="insufficient_training_before_signal")
    # Reuse the already-audited validation whenever it contains NO observations
    # unavailable before this candidate's signal. Historical preview requests
    # re-evaluate against their own earlier cutoff to avoid hindsight gating.
    if len(training) == len(windows) and isinstance(report.get("walk_forward"), dict):
        local_validation = report["walk_forward"]
    else:
        local_validation = evaluate_walk_forward(training)
    if not local_validation["research_gate_passed"]:
        return unavailable_prediction(symbols, status="not_validated_before_signal")
    examples = _training_rows(training)
    weights = _fit(examples)
    prior = _mean([float(item.beat_spy) for item in examples])
    approved: list[str] = []
    scores: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for candidate in candidates:
        symbol = candidate.get("symbol")
        if not isinstance(symbol, str):
            continue
        try:
            features = _features(candidate)
        except PredictionEvidenceError:
            excluded.append({"symbol": symbol, "reason": "missing_frozen_model_features"})
            continue
        p = _probability(weights, features)
        scores.append({
            "symbol": symbol, "estimated_probability_beating_spy": round(p, 4),
            "training_prior": round(prior, 4),
        })
        if p >= MIN_STOCK_PROBABILITY and p >= prior + MIN_PRIOR_LIFT:
            approved.append(symbol)
        else:
            excluded.append({"symbol": symbol, "reason": "below_predeclared_model_threshold"})
    return {
        "version": MODEL_VERSION,
        "status": "research_gate_passed",
        "requested_symbols": symbols,
        "proposed_slot_count": min(2, len(symbols)),
        "approved_symbols": approved,
        "scores": scores,
        "excluded": excluded,
        "training_windows": len(training),
        "training_candidate_outcomes": len(examples),
        "validation": local_validation,
        "source_sha256": report.get("source_sha256"),
        "caveat": (
            "Conditional outperformance estimates are experimental, based only on past selected "
            "stocks. They are not calibrated investment probabilities or price predictions; "
            "all existing eligibility, concentration and loss limits still apply."
        ),
    }
