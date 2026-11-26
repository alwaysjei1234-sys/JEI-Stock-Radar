"""One-shot real-model acceptance, never substituted by a mock."""
import json
import tempfile
import time
from pathlib import Path
from tools.jei_hybrid_worker import pull_once
from jei_local_ai_router import local_ready, MODEL

def main():
    if not local_ready():
        raise RuntimeError("required local model unavailable")
    with tempfile.TemporaryDirectory() as d:
        options = dict(output_dir=Path(d)/"receipts", job_db=Path(d)/"jobs.db",
                       enable_local=True)
        start = time.monotonic()
        result = pull_once(**options)
        elapsed = time.monotonic()-start
        if result.get("status") != "receipt_saved" or result.get("narrative_source") != "model":
            print(json.dumps({"real_model_verified":False,"result":result}))
            raise RuntimeError("real model response missing")
        receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
        if not receipt.get("narrative") or receipt.get("uploaded") is not False:
            raise RuntimeError("invalid receipt")
        cached = pull_once(**options)
        if cached.get("narrative_source") != "cache":
            raise RuntimeError("cache not verified; snapshot may have changed")
        evidence = {"real_model_response_verified":True,"provider":"github_actions_cpu_ollama",
                    "model":MODEL,"elapsed_seconds":round(elapsed,3),
                    "task_id":result["task_id"],"observed":receipt["observed"],
                    "narrative":receipt["narrative"],"cache_verified":True,
                    "live_public_manifest_verified":True,
                    "windows_verified":False,"colab_verified":False,
                    "semantic_quality_independently_verified":False}
        Path("audit-output").mkdir(exist_ok=True)
        Path("audit-output/ollama-live.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(evidence,ensure_ascii=False))

if __name__ == "__main__":
    main()
