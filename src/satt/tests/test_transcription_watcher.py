"""Unit tests for watcher claim ownership and failure behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import threading
import types

import pytest


@pytest.fixture
def watcher(monkeypatch):
    watchdog = types.ModuleType("watchdog")
    events = types.ModuleType("watchdog.events")
    observers = types.ModuleType("watchdog.observers")

    class FileSystemEventHandler:
        pass

    class Observer:
        pass

    events.FileSystemEventHandler = FileSystemEventHandler
    observers.Observer = Observer
    monkeypatch.setitem(sys.modules, "watchdog", watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", observers)

    path = Path(__file__).resolve().parents[3] / "scripts" / "watch.py"
    spec = importlib.util.spec_from_file_location("satt_test_watch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FinishedProcess:
    returncode = 0

    def poll(self):
        return self.returncode


def test_job_is_never_started_without_successful_atomic_claim(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "_api_post", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        watcher.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("subprocess must not start"),
    )
    watcher._run_transcription_job("slot-1", "EP001", "session-token")


def test_successful_job_uses_claim_token_to_finish(watcher, monkeypatch, tmp_path):
    calls = []
    audio = tmp_path / "episode.wav"
    audio.touch()
    monkeypatch.setattr(
        watcher,
        "_api_post",
        lambda url, token, body: {
            "status": "in_progress",
            "claimToken": "owned-claim",
        },
    )
    monkeypatch.setattr(watcher, "_find_audio_for_key", lambda key: str(audio))
    monkeypatch.setattr(watcher.subprocess, "Popen", lambda command: FinishedProcess())
    monkeypatch.setattr(
        watcher,
        "_api_put",
        lambda url, token, body: calls.append((url, body)) or {"status": body["status"]},
    )

    watcher._run_transcription_job("slot-1", "EP001", "session-token")

    assert calls == [
        (
            watcher.SATT_API + "/postproduction/slot-1/transcribe-status",
            {"status": "done", "claimToken": "owned-claim"},
        )
    ]


def test_failed_heartbeat_marks_claim_lost(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "LEASE_HEARTBEAT_INTERVAL", 0)
    monkeypatch.setattr(watcher, "_api_put", lambda *args, **kwargs: None)
    stop = threading.Event()
    lost = threading.Event()
    watcher._heartbeat_claim("slot-1", "claim", "session", stop, lost)
    assert lost.is_set()


def test_subprocess_start_failure_marks_owned_claim_failed(
    watcher, monkeypatch, tmp_path
):
    audio = tmp_path / "episode.wav"
    audio.touch()
    calls = []
    monkeypatch.setattr(
        watcher,
        "_api_post",
        lambda *args, **kwargs: {
            "status": "in_progress",
            "claimToken": "owned-claim",
        },
    )
    monkeypatch.setattr(watcher, "_find_audio_for_key", lambda key: str(audio))
    monkeypatch.setattr(
        watcher.subprocess,
        "Popen",
        lambda command: (_ for _ in ()).throw(OSError("executable missing")),
    )
    monkeypatch.setattr(
        watcher,
        "_api_put",
        lambda url, token, body: calls.append(body) or {"status": body["status"]},
    )

    watcher._run_transcription_job("slot-1", "EP001", "session-token")

    assert calls == [
        {
            "status": "failed",
            "claimToken": "owned-claim",
            "error": "Could not start transcribe-auto.py: executable missing",
        }
    ]
