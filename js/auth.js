/* ============================================
   Auth Module (v3 — stores password for API)
   __PASSWORD_HASH__ is replaced at deploy time.
   ============================================ */

const Auth = {
  _expectedHash: '__PASSWORD_HASH__',
  _sessionKey: 'satt_auth_token',
  _tokenTTL: 8 * 60 * 60 * 1000,

  init() {
    var gate = document.getElementById('authGate');
    var content = document.getElementById('protectedContent');
    var loading = document.getElementById('loadingOverlay');

    // Dev mode
    if (this._expectedHash === '__' + 'PASSWORD_HASH' + '__') {
      console.info('Auth: dev mode, skipping gate.');
      if (gate) gate.style.display = 'none';
      if (content) content.style.display = 'block';
      this._initStorage(loading);
      return;
    }

    // Already authenticated
    if (this._hasValidSession()) {
      if (gate) gate.style.display = 'none';
      if (content) content.style.display = 'block';
      this._initStorage(loading);
      return;
    }

    // Show gate
    if (gate) gate.style.display = 'flex';
    if (content) content.style.display = 'none';
    if (loading) loading.style.display = 'none';

    var input = document.getElementById('gatePassword');
    var btn = document.getElementById('gateSubmit');
    var error = document.getElementById('gateError');
    var self = this;

    if (btn) btn.addEventListener('click', function() { self._attempt(input, error, gate, content, loading); });
    if (input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') self._attempt(input, error, gate, content, loading);
      });
      setTimeout(function() { input.focus(); }, 100);
    }
  },

  async _attempt(input, error, gate, content, loading) {
    var pw = input.value;
    if (!pw) {
      input.classList.add('error');
      setTimeout(function() { input.classList.remove('error'); }, 300);
      return;
    }

    var hash = await this._hashPassword(pw);

    if (hash === this._expectedHash) {
      this._setSession(hash, pw);
      gate.style.display = 'none';
      content.style.display = 'block';
      this._initStorage(loading);
    } else {
      input.value = '';
      input.classList.add('error');
      error.textContent = 'Wrong password';
      setTimeout(function() {
        input.classList.remove('error');
        error.textContent = '';
      }, 1500);
    }
  },

  async _initStorage(loading) {
    // Show loading overlay while fetching from API
    if (loading) loading.style.display = 'flex';
    try {
      await Storage.init();

      // Check for localStorage migration opportunity
      if (!Storage._useLocalFallback) {
        var hasLocalData = ['config', 'ideas', 'jokes', 'showSlots', 'assignments'].some(function(key) {
          return localStorage.getItem('satt_' + key) !== null;
        });
        var apiEmpty = (Storage.getIdeas().length === 0 && Storage.getJokes().length === 0);

        if (hasLocalData && apiEmpty) {
          if (confirm('Found local data in this browser. Migrate it to the shared API so both you and Rocket can see it?')) {
            await Storage.migrateFromLocalStorage();
            Toast.success('Data migrated to shared API!');
          }
        }
      }

      // Call page-specific init if defined
      if (typeof onStorageReady === 'function') onStorageReady();
    } catch (err) {
      console.error('Storage init failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to load data: ' + err.message);
    } finally {
      if (loading) loading.style.display = 'none';
    }
  },

  _hasValidSession() {
    try {
      var raw = sessionStorage.getItem(this._sessionKey);
      if (!raw) return false;
      var session = JSON.parse(raw);
      if (Date.now() - session.ts > this._tokenTTL) {
        sessionStorage.removeItem(this._sessionKey);
        return false;
      }
      return session.hash === this._expectedHash;
    } catch { return false; }
  },

  _setSession(hash, password) {
    sessionStorage.setItem(this._sessionKey, JSON.stringify({
      hash: hash,
      password: password,   // stored for API auth headers
      ts: Date.now()
    }));
  },

  async _hashPassword(password) {
    var encoder = new TextEncoder();
    var data = encoder.encode(password);
    var buffer = await crypto.subtle.digest('SHA-256', data);
    var array = Array.from(new Uint8Array(buffer));
    return array.map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
  },

  logout() {
    sessionStorage.removeItem(this._sessionKey);
    location.reload();
  }
};
