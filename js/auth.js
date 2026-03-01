/* ============================================
   Auth Module (v4 — JWT, redirects to login.html)
   ============================================ */

const Auth = {
  _storageKey: 'satt_jwt',

  init() {
    var data = this._getSession();
    if (!data) {
      var next = encodeURIComponent(location.pathname + location.search);
      location.href = 'login.html?next=' + next;
      return;
    }
    document.getElementById('protectedContent').style.display = 'block';
    this._initStorage();
  },

  _getSession() {
    try {
      var raw = localStorage.getItem(this._storageKey);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data.token) return null;
      // Decode JWT exp from base64url payload
      var parts = data.token.split('.');
      if (parts.length !== 3) return null;
      var payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        localStorage.removeItem(this._storageKey);
        return null;
      }
      return data;
    } catch(e) { return null; }
  },

  getToken() {
    var data = this._getSession();
    return data ? data.token : null;
  },

  logout() {
    localStorage.removeItem(this._storageKey);
    location.href = 'login.html';
  },

  async _initStorage() {
    var loading = document.getElementById('loadingOverlay');
    if (loading) loading.style.display = 'flex';
    try {
      await Storage.init();
      if (typeof onStorageReady === 'function') onStorageReady();
    } catch(e) {
      console.error('Storage init failed:', e);
      if (typeof Toast !== 'undefined') Toast.error('Failed to load data: ' + e.message);
    } finally {
      if (loading) loading.style.display = 'none';
    }
  }
};
