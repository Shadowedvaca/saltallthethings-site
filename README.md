# Salt All The Things — Podcast Website & Show Management

Website and internal production tools for the *Salt All The Things* WoW podcast.

## Setup

### 1. Create the GitHub repo

Push this entire folder to a new GitHub repo (e.g. `salt-all-the-things`).

### 2. Set the admin password

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

- **Name:** `ADMIN_PASSWORD`
- **Value:** whatever password you want for the admin pages

### 3. Enable GitHub Pages

Go to **Settings** → **Pages** → Under "Build and deployment":
- **Source:** GitHub Actions

That's it. The included workflow (`.github/workflows/deploy.yml`) handles everything:
- Hashes your password (never stored in plain text)
- Injects the hash into the auth script
- Deploys to GitHub Pages

### 4. First deploy

Push to `main` and the Action runs automatically. Your site will be live at:
```
https://<your-username>.github.io/<repo-name>/
```

## Pages

| Page | URL | Auth Required |
|------|-----|---------------|
| Landing page | `/index.html` | No — public |
| Show Management | `/show_management.html` | Yes |
| Config | `/config.html` | Yes |

## Changing the password

Update the `ADMIN_PASSWORD` secret in GitHub and either push a commit or manually trigger the workflow (Actions → Deploy → Run workflow). The hash gets regenerated on every deploy.

## Local development

When running locally (just opening the HTML files in a browser), the auth gate is automatically skipped since the password hash placeholder hasn't been replaced. All features work normally.

## Data storage

All data (ideas, show schedule, config, API keys) is stored in your browser's `localStorage`. This means:
- Data is per-browser, per-device
- API keys never leave your browser or hit GitHub
- Use the Export/Import feature on the Config page to backup or transfer data between devices

## Tech stack

- Pure HTML/CSS/JS — no build step, no frameworks
- GitHub Pages for hosting
- GitHub Actions for CI/CD
- Anthropic Claude API or OpenAI API for show idea processing
