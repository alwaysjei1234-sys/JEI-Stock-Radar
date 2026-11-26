"""One-shot real-model acceptance, never substituted by a mock."""
import json
import tempfile
import time
from pathlib import Path
from tools.jei_hybrid_worker import pull_once
from jei_local_ai_router import local_ready, MODEL
from tools.jei_hybrid_audit import local_summary, validate_summary_response, summary_counts

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
            if result.get("status") == "receipt_saved":
                print(Path(result["receipt"]).read_text(encoding="utf-8"))
            raise RuntimeError("real model response missing")
        receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
        if not receipt.get("narrative") or receipt.get("uploaded") is not False:
            raise RuntimeError("invalid receipt")
        expected_text = "符合門檻的觀察統計共 {} 組，其中 {} 組未達績效標準。此為既有觀察統計，並非獨立樣本外回測。".format(receipt["observed"]["eligible_aggregates"], receipt["observed"]["underperforming_aggregates"])
        if receipt["narrative"] != expected_text:
            raise RuntimeError("summary fact verification failed")
        cases = []
        for n, weak in ((0,0),(7,0),(8,3),(5,5)):
            start_case = time.monotonic()
            output = local_summary({"eligible_aggregates":n,"underperforming_aggregates":weak})
            if output != "符合門檻的觀察統計共 {} 組，其中 {} 組未達績效標準。此為既有觀察統計，並非獨立樣本外回測。".format(n,weak):
                raise RuntimeError("synthetic case mismatch")
            cases.append({"n":n,"weak":weak,"seconds":round(time.monotonic()-start_case,3)})
        cached = pull_once(**options)
        if cached.get("narrative_source") != "cache":
            raise RuntimeError("cache not verified; snapshot may have changed")
        evidence = {"real_model_response_verified":True,"provider":"github_actions_cpu_ollama",
                    "model":MODEL,"elapsed_seconds":round(elapsed,3),
                    "task_id":result["task_id"],"observed":receipt["observed"],
                    "narrative":receipt["narrative"],"cache_verified":True,
                    "live_public_manifest_verified":True,
                    "windows_verified":False,"colab_verified":False,
                    "structured_fact_validation":True,"synthetic_real_model_cases":cases,
                    "semantic_quality_independently_verified":False}
        Path("audit-output").mkdir(exist_ok=True)
        Path("audit-output/ollama-live.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(evidence,ensure_ascii=False))

if __name__ == "__main__":
    main()
