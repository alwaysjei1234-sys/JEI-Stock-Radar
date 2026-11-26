"""Opt-in routing pilot. Does not submit prompts, execute jobs, or change feeds.

Run: python jei_local_ai_router.py --self-test
Probe: python jei_local_ai_router.py --probe
Local inference must be separately enabled and verified offline (including
Ollama cloud features disabled). Never expose the Ollama port to the Internet.
"""
import argparse
import json
import unittest
from urllib.request import HTTPRedirectHandler, Request, build_opener

MODEL = "qwen3:4b"
TAGS_URL = "http://127.0.0.1:11434/api/tags"

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def local_ready():
    """Read only installed model names; no user data is transmitted."""
    try:
        with build_opener(NoRedirect()).open(Request(TAGS_URL), timeout=2) as res:
            raw = res.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return False
            models = json.loads(raw)["models"]
            return isinstance(models, list) and any(
                isinstance(m, dict) and m.get("name") == MODEL for m in models
            )
    except (OSError, ValueError, KeyError, TypeError):
        return False

def route(*, data_class="restricted", enabled=False, local_available=False,
          colab_coordination=None, colab_heartbeat_verified=False,
          colab_task_supported=False, task_kind=None):
    """Return a routing decision, never invoke any backend.

    Public classification must be explicit. Unknown classes fail closed.
    Restricted jobs remain paused until a verified local-only inference
    implementation exists; a health probe alone is not privacy proof.
    """
    if data_class != "public":
        return "hold_restricted"
    if enabled is not True:
        return "existing_cloud_pipeline"
    if local_available is True:
        return "local_candidate"
    # Published status alone is not proof of freshness. The caller must
    # independently verify a recent authenticated heartbeat and task support.
    if (isinstance(colab_coordination, dict)
            and colab_coordination.get("colab_status") == "RECENT_HEARTBEAT"
            and colab_coordination.get("evidence") == "authenticated_google_drive_heartbeat"
            and colab_heartbeat_verified is True
            and colab_task_supported is True
            and task_kind == "audit_observed_picks"):
        return "colab_candidate"
    return "existing_cloud_pipeline"

class RoutingTests(unittest.TestCase):
    def test_default_is_restricted(self):
        self.assertEqual(route(), "hold_restricted")

    def test_private_never_cloud(self):
        for category in ("restricted", "unknown", "personal", None):
            for enabled in (False, True):
                for available in (False, True):
                    self.assertEqual(route(data_class=category, enabled=enabled,
                                           local_available=available), "hold_restricted")

    def test_public_opt_in_and_availability(self):
        for enabled in (False, True):
            for available in (False, True):
                self.assertEqual(route(data_class="public", enabled=enabled,
                                       local_available=available),
                                 "local_candidate" if enabled and available
                                 else "existing_cloud_pipeline")

    def test_colab_candidate_requires_all_gates(self):
        coord = {"colab_status": "RECENT_HEARTBEAT",
                 "evidence": "authenticated_google_drive_heartbeat"}
        for verified in (False, True):
            for supported in (False, True):
                self.assertEqual(route(data_class="public", enabled=True,
                                       colab_coordination=coord,
                                       colab_heartbeat_verified=verified,
                                       colab_task_supported=supported,
                                       task_kind="audit_observed_picks"),
                                 "colab_candidate" if verified and supported
                                 else "existing_cloud_pipeline")

    def test_stale_unknown_or_untrusted_colab_falls_back(self):
        for coord in (None, {}, {"colab_status": "STALE",
                                 "evidence": "authenticated_google_drive_heartbeat"},
                      {"colab_status": "RECENT_HEARTBEAT", "evidence": "unknown"}):
            self.assertEqual(route(data_class="public", enabled=True,
                                   colab_coordination=coord,
                                   colab_heartbeat_verified=True,
                                   colab_task_supported=True,
                                   task_kind="audit_observed_picks"),
                             "existing_cloud_pipeline")

    def test_local_first_and_restricted_never_cloud(self):
        opts = dict(enabled=True, local_available=True,
                    colab_coordination={"colab_status": "RECENT_HEARTBEAT",
                        "evidence": "authenticated_google_drive_heartbeat"},
                    colab_heartbeat_verified=True, colab_task_supported=True,
                    task_kind="audit_observed_picks")
        self.assertEqual(route(data_class="public", **opts), "local_candidate")
        self.assertEqual(route(data_class="restricted", **opts), "hold_restricted")
        opts["local_available"] = False
        self.assertEqual(route(data_class="restricted", **opts), "hold_restricted")
        opts["enabled"] = False
        self.assertEqual(route(data_class="public", **opts), "existing_cloud_pipeline")

    def test_unsupported_colab_task(self):
        coord = {"colab_status": "RECENT_HEARTBEAT",
                 "evidence": "authenticated_google_drive_heartbeat"}
        for kind in (None, "llm_summary", "arbitrary_code"):
            self.assertEqual(route(data_class="public", enabled=True,
                                   colab_coordination=coord,
                                   colab_heartbeat_verified=True,
                                   colab_task_supported=True, task_kind=kind),
                             "existing_cloud_pipeline")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=["jei_local_ai_router.py"])
    else:
        print(json.dumps({"model": MODEL, "local_available": local_ready()}))
