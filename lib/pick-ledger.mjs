// JEI immutable recommendation ledger (pure functions; no external dependencies).
// Feed integration must call recordPick on the date of each actual recommendation.
// Historical recommendations MUST NOT be backfilled using future information.
const HORIZONS = [1, 3, 7, 15, 30];
const validPrice = x => Number.isFinite(Number(x)) && Number(x) > 0;
const dateKey = x => /^\d{4}-\d{2}-\d{2}$/.test(x);
export function recordPick(ledger, pick) {
  if (!pick || !dateKey(pick.date) || !/^\d{4,6}$/.test(String(pick.symbol)) ||
      !validPrice(pick.entryPrice) || !pick.category || !pick.reason ||
      !pick.source || !pick.strategyVersion) throw new Error('Incomplete pick evidence');
  const id = [pick.date, pick.symbol, pick.category, pick.strategyVersion].join(':');
  if (ledger.some(p => p.id === id)) return ledger; // stable across feed reruns
  return [...ledger, Object.freeze({
    id, date: pick.date, symbol: String(pick.symbol),
    category: pick.category, entryPrice: Number(pick.entryPrice),
    reason: pick.reason, source: pick.source, strategyVersion: pick.strategyVersion,
    priceType: pick.priceType || 'verified-close',
    createdAt: pick.createdAt || null
  })];
}
// bars: verified daily close data, strictly AFTER recommendation date, ordered by trading date.
// If a horizon has not matured, its outcome remains pending; never use the last available
// day as a substitute. Adjusted-price series must be consistent with entryPrice.
export function scorePick(pick, bars) {
  const sorted = [...bars].filter(b => dateKey(b.date) && b.date > pick.date &&
    validPrice(b.close) && b.verified === true).sort((a,b) => a.date.localeCompare(b.date));
  const unique = sorted.filter((b,i) => i === 0 || b.date !== sorted[i-1].date);
  const outcomes = {};
  for (const n of HORIZONS) {
    const b = unique[n-1];
    outcomes[n] = b ? {status:'matured', date:b.date,
      close:Number(b.close), returnPct:(Number(b.close)/pick.entryPrice-1)*100}
      : {status:'pending'};
  }
  return {id:pick.id, outcomes};
}
// Strategy P&L must be computed separately from pick forward returns, with explicit
// execution assumptions, commissions, transaction tax, and unfilled orders.
export { HORIZONS };
