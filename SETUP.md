# Justin's Morning Brief — Setup Guide

Complete setup takes about 45 minutes. Do it once, runs forever.

---

## What you'll have when done

A private podcast that generates a new 6-8 minute episode every weekday at 5:30am AEST.
It appears in Overcast on your phone. When you connect to CarPlay, it plays automatically.
Zero manual effort after setup.

---

## Step 1 — Create the GitHub repo (5 min)

1. Go to github.com and create a new **private** repository called `morning-brief`
2. Clone it locally:
   ```
   git clone https://github.com/YOURUSERNAME/morning-brief.git
   cd morning-brief
   ```
3. Copy all files from this package into the repo folder
4. Push to GitHub:
   ```
   git add .
   git commit -m "Initial setup"
   git push
   ```

---

## Step 2 — Enable GitHub Pages (3 min)

1. In your repo on GitHub: Settings → Pages
2. Source: **GitHub Actions** (not "Deploy from branch")
3. That's it — the workflow handles deployment automatically

---

## Step 3 — Get your API keys (15 min)

### Anthropic (Claude)
- Go to console.anthropic.com
- API Keys → Create Key
- Copy the key (starts with `sk-ant-`)

### ElevenLabs (voice)
- Go to elevenlabs.io and create an account
- Subscribe to **Creator** plan ($22 USD/mo) — gives you 100k characters/month, enough for ~15 episodes
- Profile → API Keys → copy your key
- Browse voices at elevenlabs.io/voice-library and find one you like
- Click the voice → copy the Voice ID from the URL or settings panel
- Recommended: look for "Adam", "Daniel", or browse for an Australian male voice

### NewsAPI
- Go to newsapi.org → Get API Key (free)
- Free developer plan gives 100 requests/day — more than enough
- Copy the API key

### Cloudflare R2 (MP3 storage)
1. Create a Cloudflare account at cloudflare.com (free)
2. Go to R2 in the dashboard
3. Create a bucket called `morning-brief`
4. Enable **Public Access** on the bucket
5. Note the public URL (format: `https://pub-XXXX.r2.dev`)
6. Go to **Manage R2 API Tokens** → Create Token
   - Permissions: Object Read & Write
   - Bucket: morning-brief (specific)
7. Copy the Account ID, Access Key ID, and Secret Access Key

---

## Step 4 — Add secrets to GitHub (5 min)

In your GitHub repo: Settings → Secrets and variables → Actions → New repository secret

Add each of these:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic key |
| `ELEVENLABS_API_KEY` | Your ElevenLabs key |
| `ELEVENLABS_VOICE_ID` | The voice ID you chose |
| `NEWS_API_KEY` | Your NewsAPI key |
| `R2_ACCOUNT_ID` | Cloudflare Account ID |
| `R2_ACCESS_KEY_ID` | R2 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | R2 Secret Access Key |
| `R2_BUCKET_NAME` | `morning-brief` |
| `R2_PUBLIC_URL` | `https://pub-XXXX.r2.dev` |
| `RSS_FEED_URL` | `https://YOURUSERNAME.github.io/morning-brief/feed.xml` |

---

## Step 5 — Test it manually (5 min)

Before waiting for the scheduler, trigger a manual run:

1. In your GitHub repo: Actions tab
2. Click "Generate Morning Brief" workflow
3. Click "Run workflow" → Run workflow
4. Watch the logs — should complete in about 2-3 minutes
5. Check your R2 bucket for the MP3 file
6. Check `https://YOURUSERNAME.github.io/morning-brief/feed.xml` for the feed

If it fails, check the workflow logs — the error message will be specific.

---

## Step 6 — Subscribe in Overcast (5 min)

1. Download **Overcast** from the App Store (free)
2. Tap the + button → Add URL
3. Paste: `https://YOURUSERNAME.github.io/morning-brief/feed.xml`
4. Subscribe
5. In the podcast settings within Overcast:
   - Downloads: On (download new episodes automatically)
   - Notifications: On (optional)
   - Keep: Last 5 episodes (enough, saves space)

---

## Step 7 — Set up CarPlay auto-play

1. Connect your phone to your car via CarPlay
2. Open Overcast from CarPlay
3. Find your Morning Brief podcast and start playing an episode
4. **That's it.** CarPlay remembers the last audio source. Every subsequent connection will resume Overcast automatically.

The next morning's episode will already be downloaded and queued as episode 1.

---

## Ongoing costs

| Item | Cost |
|---|---|
| ElevenLabs Creator | ~$33 AUD/mo |
| Cloudflare R2 | ~$2 AUD/mo |
| Claude API | ~$4 AUD/mo |
| NewsAPI | Free |
| GitHub Actions | Free (2,000 min/mo included) |
| GitHub Pages | Free |
| **Total** | **~$39 AUD/mo** |

---

## Customising the voice

To change the ElevenLabs voice after setup:
1. Browse elevenlabs.io/voice-library
2. Copy the new Voice ID
3. Update the `ELEVENLABS_VOICE_ID` secret in GitHub
4. Runs automatically next day

---

## Customising the briefing content

The briefing prompt is in `scripts/generate.py` around line 140.
Edit the prompt text, commit, and push — takes effect next day.

For example, to add F1 race weekend alerts, add an F1 section to the prompt
and a new data fetcher calling the Ergast F1 API (free, no key).

---

## Troubleshooting

**Episode not appearing in Overcast**
- GitHub Pages can take 2-5 minutes to update after the workflow runs
- Pull to refresh in Overcast
- Verify the feed URL is accessible in a browser first

**Workflow failing at ElevenLabs step**
- Check your character quota at elevenlabs.io
- The script is ~900-1100 words = ~5,000-6,000 characters per episode
- Creator plan gives 100k characters/month = ~16 episodes before the month resets

**Workflow failing at NewsAPI step**
- Free plan rate limits: wait a few minutes and re-run
- If hitting limits daily, upgrade to the $449/mo plan or swap to GDELT (free, no limits)

**No audio in CarPlay**
- Ensure Overcast has downloaded the episode (not just listed it)
- Go to Overcast settings → General → ensure Background App Refresh is on

---

## Optional upgrade: GDELT for news (no rate limits, free)

Replace `fetch_world_news()` in generate.py with a GDELT query for truly unlimited
international news with no API key. Example endpoint:

```
https://api.gdeltproject.org/api/v2/doc/doc?query=sourcelang:english&mode=artlist&maxrecords=10&format=json
```

This gives full article data with no daily limits.
