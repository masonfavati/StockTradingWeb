"""The existing opt-in Mac agent also evaluates matured journal records once daily."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis import forward_schedule_cli as cli


def run(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(sys, 'argv', [
        'forward_schedule_cli', 'run-once', '--dir', str(root),
    ])
    cli.main()


def test_outside_morning_window_never_loads_future_prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, 'scheduled_capture', lambda *_a, **_k: ('outside_window', None))
    monkeypatch.setattr(cli, 'evaluate_ready', lambda *_a, **_k: pytest.fail('No price fetch outside window'))
    run(monkeypatch, tmp_path)


def test_existing_agent_run_also_processes_up_to_five_matured_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, 'scheduled_capture', lambda *_a, **_k: ('already_registered', None))
    recorded = []

    def evaluate(root, *, limit):
        recorded.append((root, limit))
        return SimpleNamespace(evaluated=(), failed=(), skipped=9)

    monkeypatch.setattr(cli, 'evaluate_ready', evaluate)
    run(monkeypatch, tmp_path)
    assert recorded == [(tmp_path, 5)]


def test_outcome_failure_is_not_silently_hidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, 'scheduled_capture', lambda *_a, **_k: ('already_registered', None))
    monkeypatch.setattr(cli, 'evaluate_ready', lambda *_a, **_k: SimpleNamespace(
        evaluated=(), failed=('recorded maturity needs manual review',), skipped=1,
    ))
    with pytest.raises(SystemExit) as error:
        run(monkeypatch, tmp_path)
    assert error.value.code == 1
