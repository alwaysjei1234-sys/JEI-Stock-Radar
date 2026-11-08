"""Three-stage JEI stock research prompt optimizer. No external AI calls."""
import json
from tools.jei_ai_trader_modes import MODES, load_profile

NEEDED = ("symbol", "market", "as_of", "horizon", "strategy", "risk_limit",
          "benchmark", "data_sources", "backtest_window")

def diagnose(request):
    if not isinstance(request, dict):
        raise ValueError("request_must_be_object")
    return [{"field": key, "issue": "missing_or_empty"}
            for key in NEEDED if not request.get(key)]

def build(request, mode="decision"):
    if mode not in MODES:
        raise ValueError("unknown_mode")
    issues = diagnose(request)
    profile = load_profile()
    prompt = (
        "你是 JEI 股票分析師，使用可核實資料，不可捏造行情、勝率或經驗。"
        "依序完成三步：(1) 初步分析與解答，區分已核實數據、推論與缺失資料；"
        "(2) 指令診斷，檢查時間區間、大盤、風險、交易成本、籌碼、資料來源；"
        "(3) 提供可複製的升級版 AI 指令。"
        "以台股為主、美股為輔；波段與強勢股趨勢策略；積極但必須風控。"
        "依主流資金、技術、籌碼、基本面、消息面交叉驗證。"
        "給出多空論點、矛盾訊號、失效條件、資料日期、來源與樣本外回測限制。"
        "無資料時明確說未知，不得臆測，不得直接下單。"
        "分析模式：" + mode + "。"
        "使用者需求：" + json.dumps(request, ensure_ascii=False, sort_keys=True)
    )
    return {"status": "PROMPT_ONLY_NOT_MARKET_ANALYSIS", "mode": mode,
            "profile": {"market_priority": profile["market_priority"],
                        "risk_appetite": profile["risk_appetite"]},
            "step1": {"status": "AWAITING_VERIFIED_MARKET_DATA",
                      "request": request, "no_fabricated_metrics": True},
            "step2": {"diagnostics": issues},
            "step3": {"optimized_prompt": prompt},
            "auto_trade": False, "auto_promote": False}
