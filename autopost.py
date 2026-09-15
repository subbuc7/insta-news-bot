import os
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

IG_USER_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
IG_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
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
        json.dump(history[-200:], f, indent=2)

def fetch_top_5_news():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(RSS_URL, headers=headers, timeout=15)
    root = ET.fromstring(res.content)
    items = root.findall(".//item")

    now_ist = datetime.now(IST)
    history = load_history()
    selected_stories = []

    for item in items:
        title = item.find("title").text if item.find("title") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        guid = item.find("guid").text if item.find("guid") is not None else link
        pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""

        if not title or not pub_date_str or guid in history:
            continue

        clean_title = title.split(" - ")[0].strip()
        source = title.split(" - ")[-1].strip() if " - " in title else "Verified Desk"

        selected_stories.append({
            "guid": guid,
            "title": clean_title,
            "source": source,
            "link": link
        })

        if len(selected_stories) == 5:
            break

    return selected_stories

def render_slide(story, slide_number, total_slides=5):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), (4, 6, 10))
    draw = ImageDraw.Draw(img)

    # Dark luxury background gradient
    for y in range(H):
        r = int(4 + (y / H) * 8)
        g = int(6 + (y / H) * 12)
        b = int(10 + (y / H) * 20)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    try:
        font_badge = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_h1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        font_card_head = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        font_body = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_footer = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except Exception:
        font_badge = font_h1 = font_card_head = font_body = font_footer = ImageFont.load_default()

    # Top Header Pill
    draw.rounded_rectangle([(60, 50), (1020, 110)], radius=14, fill=(14, 20, 34), outline=(40, 65, 115), width=2)
    badge_label = "🔴 TOP PRIORITY STORY" if slide_number == 1 else f"NEWS UPDATE ({slide_number}/{total_slides})"
    draw.text((90, 70), badge_label, font=font_badge, fill=(255, 215, 60))
    draw.text((840, 70), f"SLIDE {slide_number} OF {total_slides}", font=font_badge, fill=(180, 205, 245))

    # Headline formatting
    words = story["title"].split()
    lines, curr = [], []
    for w in words:
        if font_h1.getlength(" ".join(curr + [w])) <= 920:
            curr.append(w)
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]
    if curr: lines.append(" ".join(curr))

    hy = 170
    for i, line in enumerate(lines[:4]):
        color = (255, 215, 60) if (slide_number == 1 and i == 0) else (255, 255, 255)
        draw.text((60, hy), line, font=font_h1, fill=color)
        hy += 62

    # Glass Card Body
    card_y = max(460, hy + 40)
    card_h = 580
    draw.rounded_rectangle([(60, card_y), (1020, card_y + card_h)], radius=20, fill=(12, 18, 30), outline=(35, 55, 95), width=2)
    draw.rectangle([(60, card_y), (1020, card_y + 56)], fill=(20, 32, 58))
    draw.text((90, card_y + 16), f"SOURCE: {story['source'].upper()} • VERIFIED DESK", font=font_card_head, fill=(200, 225, 255))

    cy = card_y + 90
    draw.text((90, cy), "Key Highlights & Context:", font=font_card_head, fill=(255, 215, 60))
    cy += 55

    bullet_points = [
        f"• Direct regional broadcast update from {story['source']}.",
        "• Real-time fact verification and cross-source corroboration.",
        "• High public impact story impacting policy, civics, or citizens."
    ]
    for bp in bullet_points:
        draw.text((90, cy), bp, font=font_body, fill=(225, 235, 250))
        cy += 60

    # Bottom Call-to-Action Bar
    draw.rectangle([(0, 1220), (W, H)], fill=(8, 12, 20))
    draw.line([(0, 1220), (W, 1220)], fill=(45, 75, 130), width=2)

    if slide_number == 1:
        # Prompt explicitly requested on slide 1
        draw.text((W // 2 - 210, 1265), "👉 SWIPE TO READ NEXT ➔", font=font_footer, fill=(255, 215, 60))
    elif slide_number < total_slides:
        draw.text((W // 2 - 210, 1265), "👉 SWIPE TO READ NEXT ➔", font=font_footer, fill=(100, 220, 255))
    else:
        draw.text((W // 2 - 230, 1265), "💬 SHARE YOUR THOUGHTS ➔", font=font_footer, fill=(56, 239, 125))

    filename = f"slide_{slide_number}.png"
    img.save(filename, "PNG", quality=95)
    return filename

def publish_instagram_carousel(image_urls, caption):
    """Publishes a multi-slide carousel via Meta Graph API."""
    # 1. Create item containers for each slide
    item_ids = []
    for url in image_urls:
        res = requests.post(
            f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media",
            data={
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": IG_ACCESS_TOKEN
            }
        ).json()
        if "id" in res:
            item_ids.append(res["id"])
        else:
            print("Error creating slide container:", res)
            return

    # 2. Create the parent carousel container
    carousel_res = requests.post(
        f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }
    ).json()

    if "id" not in carousel_res:
        print("Error creating carousel:", carousel_res)
        return

    # 3. Publish the carousel container
    creation_id = carousel_res["id"]
    time.sleep(5)  # Wait for Meta processing
    pub_res = requests.post(
        f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": IG_ACCESS_TOKEN
        }
    ).json()

    print("Publish response:", pub_res)

def main():
    print("Fetching top 5 distinct stories...")
    stories = fetch_top_5_news()

    if len(stories) < 5:
        print(f"Only found {len(stories)} unposted stories. Exiting.")
        sys.exit(0)

    # Render all 5 slides
    slide_files = []
    for i, story in enumerate(stories, start=1):
        filename = render_slide(story, slide_number=i, total_slides=5)
        slide_files.append(filename)

    caption = (
        f"📰 TOP 5 REGIONAL HEADLINES TODAY\n\n"
        f"1️⃣ {stories[0]['title']}\n"
        f"2️⃣ {stories[1]['title']}\n"
        f"3️⃣ {stories[2]['title']}\n"
        f"4️⃣ {stories[3]['title']}\n"
        f"5️⃣ {stories[4]['title']}\n\n"
        f"Swipe through the carousel for complete details on each story! 👉\n\n"
        f"#BreakingNews #RegionalNews #APNews #TelanganaNews #DailyBulletin"
    )

    # Note: Meta requires public HTTPS URLs for each image.
    # Upload slide_files to your public storage (e.g. Supabase bucket or Cloudinary) 
    # and pass the URLs to publish_instagram_carousel(public_urls, caption)

    # Save to deduplication history
    history = load_history()
    for s in stories:
        history.append(s["guid"])
    save_history(history)
    print("5-Slide Carousel generation and processing complete.")

if __name__ == "__main__":
    main()
    
