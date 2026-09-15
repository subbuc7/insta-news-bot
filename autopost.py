import os
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

IG_USER_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
IG_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()

IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_FILE = "posted_history.json"
RSS_URL = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-100:], f, indent=2)

def fetch_latest_today_news():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(RSS_URL, headers=headers, timeout=15)
    root = ET.fromstring(res.content)
    items = root.findall(".//item")

    now_ist = datetime.now(IST)
    today_date_str = now_ist.strftime("%Y-%m-%d")
    history = load_history()

    print(f"Checking {len(items)} items for date: {today_date_str}")

    for item in items:
        title = item.find("title").text if item.find("title") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        guid = item.find("guid").text if item.find("guid") is not None else link
        pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""

        if not title or not pub_date_str:
            continue

        try:
            pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except Exception:
            try:
                pub_dt = datetime.strptime(pub_date_str[:25], "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue

        pub_ist = pub_dt.astimezone(IST)

        # STRICT FILTER: Only news published TODAY in IST
        if pub_ist.strftime("%Y-%m-%d") != today_date_str:
            continue

        # DEDUPLICATION: Skip if already published
        if guid in history:
            continue

        clean_title = title.split(" - ")[0].strip()
        source = title.split(" - ")[-1].strip() if " - " in title else "Verified News Desk"

        return {
            "guid": guid,
            "title": clean_title,
            "source": source,
            "published_at": pub_ist.strftime("%d %b %Y, %I:%M %p IST")
        }
    return None

def render_news_graphic(news_item, output_filename="post_image.png"):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), (10, 16, 30))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        r = int(9 + (y / H) * 8)
        g = int(16 + (y / H) * 12)
        b = int(36 + (y / H) * 18)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    try:
        font_bar = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_badge = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_h1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        font_card_head = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_body = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_source = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_footer = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
    except Exception:
        font_bar = font_badge = font_h1 = font_card_head = font_body = font_source = font_footer = ImageFont.load_default()

    draw.rounded_rectangle([(60, 45), (1020, 100)], radius=12, fill=(18, 28, 52), outline=(42, 70, 125), width=2)
    draw.ellipse([(85, 66), (97, 78)], fill=(255, 60, 60))
    draw.text((112, 61), "BREAKING NEWS TODAY  |  INSTAGRAM BULLETIN", font=font_bar, fill=(230, 240, 255))
    draw.text((865, 61), datetime.now(IST).strftime("%d %b %Y").upper(), font=font_bar, fill=(255, 205, 60))

    draw.rounded_rectangle([(60, 125), (420, 175)], radius=10, fill=(212, 160, 23), outline=(255, 225, 120), width=2)
    draw.text((82, 137), "TOP HEADLINE  •  TODAY", font=font_badge, fill=(15, 15, 15))

    words = news_item["title"].split()
    lines, curr = [], []
    for w in words:
        if font_h1.getlength(" ".join(curr + [w])) <= 940:
            curr.append(w)
        else:
            if curr:
                lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    hy = 205
    for i, line in enumerate(lines[:3]):
        draw.text((60, hy), line, font=font_h1, fill=(255, 215, 60) if i == 0 else (255, 255, 255))
        hy += 60

    card_y = max(440, hy + 30)
    card_h = 680
    draw.rounded_rectangle([(60, card_y), (1020, card_y + card_h)], radius=18, fill=(16, 26, 48), outline=(48, 85, 155), width=2)
    draw.rectangle([(60, card_y), (1020, card_y + 52)], fill=(24, 40, 75))
    draw.text((85, card_y + 15), f"OFFICIAL REPORT  •  SOURCE: {news_item['source'].upper()}", font=font_card_head, fill=(210, 230, 255))

    cy = card_y + 80
    draw.text((85, cy), "Key Highlights:", font=font_source, fill=(255, 215, 60))
    cy += 50

    bullets = [
        ("• Published:", f" {news_item['published_at']}"),
        ("• News Outlet:", f" {news_item['source']}"),
        ("• Verification:", " Real-time verified same-day broadcast"),
        ("• Status:", " Approved Daily Bulletin")
    ]

    for label, val in bullets:
        draw.text((85, cy), label, font=font_source, fill=(80, 185, 255))
        lw = font_source.getlength(label)
        draw.text((85 + lw, cy), val, font=font_body, fill=(230, 240, 255))
        draw.line([(85, cy + 45), (995, cy + 45)], fill=(32, 52, 95), width=1)
        cy += 70

    callout_y = card_y + 450
    draw.rounded_rectangle([(85, callout_y), (995, callout_y + 180)], radius=12, fill=(22, 38, 70), outline=(50, 95, 175), width=1)
    draw.text((110, callout_y + 25), "DAILY BULLETIN BRIEF:", font=font_card_head, fill=(255, 205, 60))
    draw.text((110, callout_y + 65), news_item["title"][:80] + "...", font=font_body, fill=(220, 235, 255))
    draw.text((110, callout_y + 105), "Follow @_ap_ts_news for around-the-clock verified updates.", font=font_body, fill=(170, 195, 230))

    draw.rectangle([(0, 1245), (W, H)], fill=(8, 14, 26))
    draw.line([(0, 1245), (W, 1245)], fill=(40, 75, 140), width=2)
    draw.text((60, 1282), "AUTOMATED NEWS NETWORK  •  VERIFIED REAL-TIME UPDATES", font=font_footer, fill=(145, 170, 205))
    draw.text((880, 1282), "@_AP_TS_NEWS", font=font_footer, fill=(255, 210, 70))

    img.save(output_filename, "JPEG", quality=92)
    print(f"Rendered image saved to {output_filename}")
    return output_filename

def upload_image_to_imgur(file_path):
    """Uploads image anonymously to Imgur to give Meta a direct CDN URL."""
    headers = {"Authorization": "Client-ID 546c25a59c58ad7"}
    with open(file_path, "rb") as f:
        res = requests.post(
            "https://api.imgur.com/3/image",
            headers=headers,
            files={"image": f},
            timeout=30
        )
    if res.status_code == 200:
        data = res.json()
        img_url = data.get("data", {}).get("link")
        print(f"Image uploaded to public CDN: {img_url}")
        return img_url
    else:
        print(f"Imgur upload failed: {res.status_code} - {res.text}")
        return None

def publish_to_instagram(image_public_url, caption):
    print(f"Creating Meta media container for Instagram ID: {IG_USER_ID}")
    container_url = f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media"
    payload = {
        "image_url": image_public_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    res = requests.post(container_url, data=payload, timeout=30)
    res_data = res.json()
    print("Media container response:", res_data)

    creation_id = res_data.get("id")
    if not creation_id:
        print("Failed to create container:", res_data)
        return False

    print(f"Waiting 6 seconds for Meta to process container {creation_id}...")
    time.sleep(6)

    publish_url = f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media_publish"
    pub_payload = {
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN
    }
    pub_res = requests.post(publish_url, data=pub_payload, timeout=30)
    pub_data = pub_res.json()
    print("Publish response:", pub_data)

    post_id = pub_data.get("id")
    if post_id:
        print(f"SUCCESS: Post published to Instagram! ID: {post_id}")
        return True
    return False

def main():
    print("Fetching today's news...")
    news_item = fetch_latest_today_news()

    if not news_item:
        print("No new unposted news found for today. Exiting.")
        sys.exit(0)

    print(f"New story: {news_item['title']} ({news_item['source']})")
    img_file = render_news_graphic(news_item, "post_image.jpg")

    caption = (
        f"🚨 TODAY'S BREAKING NEWS: {news_item['title']}\n\n"
        f"📅 Date: {news_item['published_at']}\n"
        f"📰 Outlet: {news_item['source']}\n\n"
        f"Verified daily bulletin. Follow @_ap_ts_news for 24/7 real-time news.\n\n"
        f"#BreakingNews #APNews #TelanganaNews #IndiaNews #DailyBulletin"
    )

    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("CRITICAL: INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN secrets missing!")
        sys.exit(1)

    public_url = upload_image_to_imgur(img_file)
    if public_url:
        published = publish_to_instagram(public_url, caption)
        if published:
            history = load_history()
            history.append(news_item["guid"])
            save_history(history)
            print("Finished successfully.")
        else:
            print("Failed to publish on Instagram.")
    else:
        print("Failed to upload image.")

if __name__ == "__main__":
    main()
    
