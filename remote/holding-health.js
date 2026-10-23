(function (root) {
  'use strict';
  const STORAGE_KEY = 'jei-holding-health-private-v2';
  const LEGACY_KEY = 'jei-holding-health-private-v1';
  const ITERATIONS = 310000;

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
  function normalizeList(value) {
    const list = Array.isArray(value) ? value : value && Array.isArray(value.holdings) ? value.holdings : null;
    if (!list) throw new Error('匯入檔必須是持股陣列或含 holdings 陣列的 JSON');
    const clean = list.map(normalizeHolding);
    if (new Set(clean.map(x => x.code)).size !== clean.length) throw new Error('匯入檔有重複股票代號');
    return clean;
  }
  function bytesToBase64(bytes) {
    let binary = '';
    bytes.forEach(value => { binary += String.fromCharCode(value); });
    return btoa(binary);
  }
  function base64ToBytes(value) {
    const binary = atob(value);
    return Uint8Array.from(binary, character => character.charCodeAt(0));
  }
  function validatePassphrase(passphrase) {
    if (typeof passphrase !== 'string' || passphrase.length < 12) {
      throw new Error('請使用至少 12 個字元的私人密語');
    }
  }
  async function deriveKey(passphrase, salt, cryptoApi) {
    const material = await cryptoApi.subtle.importKey('raw', new TextEncoder().encode(passphrase), 'PBKDF2', false, ['deriveKey']);
    return cryptoApi.subtle.deriveKey(
      { name: 'PBKDF2', salt, iterations: ITERATIONS, hash: 'SHA-256' },
      material, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
    );
  }
  async function encrypt(holdings, passphrase, cryptoApi) {
    validatePassphrase(passphrase);
    const clean = normalizeList(holdings);
    const salt = cryptoApi.getRandomValues(new Uint8Array(16));
    const iv = cryptoApi.getRandomValues(new Uint8Array(12));
    const key = await deriveKey(passphrase, salt, cryptoApi);
    const plaintext = new TextEncoder().encode(JSON.stringify(clean));
    const ciphertext = await cryptoApi.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext);
    return {
      version: 2, algorithm: 'AES-GCM', kdf: 'PBKDF2-SHA-256', iterations: ITERATIONS,
      salt: bytesToBase64(salt), iv: bytesToBase64(iv),
      ciphertext: bytesToBase64(new Uint8Array(ciphertext))
    };
  }
  async function decrypt(record, passphrase, cryptoApi) {
    validatePassphrase(passphrase);
    if (!record || record.version !== 2 || record.algorithm !== 'AES-GCM' ||
        record.kdf !== 'PBKDF2-SHA-256' || record.iterations !== ITERATIONS) {
      throw new Error('私人資料格式不支援或已損壞');
    }
    const key = await deriveKey(passphrase, base64ToBytes(record.salt), cryptoApi);
    const plaintext = await cryptoApi.subtle.decrypt(
      { name: 'AES-GCM', iv: base64ToBytes(record.iv) }, key, base64ToBytes(record.ciphertext)
    );
    return normalizeList(JSON.parse(new TextDecoder().decode(plaintext)));
  }
  function loadEnvelope(storage) {
    const raw = storage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  }
  function summarize(holdings) {
    return holdings.reduce((summary, item) => {
      summary.cost += item.cost * item.shares;
      if (item.price != null) {
        summary.marketValue += item.price * item.shares;
        summary.pnl += (item.price - item.cost) * item.shares;
        summary.pricedCount += 1;
      }
      return summary;
    }, { cost: 0, marketValue: 0, pnl: 0, pricedCount: 0 });
  }
  function money(value) {
    return Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 2 });
  }
  function init(doc, storage, cryptoApi) {
    const unlockForm = doc.getElementById('unlockForm');
    const vault = doc.getElementById('ownerVault');
    const form = doc.getElementById('holdingForm');
    const list = doc.getElementById('holdingRows');
    const status = doc.getElementById('holdingStatus');
    const summary = doc.getElementById('holdingSummary');
    const clearButton = doc.getElementById('clearHoldings');
    if (!unlockForm || !vault || !form || !list || !status || !summary || !clearButton) return;

    let holdings = [];
    let passphrase = '';
    let unlocked = false;
    const passField = doc.getElementById('privatePassphrase');
    const confirmField = doc.getElementById('privatePassphraseConfirm');
    const confirmLabel = doc.getElementById('confirmLabel');
    const unlockButton = doc.getElementById('unlockButton');
    const importFile = doc.getElementById('importFile');

    function setLocked(message) {
      holdings = [];
      passphrase = '';
      unlocked = false;
      vault.hidden = true;
      unlockForm.hidden = false;
      if (passField) passField.value = '';
      if (confirmField) confirmField.value = '';
      if (status) status.textContent = message || '私人資料維持加密；鎖定後不留在畫面記憶體。';
      render();
    }
    function render() {
      list.replaceChildren();
      if (!unlocked) {
        summary.textContent = '私人清單已鎖定';
        return;
      }
      if (!holdings.length) {
        const row = doc.createElement('p');
        row.className = 'empty';
        row.textContent = '尚未匯入持股資料；可選擇 JSON 檔在本機匯入。';
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
        (result.pricedCount ? '｜估算損益 ' + money(result.pnl) : '｜尚無手動市價，未計算損益');
    }
    async function persist(message) {
      try {
        if (!unlocked) throw new Error('請先解鎖私人清單');
        const envelope = await encrypt(holdings, passphrase, cryptoApi);
        storage.setItem(STORAGE_KEY, JSON.stringify(envelope));
        storage.removeItem(LEGACY_KEY);
        status.textContent = message || '已加密儲存在本機瀏覽器；私人內容不會傳送到網站或 GitHub。';
        render();
      } catch (error) {
        status.textContent = '儲存失敗：' + error.message;
      }
    }
    function readLegacy() {
      const raw = storage.getItem(LEGACY_KEY);
      return raw ? normalizeList(JSON.parse(raw)) : [];
    }
    unlockForm.addEventListener('submit', async event => {
      event.preventDefault();
      const candidate = passField.value;
      try {
        const envelope = loadEnvelope(storage);
        if (envelope) {
          holdings = await decrypt(envelope, candidate, cryptoApi);
        } else {
          const firstSetup = storage.getItem(LEGACY_KEY) == null;
          if (firstSetup) {
            validatePassphrase(candidate);
            if (candidate !== confirmField.value) throw new Error('兩次輸入的私人密語不一致');
            holdings = [];
          } else {
            holdings = readLegacy();
          }
          passphrase = candidate;
          unlocked = true;
          vault.hidden = false;
          unlockForm.hidden = true;
          await persist('私人清單已完成本機加密。請記住私人密語，網站不會保存或寄送它。');
          return;
        }
        passphrase = candidate;
        unlocked = true;
        vault.hidden = false;
        unlockForm.hidden = true;
        status.textContent = '私人持股已在本機解鎖；頁面鎖定後會清除畫面資料。';
        render();
      } catch (_) {
        passphrase = '';
        holdings = [];
        status.textContent = storage.getItem(STORAGE_KEY)
          ? '無法解鎖：密語錯誤或加密資料損壞。' : '請設定至少 12 個字元的私人密語，並再次輸入確認。';
        render();
      }
    });
    passField.addEventListener('input', () => {
      const setup = !storage.getItem(STORAGE_KEY) && !storage.getItem(LEGACY_KEY);
      confirmLabel.hidden = !setup;
      confirmField.required = setup;
      unlockButton.textContent = setup ? '建立加密私人清單' : '解鎖私人清單';
      passField.autocomplete = setup ? 'new-password' : 'current-password';
    });
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (!unlocked) return;
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
    if (importFile) importFile.addEventListener('change', async () => {
      const file = importFile.files && importFile.files[0];
      if (!file || !unlocked) return;
      try {
        const imported = normalizeList(JSON.parse(await file.text()));
        const byCode = new Map(holdings.map(item => [item.code, item]));
        imported.forEach(item => byCode.set(item.code, item));
        holdings = Array.from(byCode.values());
        await persist('匯入完成；持股內容已在本機重新加密，沒有上傳。');
      } catch (error) {
        status.textContent = '匯入失敗：' + error.message;
      } finally {
        importFile.value = '';
      }
    });
    doc.getElementById('lockHoldings').addEventListener('click', () => setLocked());
    clearButton.addEventListener('click', () => {
      if (!unlocked || (typeof root.confirm === 'function' && !root.confirm('確定清除此裝置上的私人持股資料？'))) return;
      holdings = [];
      storage.removeItem(STORAGE_KEY);
      storage.removeItem(LEGACY_KEY);
      status.textContent = '本機私人持股資料已清除。';
      setLocked('私人持股資料已清除。');
    });
    const startSetup = !storage.getItem(STORAGE_KEY) && !storage.getItem(LEGACY_KEY);
    confirmLabel.hidden = !startSetup;
    confirmField.required = startSetup;
    unlockButton.textContent = startSetup ? '建立加密私人清單' : '解鎖私人清單';
    passField.autocomplete = startSetup ? 'new-password' : 'current-password';
    setLocked(startSetup ? '首次使用請建立至少 12 個字元的私人密語。密語只留在你的記憶中。' : undefined);
    root.addEventListener && root.addEventListener('pagehide', () => setLocked());
  }
  root.JEIHoldingHealth = { STORAGE_KEY, LEGACY_KEY, ITERATIONS, normalizeHolding, normalizeList, encrypt, decrypt, loadEnvelope, summarize, init };
  if (typeof document !== 'undefined') {
    const start = () => init(document, window.localStorage, window.crypto);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
  }
}(typeof window !== 'undefined' ? window : globalThis));
