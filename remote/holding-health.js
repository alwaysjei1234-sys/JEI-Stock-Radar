(function (root) {
  'use strict';
  const STORAGE_KEY = 'jei-holding-health-private-v1';

  function positiveNumber(value, label, allowEmpty) {
    if ((value === '' || value == null) && allowEmpty) return null;
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) throw new Error(label + '必須是大於 0 的數字');
    return number;
  }

  function normalizeHolding(input) {
    if (!input || typeof input !== 'object') throw new Error('持股資料格式錯誤');
    const code = String(input.code || '').trim().toUpperCase();
    const name = String(input.name || '').trim();
    if (!/^[A-Z0-9.-]{1,12}$/.test(code)) throw new Error('請輸入正確的股票代號');
    if (name.length > 40) throw new Error('名稱不可超過 40 個字');
    const cost = positiveNumber(input.cost, '平均成本', false);
    const shares = positiveNumber(input.shares, '持有股數', false);
    if (!Number.isSafeInteger(shares)) throw new Error('持有股數必須是整數');
    const price = positiveNumber(input.price, '手動市價', true);
    return { code, name: name || code, cost, shares, price };
  }

  function load(storage) {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.map(normalizeHolding);
    } catch (_) {
      return [];
    }
  }

  function save(storage, holdings) {
    const clean = holdings.map(normalizeHolding);
    storage.setItem(STORAGE_KEY, JSON.stringify(clean));
    return clean;
  }

  function summarize(holdings) {
    return holdings.reduce((summary, item) => {
      summary.cost += item.cost * item.shares;
      if (item.price != null) {
        summary.pricedCost += item.cost * item.shares;
        summary.marketValue += item.price * item.shares;
        summary.pnl += (item.price - item.cost) * item.shares;
        summary.pricedCount += 1;
      }
      return summary;
    }, { cost: 0, marketValue: 0, pnl: 0, pricedCost: 0, pricedCount: 0 });
  }

  function money(value) {
    return Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 2 });
  }

  function init(doc, storage) {
    const form = doc.getElementById('holdingForm');
    const list = doc.getElementById('holdingRows');
    const status = doc.getElementById('holdingStatus');
    const summary = doc.getElementById('holdingSummary');
    const clearButton = doc.getElementById('clearHoldings');
    if (!form || !list || !status || !summary || !clearButton) return;

    let holdings = load(storage);
    function render() {
      list.replaceChildren();
      if (!holdings.length) {
        const row = doc.createElement('p');
        row.className = 'empty';
        row.textContent = '尚未在此裝置建立持股資料。';
        list.appendChild(row);
      }
      holdings.forEach(item => {
        const row = doc.createElement('article');
        row.className = 'holding';
        const details = doc.createElement('div');
        const title = doc.createElement('strong');
        title.textContent = item.code + ' ' + item.name;
        const info = doc.createElement('p');
        info.textContent = '成本 ' + money(item.cost) + '｜股數 ' + money(item.shares) +
          (item.price == null ? '｜市價尚未輸入' : '｜手動市價 ' + money(item.price));
        details.append(title, info);
        const remove = doc.createElement('button');
        remove.type = 'button';
        remove.textContent = '刪除';
        remove.setAttribute('aria-label', '刪除 ' + item.code);
        remove.addEventListener('click', () => {
          holdings = holdings.filter(entry => entry.code !== item.code);
          persist();
        });
        row.append(details, remove);
        list.appendChild(row);
      });
      const result = summarize(holdings);
      summary.textContent = '持有 ' + holdings.length + ' 檔｜投入成本 ' + money(result.cost) +
        (result.pricedCount ? '｜已填手動市價 ' + result.pricedCount + ' 檔，估算損益 ' + money(result.pnl) : '｜尚無手動市價，未計算損益');
    }
    function persist(message) {
      try {
        holdings = save(storage, holdings);
        status.textContent = message || '已儲存在本機瀏覽器；不會上傳至 JEI 或 GitHub。';
        render();
      } catch (error) {
        status.textContent = '儲存失敗：' + error.message;
      }
    }

    form.addEventListener('submit', event => {
      event.preventDefault();
      try {
        const entry = normalizeHolding({
          code: doc.getElementById('holdingCode').value,
          name: doc.getElementById('holdingName').value,
          cost: doc.getElementById('holdingCost').value,
          shares: doc.getElementById('holdingShares').value,
          price: doc.getElementById('holdingPrice').value
        });
        if (holdings.some(item => item.code === entry.code)) throw new Error('此股票代號已存在，請直接刪除後重新新增');
        holdings.push(entry);
        persist();
        form.reset();
      } catch (error) {
        status.textContent = error.message;
      }
    });
    clearButton.addEventListener('click', () => {
      holdings = [];
      try {
        storage.removeItem(STORAGE_KEY);
        status.textContent = '本機持股資料已清除。';
        render();
      } catch (error) {
        status.textContent = '清除失敗：' + error.message;
      }
    });
    render();
  }

  root.JEIHoldingHealth = { STORAGE_KEY, normalizeHolding, load, save, summarize, init };
  if (typeof document !== 'undefined') {
    const start = () => init(document, window.localStorage);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
  }
}(typeof window !== 'undefined' ? window : globalThis));
