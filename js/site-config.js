/* ============================================
   Site Config — Centralized External Links
   
   Edit this file to update links across the
   entire site. No need to hunt through HTML.
   ============================================ */

const SiteConfig = {
  // ---- Podcast Platforms ----
  platforms: {
    spotify: 'https://open.spotify.com/show/1zR6Ro5ZEKNVxi6Vmffdi3',
    apple: 'https://podcasts.apple.com/us/podcast/salt-all-the-things/id1876978999',
    youtube: 'https://www.youtube.com/channel/UCg_DAljSae62HqGj0ta_e8g',
    amazonMusic: 'https://music.amazon.com/podcasts/6b191782-b370-44d0-b0e3-ebd2e3e0ac23/salt-all-the-things',
    pocketCasts: '',    // e.g. 'https://pca.st/...'
    overcast: '',       // e.g. 'https://overcast.fm/...'
    rss: 'https://anchor.fm/s/10f035ec0/podcast/rss'
  },

  // ---- Community ----
  discord: 'https://discord.gg/5F7mC72hGU',

  // ---- Support ----
  patreon: 'https://www.patreon.com/cw/SaltAllTheThingsPodcast',
  buyMeACoffee: 'https://buymeacoffee.com/saltallthethings',
  kofi: 'https://ko-fi.com/saltallthethings',
  paypal: 'https://www.paypal.com/donate/?hosted_button_id=929EXMERABQNC',

  // ---- Social Media ----
  social: {
    twitter: '',        // e.g. 'https://twitter.com/saltallthethings'
    bluesky: '',        // e.g. 'https://bsky.app/profile/...'
    tiktok: '',         // e.g. 'https://tiktok.com/@saltallthethings'
    instagram: ''       // e.g. 'https://instagram.com/saltallthethings'
  },

  // ---- Guild Attribution ----
  guild: {
    name: 'Pull All The Things',
    url: 'https://www.pullallthethings.com/',
    tagline: 'Brought to you by the World of Warcraft guild'
  },

  // ---- Show Info ----
  show: {
    name: 'Salt All The Things',
    tagline: 'Two friends, two decades of WoW, and zero filter — the good, the bad, and the salty.',
    subtitle: 'A little salt for your day',
    launchDate: '2026-02-17',
    hosts: [
      { name: 'Rocket', role: 'Primary Host', character: 'Rocket' },
      { name: 'Trog', role: 'Co-Host', character: 'Trogmoon' }
    ]
  },

  // ---- API ----
  // Public episodes endpoint (no auth required)
  publicApiUrl: '__API_URL__',  // replaced at deploy time

  // ---- Helper Methods ----
  hasLink(key) {
    if (typeof key === 'string') return !!key && key.length > 0;
    return false;
  },

  getActivePlatforms() {
    const active = [];
    const names = {
      spotify: { name: 'Spotify', icon: '🎧', color: '#1DB954' },
      apple: { name: 'Apple Podcasts', icon: '🍎', color: '#872EC4' },
      youtube: { name: 'YouTube', icon: '▶', color: '#FF0000' },
      amazonMusic: { name: 'Amazon Music', icon: '🎵', color: '#25D1DA' },
      pocketCasts: { name: 'Pocket Casts', icon: '📱', color: '#F43E37' },
      overcast: { name: 'Overcast', icon: '🔊', color: '#FC7E0F' },
      rss: { name: 'RSS Feed', icon: '📡', color: '#EE802F' }
    };
    for (const [key, url] of Object.entries(this.platforms)) {
      if (url && url.length > 0) {
        active.push({ key, url, ...names[key] });
      }
    }
    return active;
  },

  getActiveSocials() {
    const active = [];
    const names = {
      twitter: { name: 'Twitter / X', icon: '𝕏' },
      bluesky: { name: 'Bluesky', icon: '🦋' },
      tiktok: { name: 'TikTok', icon: '♪' },
      instagram: { name: 'Instagram', icon: '📷' }
    };
    for (const [key, url] of Object.entries(this.social)) {
      if (url && url.length > 0) {
        active.push({ key, url, ...names[key] });
      }
    }
    return active;
  }
};
