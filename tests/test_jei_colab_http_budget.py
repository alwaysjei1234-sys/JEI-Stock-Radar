"""Synthetic transport regressions; these do not execute a Colab runtime."""
import io
import json
import unittest
from unittest.mock import patch
from tools import jei_colab_heartbeat as heartbeat


class Clock:
    value = 0
    def now(self):
        return self.value


class Drip(io.BytesIO):
    def __init__(self, body, clock, step=1):
        super().__init__(body)
        self.clock, self.step = clock, step
    def read(self, size=-1):
        # Buffered read can hide a continuously arriving slow body.
        self.clock.value += 100
        return super().read(size)
    def read1(self, size=-1):
        self.clock.value += self.step
        return io.BytesIO.read(self, min(size, 1))


class PublicReadBudgetTests(unittest.TestCase):
    def coordination(self):
        return json.dumps({"schema": 1, "colab_status": "UNKNOWN",
                           "fallback": "github_actions", "restart_possible": False}).encode()

    def test_continuous_slow_coordination_exceeds_elapsed_budget(self):
        clock = Clock()
        response = Drip(self.coordination(), clock)
        with patch.object(heartbeat.time, "monotonic", clock.now), patch.object(
                heartbeat.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(TimeoutError):
                heartbeat.read_github_coordination()
        self.assertTrue(response.closed)

    def test_connection_time_counts_against_budget(self):
        clock = Clock()
        response = io.BytesIO(self.coordination())
        def connect(*args, **kwargs):
            clock.value = 11
            return response
        with patch.object(heartbeat.time, "monotonic", clock.now), patch.object(
                heartbeat.urllib.request, "urlopen", side_effect=connect):
            with self.assertRaises(TimeoutError):
                heartbeat.read_github_coordination()
        self.assertTrue(response.closed)

    def test_truncated_complete_json_rejected_by_content_length(self):
        body = self.coordination()
        response = io.BytesIO(body)
        response.headers = {"Content-Length": str(len(body) + 10)}
        with patch.object(heartbeat.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(ValueError):
                heartbeat.read_github_coordination()
        self.assertTrue(response.closed)

    def test_valid_prefix_cannot_hide_oversize_coordination(self):
        body = self.coordination().ljust(4096, b' ') + b'ignored trailing bytes'
        with patch.object(heartbeat.urllib.request, "urlopen", return_value=io.BytesIO(body)):
            with self.assertRaises(ValueError):
                heartbeat.read_github_coordination()

    def test_default_observed_fetch_also_has_elapsed_budget(self):
        clock = Clock()
        response = Drip(json.dumps({"latest_official_day": "2026-11-27", "groups": {}}).encode(), clock)
        task = {"kind": "audit_observed_picks", "task_id": "observed-2026-11-27",
                "official_day": "2026-11-27"}
        with patch.object(heartbeat.time, "monotonic", clock.now), patch.object(
                heartbeat.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(TimeoutError):
                heartbeat.audit_observed_picks(task)
        self.assertTrue(response.closed)

    def test_fast_chunked_body_still_passes_and_closes(self):
        clock = Clock()
        response = Drip(self.coordination(), clock, step=0.001)
        with patch.object(heartbeat.time, "monotonic", clock.now), patch.object(
                heartbeat.urllib.request, "urlopen", return_value=response):
            self.assertEqual(heartbeat.read_github_coordination(), {"state": "UNKNOWN", "changed_at_utc": ""})
        self.assertTrue(response.closed)

    def test_matching_content_length_passes(self):
        body = self.coordination()
        response = io.BytesIO(body)
        response.headers = {"Content-Length": str(len(body))}
        with patch.object(heartbeat.urllib.request, "urlopen", return_value=response):
            self.assertEqual(heartbeat.read_github_coordination()["state"], "UNKNOWN")
