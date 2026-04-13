#!/usr/bin/env python3
"""
Morning Brief Generator
Fetches live data, generates a spoken briefing via Claude, converts to MP3 via ElevenLabs,
uploads to Cloudflare R2, and updates the RSS feed.

Run daily at 5:30am AEST Mon-Fri via cron or GitHub Actions.
"""

import os
import json
import datetime
import requests
import boto3
import anthropic
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# CONFIG — set these in environment variables (see .env.example)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
ELEVENLABS_API_KEY   = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID  = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel — replace with your chosen voice
NEWS_API_KEY         = os.environ["NEWS_API_KEY"]

# Cloudflare R2 (S3-compatible)
R2_ACCOUNT_ID        = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID     = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET_NAME       = os.environ["R2_BUCKET_NAME"]
R2_PUBLIC_URL        = os.environ["R2_PUBLIC_URL"]  # e.g. https://pub-xxx.r2.dev

# RSS feed — this file gets pushed to GitHub Pages
RSS_OUTPUT_PATH      = Path(os.environ.get("RSS_OUTPUT_PATH", "./rss/feed.xml"))
RSS_FEED_URL         = os.environ["RSS_FEED_URL"]  # e.g. https://yourusername.github.io/morning-brief/feed.xml

# Location
GOLD_COAST_LAT       = -28.0167
GOLD_COAST_LON       = 153.4000
AEST                 = ZoneInfo("Australia/Brisbane")

# ---------------------------------------------------------------------------
# DATA FETCHERS
# ---------------------------------------------------------------------------

def fetch_weather():
    """Open-Meteo — free, no API key required."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={GOLD_COAST_LAT}&longitude={GOLD_COAST_LON}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
        f"&hourly=temperature_2m,precipitation_probability,windspeed_10m"
        f"&timezone=Australia%2FBrisbane"
        f"&forecast_days=1"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    daily = data["daily"]

    # Decode WMO weather code to plain English
    wmo_codes = {
        0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "icy fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
        61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
        75: "heavy snow", 80: "light showers", 81: "showers", 82: "heavy showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail"
    }
    code = daily["weathercode"][0]
    condition = wmo_codes.get(code, "mixed conditions")

    # Morning hours (6am-9am) precipitation probability
    hourly = data["hourly"]
    morning_hours = [6, 7, 8, 9]
    morning_rain_probs = [hourly["precipitation_probability"][h] for h in morning_hours]
    avg_morning_rain = sum(morning_rain_probs) / len(morning_rain_probs)

    return {
        "condition": condition,
        "max_temp": daily["temperature_2m_max"][0],
        "min_temp": daily["temperature_2m_min"][0],
        "rain_mm": daily["precipitation_sum"][0],
        "morning_rain_chance": round(avg_morning_rain),
        "wind_speed_morning": hourly["windspeed_10m"][7],  # 7am
    }


def fetch_world_news():
    """NewsAPI — top international headlines."""
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?language=en&pageSize=8&apiKey={NEWS_API_KEY}"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    articles = r.json().get("articles", [])
    return [
        {
            "title": a["title"],
            "source": a["source"]["name"],
            "description": a.get("description", ""),
        }
        for a in articles[:8]
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


def fetch_au_business_news():
    """NewsAPI — Australian business and economic news."""
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?country=au&category=business&pageSize=8&apiKey={NEWS_API_KEY}"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    articles = r.json().get("articles", [])
    return [
        {
            "title": a["title"],
            "source": a["source"]["name"],
            "description": a.get("description", ""),
        }
        for a in articles[:8]
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


def fetch_property_news():
    """NewsAPI — Australian property and housing market."""
    url = (
        f"https://newsapi.org/v2/everything"
        f"?q=australia+property+market+housing+real+estate+gold+coast"
        f"&language=en&sortBy=publishedAt&pageSize=5&apiKey={NEWS_API_KEY}"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    articles = r.json().get("articles", [])
    return [
        {
            "title": a["title"],
            "source": a["source"]["name"],
            "description": a.get("description", ""),
        }
        for a in articles[:5]
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


def fetch_bitcoin():
    """CoinGecko — Bitcoin price and 24h stats. Free, no key required."""
    url = (
        "https://api.coingecko.com/api/v3/coins/bitcoin"
        "?localization=false&tickers=false&community_data=false&developer_data=false"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    market = data["market_data"]
    return {
        "price_aud": market["current_price"]["aud"],
        "price_usd": market["current_price"]["usd"],
        "change_24h_pct": market["price_change_percentage_24h"],
        "change_7d_pct": market["price_change_percentage_7d"],
        "ath_aud": market["ath"]["aud"],
        "ath_distance_pct": market["ath_change_percentage"]["aud"],
        "market_cap_aud": market["market_cap"]["aud"],
    }


def fetch_bitcoin_news():
    """NewsAPI — Bitcoin and crypto news."""
    url = (
        f"https://newsapi.org/v2/everything"
        f"?q=bitcoin+cryptocurrency&language=en&sortBy=publishedAt&pageSize=5&apiKey={NEWS_API_KEY}"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    articles = r.json().get("articles", [])
    return [
        {
            "title": a["title"],
            "source": a["source"]["name"],
            "description": a.get("description", ""),
        }
        for a in articles[:5]
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


# ---------------------------------------------------------------------------
# SCRIPT GENERATION — Claude API
# ---------------------------------------------------------------------------

def generate_script(weather, world_news, au_business, property_news, bitcoin, bitcoin_news, date_str):
    """Call Claude to turn raw data into a natural spoken briefing script."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    world_news_text = "\n".join(
        f"- {a['title']} ({a['source']}): {a['description']}" for a in world_news
    )
    au_business_text = "\n".join(
        f"- {a['title']} ({a['source']}): {a['description']}" for a in au_business
    )
    property_text = "\n".join(
        f"- {a['title']} ({a['source']}): {a['description']}" for a in property_news
    )
    btc_news_text = "\n".join(
        f"- {a['title']} ({a['source']}): {a['description']}" for a in bitcoin_news
    )

    prompt = f"""You are producing a personal spoken morning briefing for Justin Gaggino — General Manager of Hismile, based in Mudgeeraba on the Gold Coast. He is 33, commercially sharp, financially literate, and time-poor. He holds Bitcoin as part of his retirement strategy. He owns property on the Gold Coast.

Today is {date_str}. Write a natural, conversational spoken script that covers these five sections in order. The entire script should take 10-12 minutes to read aloud at a comfortable pace (roughly 1500-1800 words).

Write it as it will be spoken — no headers, no bullet points, no markdown. Use natural spoken transitions between every section. Be direct and specific. Do not use filler phrases or corporate speak. Assume the listener is smart and wants insight, not just headlines. For every story go beyond the headline — explain what happened, why it matters, what the likely implications are, and what to watch next.

---

SECTION 1 — WEATHER (Gold Coast today, keep this brief — 2-3 sentences max):
{json.dumps(weather, indent=2)}

SECTION 2 — WORLD NEWS (cover the 5 most significant international stories in depth — for each one explain what happened, why it matters globally, and what to watch next. Spend at least 2-3 sentences per story. Pick stories with real geopolitical, economic, or social significance):
{world_news_text}

SECTION 3 — AUSTRALIAN BUSINESS & ECONOMY (cover 4-5 stories in depth — for each one explain the business or economic implication, not just the headline. Include any relevant impact on Australian consumers, businesses, or markets. Spend at least 2-3 sentences per story):
{au_business_text}

SECTION 4 — PROPERTY MARKET (Gold Coast and wider Australian housing market — give real insight here, not just headlines. Cover price movements, auction clearance rates, demand trends, and any policy or rate decisions affecting the market. 3-4 sentences minimum):
{property_text}

SECTION 5 — BITCOIN UPDATE (cover the current price in both AUD and USD, the 24h and 7-day movement, how far it is from all-time high, and then cover any significant news or market events driving the price. Give context on whether this is a meaningful move or noise. 3-4 sentences minimum):
Price data: {json.dumps(bitcoin, indent=2)}
Recent news: {btc_news_text}

---

Start the script with "Good morning Justin" and today's date spoken naturally. End with a brief, sharp one-sentence sign-off. No inspirational quotes."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# TEXT TO SPEECH — ElevenLabs
# ---------------------------------------------------------------------------

def generate_audio(script_text, output_path):
    """Convert script to MP3 using ElevenLabs."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": script_text,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(r.content)
    return output_path


# ---------------------------------------------------------------------------
# UPLOAD TO CLOUDFLARE R2
# ---------------------------------------------------------------------------

def upload_to_r2(local_path, filename):
    """Upload MP3 to Cloudflare R2 bucket."""
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )
    s3.upload_file(
        str(local_path),
        R2_BUCKET_NAME,
        filename,
        ExtraArgs={"ContentType": "audio/mpeg"}
    )
    return f"{R2_PUBLIC_URL}/{filename}"


# ---------------------------------------------------------------------------
# RSS FEED BUILDER
# ---------------------------------------------------------------------------

def update_rss_feed(episodes):
    """
    Rebuild the RSS feed XML.
    episodes = list of dicts: {title, url, file_size_bytes, pub_date, guid, duration_seconds}
    """
    items_xml = ""
    for ep in episodes:
        items_xml += f"""
    <item>
      <title>{ep['title']}</title>
      <enclosure url="{ep['url']}" type="audio/mpeg" length="{ep['file_size_bytes']}"/>
      <pubDate>{ep['pub_date']}</pubDate>
      <guid isPermaLink="false">{ep['guid']}</guid>
      <itunes:duration>{ep.get('duration_seconds', 480)}</itunes:duration>
      <description>{ep['title']}</description>
    </item>"""

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Justin's Morning Brief</title>
    <link>{RSS_FEED_URL}</link>
    <description>Daily personal briefing — weather, world news, Australian business, property, and Bitcoin.</description>
    <language>en-au</language>
    <itunes:explicit>no</itunes:explicit>
    <itunes:category text="News"/>
    <itunes:author>Justin Gaggino</itunes:author>
    <lastBuildDate>{datetime.datetime.now(AEST).strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>
{items_xml}
  </channel>
</rss>"""

    RSS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RSS_OUTPUT_PATH.write_text(feed)
    print(f"RSS feed written to {RSS_OUTPUT_PATH}")


def load_episode_history(history_path="rss/episodes.json"):
    """Load existing episode list to append to."""
    p = Path(history_path)
    if p.exists():
        return json.loads(p.read_text())
    return []


def save_episode_history(episodes, history_path="rss/episodes.json"):
    Path(history_path).write_text(json.dumps(episodes, indent=2))


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    now = datetime.datetime.now(AEST)
    date_str = now.strftime("%A, %d %B %Y")
    filename = now.strftime("%Y-%m-%d") + ".mp3"
    guid = now.strftime("%Y-%m-%d")
    pub_date = now.strftime("%a, %d %b %Y 05:45:00 +1000")

    print(f"=== Morning Brief Generator — {date_str} ===")

    # 1. Fetch all data
    print("Fetching weather...")
    weather = fetch_weather()

    print("Fetching world news...")
    world_news = fetch_world_news()

    print("Fetching AU business news...")
    au_business = fetch_au_business_news()

    print("Fetching property news...")
    property_news = fetch_property_news()

    print("Fetching Bitcoin data...")
    bitcoin = fetch_bitcoin()
    bitcoin_news = fetch_bitcoin_news()

    # 2. Generate script via Claude
    print("Generating script via Claude...")
    script = generate_script(weather, world_news, au_business, property_news, bitcoin, bitcoin_news, date_str)
    print(f"Script generated ({len(script.split())} words)")

    # Save script for debugging
    script_path = Path(f"/tmp/{guid}.txt")
    script_path.write_text(script)

    # 3. Convert to audio
    print("Generating audio via ElevenLabs...")
    mp3_path = Path(f"/tmp/{filename}")
    generate_audio(script, mp3_path)
    file_size = mp3_path.stat().st_size
    print(f"Audio generated: {file_size / 1024 / 1024:.1f} MB")

    # 4. Upload to R2
    print("Uploading to Cloudflare R2...")
    public_url = upload_to_r2(mp3_path, filename)
    print(f"Uploaded: {public_url}")

    # 5. Update RSS
    print("Updating RSS feed...")
    episodes = load_episode_history()

    # Remove duplicate for today if rerunning
    episodes = [e for e in episodes if e["guid"] != guid]

    # Prepend today
    episodes.insert(0, {
        "title": f"Morning Brief — {date_str}",
        "url": public_url,
        "file_size_bytes": file_size,
        "pub_date": pub_date,
        "guid": guid,
        "duration_seconds": 480,
    })

    # Keep only last 30 episodes in feed
    episodes = episodes[:30]
    save_episode_history(episodes)
    update_rss_feed(episodes)

    print(f"=== Done. Episode: {filename} ===")


if __name__ == "__main__":
    main()
