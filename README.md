# Tennis Watch

A private dashboard that collects tennis injury, MTO, withdrawal and break news from feeds and shows it on a status board.

## How it works
- `fetch.py` runs on GitHub every 30 minutes (GitHub Actions), reads the feeds in `feeds.json`, and saves detected events to `public/data/events.json`.
- `extractor.py` is the free keyword version of the detector. Later it gets swapped for an AI version (same `extract()` function).
- `public/index.html` is the website. Cloudflare Pages publishes the `public` folder.

## Setup
1. Create a **private** GitHub repo, then upload everything in this folder (Add file > Upload files).
   If `.github` doesn't upload, use Add file > Create new file, type the name `.github/workflows/fetch.yml`, and paste the workflow below.
2. Go to the **Actions** tab, enable workflows, open "Fetch tennis news", click **Run workflow**.
3. Publish `public` with Cloudflare Pages: Workers & Pages > Create > Pages > Connect to Git > pick the repo.
   Framework preset: None. Build command: leave empty. Build output directory: `public`.
4. Lock the site to your email with Cloudflare Zero Trust > Access > Applications > Self-hosted, covering `yourproject.pages.dev` and `*.yourproject.pages.dev`, with an Allow policy for your email.

## Workflow file (`.github/workflows/fetch.yml`)

```yaml
name: Fetch tennis news

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: fetch
  cancel-in-progress: false

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Fetch news and extract events
        run: python3 fetch.py
      - name: Save changes
        run: |
          git config user.name "tennis-bot"
          git config user.email "tennis-bot@users.noreply.github.com"
          git add public/data
          git diff --cached --quiet || (git commit -m "Update data" && git push)
```

## Notes
- Keyword detection is crude: player names are guessed and some headlines will be noise. Confidence tags show how sure it is.
- A feed that fails (Reddit often blocks cloud servers) is skipped and shown as a warning on the page.
- Add or remove feeds in `feeds.json`.
