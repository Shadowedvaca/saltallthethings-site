/* ============================================
   Auth Module (v2)
   Works with an HTML-based gate already in the
   page. No JS-based body hiding.
   __PASSWORD_HASH__ is replaced at deploy time.
   ============================================ */

const Auth = {
  _expectedHash: '__PASSWORD_HASH__',
  _sessionKey: 'satt_auth_token',
  _tokenTTL: 8 * 60 * 60 * 1000, // 8 hours

  init() {
    const gate = document.getElementById('authGate');
    const content = document.getElementById('protectedContent');

    // Dev mode - hash was never replaced, skip auth
    if (this._expectedHash === '__' + 'PASSWORD_HASH' + '__') {
      console.info('Auth: dev mode (no hash set), skipping gate.');
      if (gate) gate.style.display = 'none';
      if (content) content.style.display = 'block';
      return;
    }

    // Already authenticated
    if (this._hasValidSession()) {
      if (gate) gate.style.display = 'none';
      if (content) content.style.display = 'block';
      return;
    }

    // Show gate, hide content
    if (gate) gate.style.display = 'flex';
    if (content) content.style.display = 'none';

    // Wire up login
    const input = document.getElementById('gatePassword');
    const btn = document.getElementById('gateSubmit');
    const error = document.getElementById('gateError');

    if (btn) btn.addEventListener('click', () => this._attempt(input, error, gate, content));
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') this._attempt(input, error, gate, content);
      });
      setTimeout(() => input.focus(), 100);
    }
  },

  async _attempt(input, error, gate, content) {
    const pw = input.value;
    if (!pw) {
      input.classList.add('error');
      setTimeout(() => input.classList.remove('error'), 300);
      return;
    }

    const hash = await this._hashPassword(pw);

    if (hash === this._expectedHash) {
      this._setSession();
      gate.style.display = 'none';
      content.style.display = 'block';
    } else {
      input.value = '';
      input.classList.add('error');
      error.textContent = 'Wrong password';
      setTimeout(() => {
        input.classList.remove('error');
        error.textContent = '';
      }, 1500);
    }
  },

  _hasValidSession() {
    try {
      const raw = sessionStorage.getItem(this._sessionKey);
      if (!raw) return false;
      const session = JSON.parse(raw);
      if (Date.now() - session.ts > this._tokenTTL) {
        sessionStorage.removeItem(this._sessionKey);
        return false;
      }
      return session.hash === this._expectedHash;
    } catch {
      return false;
    }
  },

  _setSession() {
    sessionStorage.setItem(this._sessionKey, JSON.stringify({
      hash: this._expectedHash,
      ts: Date.now()
    }));
  },

  async _hashPassword(password) {
    const encoder = new TextEncoder();
    const data = encoder.encode(password);
    const buffer = await crypto.subtle.digest('SHA-256', data);
    const array = Array.from(new Uint8Array(buffer));
    return array.map(b => b.toString(16).padStart(2, '0')).join('');
  },

  logout() {
    sessionStorage.removeItem(this._sessionKey);
    location.reload();
  }
};
