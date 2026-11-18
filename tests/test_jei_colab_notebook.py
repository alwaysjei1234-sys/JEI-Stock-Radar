import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.jei_colab_report_validator import validate


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
CELLS = json.loads((ROOT / "colab/JEI_Colab_Audit.ipynb").read_bytes())["cells"]


class ColabNotebookTests(unittest.TestCase):
    def test_early_bootstrap_starts_once_and_last_cell_is_retry(self):
        import threading
        cells = CELLS
        startup = "".join(cells[2]["source"])
        self.assertIn("jei_start_heartbeat_if_needed()", startup)
        self.assertIn("HEARTBEAT_STARTED", startup)
        self.assertIn("module.start_heartbeat", startup)
        self.assertLess(2, next(i for i, c in enumerate(cells)
                                if "jei_diagnostics_latest.json" in "".join(c["source"])))
        retry = "".join(cells[-1]["source"])
        self.assertIn("jei_start_heartbeat_if_needed()", retry)
        calls = []
        stop = threading.Event()
        fake_thread = types.SimpleNamespace(is_alive=lambda: True, join=lambda timeout: None)
        module = types.SimpleNamespace(
            start_heartbeat=lambda *args, **kwargs: (calls.append((args, kwargs)) or (stop, fake_thread)),
            read_github_coordination=lambda: {},
            audit_observed_picks=lambda task: {},
        )
        spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m: None))
        namespace = {"jei_source_commit": SHA,
                     "jei_source_base": "https://raw.githubusercontent.com/example/" + SHA + "/"}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "MyDrive").mkdir()
            executable = startup.replace("/content/drive", tmp)
            with patch.dict("sys.modules", {"google.colab": types.SimpleNamespace(
                    drive=types.SimpleNamespace(mount=lambda path: None))}), patch(
                    "urllib.request.urlretrieve", return_value=None), patch(
                    "importlib.util.spec_from_file_location", return_value=spec), patch(
                    "importlib.util.module_from_spec", return_value=module):
                exec(compile(executable, "early-heartbeat", "exec"), namespace)
                self.assertEqual(len(calls), 1)
                self.assertEqual(namespace["jei_heartbeat_bootstrap_status"], "RUNNING")
                exec(compile(executable, "duplicate-heartbeat", "exec"), namespace)
                self.assertEqual(len(calls), 1)
        stop.set()

    def test_report_pins_source_and_requires_both_current_outputs(self):
        requests = []

        def resolve(request, timeout):
            url = getattr(request, "full_url", request)
            requests.append(url)
            if url.endswith("/commits/main"):
                revision = SHA if len(requests) == 1 else "b" * 40
                return io.BytesIO(json.dumps({"sha": revision}).encode())
            self.assertTrue(url.endswith(f"/{SHA}/remote/system.json"), url)
            return io.BytesIO(b'{"data_date":"2026-11-12"}')

        def download(url, target):
            self.assertIn(f"/{SHA}/", url)
            relative = url.split(f"/{SHA}/", 1)[1]
            Path(target).write_bytes((ROOT / relative).read_bytes())

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                ns = {}
                modules = {"google.colab": types.SimpleNamespace(
                    drive=types.SimpleNamespace(mount=lambda path: None))}
                with patch.dict("sys.modules", modules), patch("urllib.request.urlopen", resolve), patch(
                        "urllib.request.urlretrieve", download):
                    for i in (1, 8, 12, 14):
                        source = "".join(CELLS[i]["source"]).replace("/content/drive", tmp)
                        if i == 8:
                            ns.update(now=ns["dt"].datetime.now(ns["dt"].timezone.utc),
                                      risk={}, issues=[], wstatus=200, rstatus=200, runs={})
                        if i == 14:
                            with self.assertRaisesRegex(RuntimeError, "共享運算"):
                                observed_path = ns["jei_observed_path"]
                                ns["jei_observed_path"] = None
                                exec(compile(source, "report-before-compute", "exec"), ns)
                            ns["jei_observed_path"] = observed_path
                        exec(compile(source, f"notebook-cell-{i}", "exec"), ns)
                dest = Path(tmp) / "MyDrive/JEI-Stock-Radar/diagnostics"
                report = json.loads((dest / "jei_colab_run_latest.json").read_bytes())
                self.assertEqual(report["source_commit"], SHA)
                self.assertEqual(set(report["outputs"]), {"diagnostics", "observed_compute"})
                self.assertTrue(validate(report, output_dir=dest, expected_commit=SHA,
                                         source_path=ROOT / "remote/pick_validation.json")["verified"])
                observed = json.loads((dest / report["outputs"]["observed_compute"]).read_bytes())
                self.assertEqual(observed["source_commit"], SHA)
                self.assertFalse(observed["independent_oos_verified"])
                self.assertEqual(len(requests), 2)
            finally:
                os.chdir(old_cwd)
