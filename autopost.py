import os
import sys
import json
import time
import io
import urllib.parse
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

        # Skip if already posted
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

def fetch_ai_background(headline):
    """Generates a photorealistic AI image matching the news story via Pollinations AI (100% Free)"""
    clean_query = headline[:70].replace("'", "").replace('"', "")
    prompt = f"editorial photo of {clean_query}, cinematic lighting, photorealistic news journalism, 4k"
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1350&nologo=true"
    
    print(f"Generating AI background image for: {clean_query}...")
    try:
        resp = requests.get(url, timeout=35)
        if resp.status_code == 200:
            bg = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            if bg.size != (1080, 1350):
                bg = bg.resize((1080, 1350), Image.Resampling.LANCZOS)
            print("AI background generated successfully!")
            return bg
    except Exception as e:
        print(f"AI image generation skipped/failed ({e}), using studio gradient.")
    return None

def render_news_graphic(news_item, output_filename="post_image.jpg"):
    W, H = 1080, 1350
    
    # 1. Base Image: Generate AI Photo or Fallback Gradient
    ai_bg = fetch_ai_background(news_item["title"])
    if ai_bg:
        img = ai_bg
    else:
        img = Image.new("RGBA", (W, H), (10, 16, 30, 255))
        d_bg = ImageDraw.Draw(img)
        for y in range(H):
            r = int(9 + (y / H) * 12)
            g = int(16 + (y / H) * 16)
            b = int(36 + (y / H) * 26)
            d_bg.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # 2. Dark Cinematic Overlay (ensures text is 100% readable over the photo)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d_ov = ImageDraw.Draw(overlay)
    
    # Top dark vignette
    for y in range(220):
        alpha = int(220 * (1 - (y / 220)))
        d_ov.line([(0, y), (W, y)], fill=(6, 10, 18, alpha))
        
    # Lower dark overlay from headline down to bottom
    for y in range(280, H):
        alpha = int(255 * min(1.0, ((y - 280) / 450) ** 1.3))
        d_ov.line([(0, y), (W, y)], fill=(6, 10, 18, alpha))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 3. Fonts Setup
    try:
        font_bar = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_badge = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_h1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 50)
        font_card_head = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_body = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_source = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_follow_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
    except Exception:
        font_bar = font_badge = font_h1 = font_card_head = font_body = font_source = font_follow_bold = ImageFont.load_default()

    # 4. Top Header Bar
    draw.rounded_rectangle([(60, 45), (1020, 100)], radius=12, fill=(18, 28, 52, 230), outline=(42, 70, 125, 255), width=2)
    draw.ellipse([(85, 66), (97, 78)], fill=(255, 60, 60))
    draw.text((112, 61), "BREAKING NEWS TODAY  |  INSTAGRAM BULLETIN", font=font_bar, fill=(230, 240, 255))
    draw.text((865, 61), datetime.now(IST).strftime("%d %b %Y").upper(), font=font_bar, fill=(255, 205, 60))

    # Category Pill
    draw.rounded_rectangle([(60, 125), (420, 175)], radius=10, fill=(212, 160, 23, 245), outline=(255, 225, 120, 255), width=2)
    draw.text((82, 137), "TOP HEADLINE  •  TODAY", font=font_badge, fill=(15, 15, 15))

    # 5. Headline Text (Wrapped)
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

    hy = 340
    for i, line in enumerate(lines[:3]):
        draw.text((60, hy), line, font=font_h1, fill=(255, 215, 60) if i == 0 else (255, 255, 255))
        hy += 64

    # 6. Center Story Card
    card_y = max(550, hy + 30)
    card_h = 570
    draw.rounded_rectangle([(60, card_y), (1020, card_y + card_h)], radius=18, fill=(14, 22, 40, 235), outline=(48, 85, 155, 230), width=2)
    draw.rectangle([(60, card_y), (1020, card_y + 50)], fill=(22, 36, 68, 240))
    draw.text((85, card_y + 14), f"OFFICIAL REPORT  •  SOURCE: {news_item['source'].upper()}", font=font_card_head, fill=(210, 230, 255))

    cy = card_y + 75
    draw.text((85, cy), "Key Highlights:", font=font_source, fill=(255, 215, 60))
    cy += 45

    bullets = [
        ("• Published:", f" {news_item['published_at']}"),
        ("• Verified Source:", f" {news_item['source']}"),
        ("• Reporting Status:", " Real-time verified bulletin"),
        ("• Region / Focus:", " State & National Major Story")
    ]

    for label, val in bullets:
        draw.text((85, cy), label, font=font_source, fill=(80, 185, 255))
        lw = font_source.getlength(label)
        draw.text((85 + lw, cy), val, font=font_body, fill=(230, 240, 255))
        draw.line([(85, cy + 40), (995, cy + 40)], fill=(32, 52, 95, 200), width=1)
        cy += 60

    callout_y = card_y + 360
    draw.rounded_rectangle([(85, callout_y), (995, callout_y + 170)], radius=12, fill=(20, 32, 60, 230), outline=(50, 95, 175, 200), width=1)
    draw.text((110, callout_y + 20), "DAILY BULLETIN BRIEF:", font=font_card_head, fill=(255, 205, 60))
    draw.text((110, callout_y + 60), news_item["title"][:80] + "...", font=font_body, fill=(220, 235, 255))
    draw.text((110, callout_y + 100), "Stay informed with verified around-the-clock news updates.", font=font_body, fill=(170, 195, 230))

    # 7. PROMINENT FOLLOW BANNER AT BOTTOM
    follow_y0 = 1240
    draw.rounded_rectangle([(60, follow_y0), (1020, 1310)], radius=14, fill=(212, 160, 23, 240), outline=(255, 225, 120, 255), width=2)
    follow_text = "👉  FOLLOW  @_AP_TS_NEWS  FOR MORE DAILY UPDATES"
    fw = font_follow_bold.getlength(follow_text)
    fx = 60 + ((960 - fw) / 2)
    draw.text((fx, follow_y0 + 20), follow_text, font=font_follow_bold, fill=(12, 12, 12))

    # Export
    rgb_img = img.convert("RGB")
    rgb_img.save(output_filename, "JPEG", quality=93)
    print(f"Rendered image saved to {output_filename}")
    return output_filename

def upload_image_to_imgur(file_path):
    headers = {"Authorization": "Client-ID 546c25a59c58ad7"}
    with open(file_path, "rb") as f:
        res = requests.post(
            "https://api.imgur.com/3/image",
            headers=headers,
            files={"image": f},
            timeout=35
        )
    if res.status_code == 200:
        img_url = res.json().get("data", {}).get("link")
        print(f"Image uploaded to public CDN: {img_url}")
        return img_url
    return None

def publish_to_instagram(image_public_url, caption):
    container_url = f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media"
    res = requests.post(container_url, data={
        "image_url": image_public_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }, timeout=30)
    creation_id = res.json().get("id")
    if not creation_id:
        print("Failed to create container:", res.text)
        return False

    time.sleep(6)
    publish_url = f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN
    }, timeout=30)
    post_id = pub_res.json().get("id")
    if post_id:
        print(f"SUCCESS: Post published to Instagram! Post ID: {post_id}")
        return True
    return False

def main():
    print("Fetching today's news...")
    news_item = fetch_latest_today_news()

    if not news_item:
        print("No new unposted news found for today. Exiting.")
        sys.exit(0)

    print(f"Story: {news_item['title']} ({news_item['source']})")
    img_file = render_news_graphic(news_item, "post_image.jpg")

    caption = (
        f"🚨 TODAY'S BREAKING NEWS: {news_item['title']}\n\n"
        f"📅 Date: {news_item['published_at']}\n"
        f"📰 Outlet: {news_item['source']}\n\n"
        f"👉 Follow @_ap_ts_news for around-the-clock verified breaking news & daily updates!\n\n"
        f"#BreakingNews #APNews #TelanganaNews #IndiaNews #DailyBulletin #NewsToday"
    )

    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("Instagram secrets missing!")
        sys.exit(1)

    public_url = upload_image_to_imgur(img_file)
    if public_url:
        published = publish_to_instagram(public_url, caption)
        if published:
            history = load_history()
            history.append(news_item["guid"])
            save_history(history)
            print("Post published & history updated!")
        else:
            print("Failed to publish.")
    else:
        print("Failed to upload image to CDN.")

if __name__ == "__main__":
    main()
    
