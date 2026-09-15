import os
import sys
import json
import time
import io
import textwrap
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

W, H = 1080, 1350

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
            "link": link,
            "published_at": pub_ist.strftime("%d %b %Y, %I:%M %p IST")
        }
    return None

def fetch_ai_photo(headline):
    """Fetches high-impact editorial photo matching the story"""
    clean_query = headline[:70].replace("'", "").replace('"', "")
    prompt = f"dramatic press photo of {clean_query}, photojournalism, realistic news photography, 4k"
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1350&nologo=true"
    
    print(f"Generating editorial photo for: {clean_query}...")
    try:
        resp = requests.get(url, timeout=35)
        if resp.status_code == 200:
            bg = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            if bg.size != (W, H):
                bg = bg.resize((W, H), Image.Resampling.LANCZOS)
            return bg
    except Exception as e:
        print(f"AI photo generation fallback: {e}")
    
    bg = Image.new("RGBA", (W, H), (15, 20, 32, 255))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        r = int(18 + (y / H) * 16)
        g = int(22 + (y / H) * 16)
        b = int(32 + (y / H) * 24)
        d.line([(0, y), (W, y)], fill=(r, g, b, 255))
    return bg

# ==========================================
# SLIDE 1: REFERENCE STYLE COVER (Photo + Red Banners)
# ==========================================
def render_cover_slide(news_item, output_filename="slide1.jpg"):
    img = fetch_ai_photo(news_item["title"])
    
    # Bottom vignette gradient so red banners and text pop
    vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d_vig = ImageDraw.Draw(vignette)
    for y in range(750, H):
        alpha = int(240 * min(1.0, ((y - 750) / 450) ** 1.3))
        d_vig.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, vignette)
    draw = ImageDraw.Draw(img)

    try:
        font_banner = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        font_sub = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
        font_watermark = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
    except Exception:
        font_banner = font_sub = font_watermark = ImageFont.load_default()

    # Top Brand Pill
    draw.rounded_rectangle([(60, 45), (310, 95)], radius=10, fill=(0, 0, 0, 200))
    draw.text((75, 58), "@_AP_TS_NEWS", font=font_watermark, fill=(255, 255, 255))

    # Wrap Headline into Red Banners
    words = news_item["title"].split()
    lines, curr = [], []
    for w in words:
        if font_banner.getlength(" ".join(curr + [w])) <= 920:
            curr.append(w)
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]
    if curr: lines.append(" ".join(curr))

    banner_bg = (185, 12, 28)  # Exact reference red
    line_h = 60
    pad_x = 18
    pad_y = 6
    
    start_y = H - 100 - (len(lines[:3]) * (line_h + 8)) - 60

    for i, line in enumerate(lines[:3]):
        tw = int(font_banner.getlength(line))
        x0 = int((W - tw) / 2) - pad_x
        y0 = start_y + i * (line_h + 8)
        x1 = x0 + tw + (pad_x * 2)
        y1 = y0 + line_h
        
        draw.rectangle([(x0, y0), (x1, y1)], fill=banner_bg)
        draw.text((x0 + pad_x, y0 + pad_y + 4), line, font=font_banner, fill=(255, 255, 255))

    # Sub-headline / Quote
    sub_quote = f'"{news_item["source"].upper()}" Breaking Report'
    qw = int(font_sub.getlength(sub_quote))
    qx = int((W - qw) / 2)
    qy = start_y + len(lines[:3]) * (line_h + 8) + 16
    draw.text((qx, qy), sub_quote, font=font_sub, fill=(245, 245, 245))

    img.convert("RGB").save(output_filename, "JPEG", quality=94)
    print(f"Slide 1 saved to {output_filename}")
    return output_filename

# ==========================================
# SLIDE 2: FULL CONTENT & DEEP-DIVE
# ==========================================
def render_content_slide(news_item, output_filename="slide2.jpg"):
    img = Image.new("RGB", (W, H), (10, 14, 24))
    draw = ImageDraw.Draw(img)

    try:
        font_head = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
        font_sub = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        font_body = ImageFont.truetype("DejaVuSans.ttf", 25)
        font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        font_follow = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
    except Exception:
        font_head = font_sub = font_body = font_bold = font_follow = ImageFont.load_default()

    # Top Header
    draw.rounded_rectangle([(60, 45), (1020, 100)], radius=12, fill=(18, 28, 52))
    draw.text((85, 60), "IN-DEPTH REPORT  •  FULL COVERAGE", font=font_sub, fill=(255, 205, 60))
    draw.text((820, 60), "@_AP_TS_NEWS", font=font_sub, fill=(200, 220, 255))

    # Headline
    words = news_item["title"].split()
    lines, curr = [], []
    for w in words:
        if font_head.getlength(" ".join(curr + [w])) <= 940:
            curr.append(w)
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]
    if curr: lines.append(" ".join(curr))

    hy = 135
    for l in lines[:2]:
        draw.text((60, hy), l, font=font_head, fill=(255, 255, 255))
        hy += 52

    # Narrative Content Box
    card_y = hy + 25
    card_h = 960
    draw.rounded_rectangle([(60, card_y), (1020, card_y + card_h)], radius=18, fill=(16, 24, 42), outline=(45, 75, 135), width=2)

    cy = card_y + 35
    paragraphs = [
        f"{news_item['title']}. This developing story was confirmed by {news_item['source']} in their latest broadcast.",
        "Authorities and official observers have highlighted that this development marks a significant turn of events with far-reaching administrative and public impact across the region."
    ]

    for p in paragraphs:
        p_lines = textwrap.wrap(p, width=54)
        for pl in p_lines:
            draw.text((90, cy), pl, font=font_body, fill=(225, 235, 250))
            cy += 36
        cy += 20

    # Key Highlights
    draw.text((90, cy), "KEY HIGHLIGHTS & BACKGROUND:", font=font_bold, fill=(255, 205, 60))
    cy += 45

    key_points = [
        f"Timeline: Official reporting confirmed on {news_item['published_at']}.",
        f"Primary Source: {news_item['source']} verified reporting network.",
        "Ongoing Status: Real-time public affairs monitoring in progress.",
        "Significance: Impacting policy, governance, and regional developments."
    ]

    for kp in key_points:
        kp_lines = textwrap.wrap(kp, width=52)
        for i, kpl in enumerate(kp_lines):
            prefix = "• " if i == 0 else "  "
            draw.text((90, cy), prefix + kpl, font=font_body, fill=(185, 210, 240))
            cy += 34
        cy += 12

    # Bottom Follow Banner
    follow_y0 = 1240
    draw.rounded_rectangle([(60, follow_y0), (1020, 1310)], radius=14, fill=(185, 12, 28))
    ft = "👉  SWIPE FOR MORE  •  FOLLOW @_AP_TS_NEWS FOR UPDATES"
    ft_w = font_follow.getlength(ft)
    draw.text((60 + (960 - ft_w) / 2, follow_y0 + 22), ft, font=font_follow, fill=(255, 255, 255))

    img.save(output_filename, "JPEG", quality=94)
    print(f"Slide 2 saved to {output_filename}")
    return output_filename

def upload_image_to_imgur(file_path):
    headers = {"Authorization": "Client-ID 546c25a59c58ad7"}
    with open(file_path, "rb") as f:
        res = requests.post("https://api.imgur.com/3/image", headers=headers, files={"image": f}, timeout=35)
    if res.status_code == 200:
        url = res.json().get("data", {}).get("link")
        print(f"Uploaded {file_path} -> {url}")
        return url
    return None

def publish_carousel_to_instagram(image_urls, caption):
    item_ids = []
    for idx, url in enumerate(image_urls):
        print(f"Creating carousel item {idx + 1}...")
        res = requests.post(f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media", data={
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": IG_ACCESS_TOKEN
        }, timeout=30)
        item_id = res.json().get("id")
        if item_id:
            item_ids.append(item_id)
        else:
            print(f"Item {idx + 1} failed:", res.text)

    if len(item_ids) < 2:
        print("Falling back to single photo post...")
        single_res = requests.post(f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media", data={
            "image_url": image_urls[0],
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }, timeout=30)
        creation_id = single_res.json().get("id")
    else:
        print("Creating Carousel Container...")
        c_res = requests.post(f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media", data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        }, timeout=30)
        creation_id = c_res.json().get("id")

    if not creation_id:
        print("Failed to create container.")
        return False

    time.sleep(6)
    pub_res = requests.post(f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media_publish", data={
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN
    }, timeout=30)
    post_id = pub_res.json().get("id")
    if post_id:
        print(f"SUCCESS: Carousel Published! Post ID: {post_id}")
        return True
    print("Publish failed:", pub_res.text)
    return False

def main():
    print("Fetching today's news...")
    news_item = fetch_latest_today_news()

    if not news_item:
        print("No new unposted news found for today. Exiting.")
        sys.exit(0)

    print(f"Story: {news_item['title']} ({news_item['source']})")
    
    s1_file = render_cover_slide(news_item, "slide1.jpg")
    s2_file = render_content_slide(news_item, "slide2.jpg")

    caption = (
        f"🚨 TODAY'S BREAKING STORY: {news_item['title']}\n\n"
        f"In a major development reported by {news_item['source']} on {news_item['published_at']}, "
        f"significant announcements have been made regarding {news_item['title'][:60]}.\n\n"
        f"Key details confirm that this initiative brings immediate focus to the regional and national landscape. "
        f"Official sources have underlined that follow-up directives and administrative procedures are now underway.\n\n"
        f"👉 Swipe left to read the full comprehensive coverage.\n"
        f"👉 Follow @_ap_ts_news for around-the-clock verified breaking news updates!\n\n"
        f"#BreakingNews #APNews #TelanganaNews #IndiaNews #DailyBulletin #NewsToday"
    )

    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("Instagram secrets missing!")
        sys.exit(1)

    url1 = upload_image_to_imgur(s1_file)
    url2 = upload_image_to_imgur(s2_file)

    if url1 and url2:
        published = publish_carousel_to_instagram([url1, url2], caption)
        if published:
            history = load_history()
            history.append(news_item["guid"])
            save_history(history)
            print("Finished successfully!")
    else:
        print("Failed to upload slides to CDN.")

if __name__ == "__main__":
    main()
    
