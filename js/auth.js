/* ============================================
   Auth Module
   Client-side password gate for admin pages.
   __PASSWORD_HASH__ is replaced at deploy time
   by a GitHub Action with the real SHA-256 hash.
   ============================================ */

const Auth = {
  // This placeholder gets replaced during CI/CD deploy
  _expectedHash: '__PASSWORD_HASH__',
  _sessionKey: 'satt_auth_token',
  _tokenTTL: 8 * 60 * 60 * 1000, // 8 hours

  /**
   * Check if user is authenticated. If not, show login gate.
   * Call this at the top of every admin page.
   */
  guard() {
    // If placeholder was never replaced (local dev), skip auth
    if (this._expectedHash === '__' + 'PASSWORD_HASH' + '__') {
      console.info('Auth: password hash not set (dev mode), skipping gate.');
      return;
    }

    if (this._hasValidSession()) {
      return; // Already authenticated
    }

    this._showLoginGate();
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

  _showLoginGate() {
    // Hide page content
    document.body.style.visibility = 'hidden';

    // Create overlay
    const overlay = document.createElement('div');
    overlay.id = 'authGate';
    overlay.innerHTML = `
      <style>
        #authGate {
          position: fixed;
          inset: 0;
          z-index: 99999;
          background: #08080f;
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: 'DM Sans', sans-serif;
          visibility: visible !important;
        }
        #authGate * {
          visibility: visible !important;
        }
        #authGate .gate-box {
          background: #13132a;
          border: 1px solid #2a2a4a;
          border-radius: 16px;
          padding: 48px 40px;
          max-width: 380px;
          width: 90%;
          text-align: center;
          box-shadow: 0 8px 32px rgba(0,0,0,0.6);
        }
        #authGate .gate-logo {
          width: 80px;
          border-radius: 8px;
          margin-bottom: 24px;
          filter: drop-shadow(0 0 20px rgba(200,168,78,0.2));
        }
        #authGate h2 {
          font-family: 'Cinzel', serif;
          color: #d4b85a;
          font-size: 1.2rem;
          margin-bottom: 8px;
        }
        #authGate .gate-sub {
          color: #5a5750;
          font-size: 0.85rem;
          margin-bottom: 24px;
        }
        #authGate input {
          width: 100%;
          padding: 10px 16px;
          background: #0f0f20;
          border: 1px solid #2a2a4a;
          border-radius: 8px;
          color: #e0ddd4;
          font-family: 'DM Sans', sans-serif;
          font-size: 0.95rem;
          text-align: center;
          letter-spacing: 2px;
          margin-bottom: 16px;
          transition: border-color 150ms ease;
        }
        #authGate input:focus {
          outline: none;
          border-color: #c8a84e;
          box-shadow: 0 0 0 3px rgba(200,168,78,0.2);
        }
        #authGate input.error {
          border-color: #cc4444;
          animation: gateShake 300ms ease;
        }
        #authGate button {
          width: 100%;
          padding: 10px 16px;
          background: linear-gradient(135deg, #c8a84e 0%, #8a7434 100%);
          color: #0a0a0f;
          border: 1px solid #c8a84e;
          border-radius: 8px;
          font-family: 'DM Sans', sans-serif;
          font-size: 0.9rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 150ms ease;
        }
        #authGate button:hover {
          background: linear-gradient(135deg, #e0c868 0%, #c8a84e 100%);
          box-shadow: 0 0 20px rgba(200,168,78,0.15);
        }
        #authGate .gate-error {
          color: #cc4444;
          font-size: 0.8rem;
          margin-top: 12px;
          min-height: 1.2em;
        }
        @keyframes gateShake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-6px); }
          75% { transform: translateX(6px); }
        }
      </style>
      <div class="gate-box">
        <img src="images/256x256.jpeg" alt="SATT" class="gate-logo">
        <h2>Crew Only</h2>
        <p class="gate-sub">Enter the password to continue</p>
        <input type="password" id="gatePassword" placeholder="••••••••" autocomplete="off">
        <button id="gateSubmit">Enter</button>
        <div class="gate-error" id="gateError"></div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Wire up events
    const input = document.getElementById('gatePassword');
    const btn = document.getElementById('gateSubmit');
    const error = document.getElementById('gateError');

    const attempt = async () => {
      const pw = input.value;
      if (!pw) {
        input.classList.add('error');
        setTimeout(() => input.classList.remove('error'), 300);
        return;
      }

      const hash = await this._hashPassword(pw);

      if (hash === this._expectedHash) {
        this._setSession();
        overlay.remove();
        document.body.style.visibility = 'visible';
      } else {
        input.value = '';
        input.classList.add('error');
        error.textContent = 'Wrong password';
        setTimeout(() => {
          input.classList.remove('error');
          error.textContent = '';
        }, 1500);
      }
    };

    btn.addEventListener('click', attempt);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') attempt();
    });

    // Focus input
    setTimeout(() => input.focus(), 100);
  },

  /**
   * Log out — clear session, reload page to show gate
   */
  logout() {
    sessionStorage.removeItem(this._sessionKey);
    location.reload();
  }
};
