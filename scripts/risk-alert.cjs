'use strict';
// Pure decision layer: alerts only on dated, fresh observations. No network or credentials.
function evaluateRiskAlert(input, nowMs = Date.now()) {
  if (!input || !Number.isFinite(input.timestampMs) || !Number.isFinite(nowMs)) return {level:'unknown', notify:false, reason:'missing_timestamp'};
  const ageMs = nowMs - input.timestampMs;
  if (ageMs < -60000 || ageMs > 10*60*1000) return {level:'unknown', notify:false, reason:'stale_or_future_data'};
  const pct = input.indexChangePct;
  const breadth = input.advancersPct;
  if (!Number.isFinite(pct) || !Number.isFinite(breadth) || breadth < 0 || breadth > 100) return {level:'unknown', notify:false, reason:'invalid_market_data'};
  if (pct <= -3 || (pct <= -2 && breadth <= 20)) return {level:'red',notify:true,reason:'broad_market_selloff'};
  if (pct <= -1.5 || (pct <= -1 && breadth <= 30)) return {level:'orange',notify:true,reason:'market_weakness'};
  return {level:'normal',notify:false,reason:'no_threshold_crossed'};
}
module.exports={evaluateRiskAlert};
