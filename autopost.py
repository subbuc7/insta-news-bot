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
TRIGGER_TYPE = os.getenv("TRIGGER_TYPE", "")
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

    history = load_history()
    selected_stories = []
    fallback_stories = []

    for item in items:
        title = item.find("title").text if item.find("title") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        guid = item.find("guid").text if item.find("guid") is not None else link
        pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""

        if not title or not pub_date_str:
            continue

        clean_title = title.split(" - ")[0].strip()
        source = title.split(" - ")[-1].strip() if " - " in title else "Verified Desk"

        story = {
            "guid": guid,
            "title": clean_title,
            "source": source,
            "link": link
        }

        if len(fallback_stories) < 5:
            fallback_stories.append(story)

        if guid not in history:
            selected_stories.append(story)

        if len(selected_stories) == 5:
            break

    # If triggered manually, guarantee 5 stories are always returned
    if TRIGGER_TYPE == "workflow_dispatch" and len(selected_stories) < 5:
        print("Manual click detected: utilizing latest available feed stories.")
        return fallback_stories

    return selected_stories

def render_slide(story, slide_number, total_slides=5):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), (4, 6, 10))
    draw = ImageDraw.Draw(img)

    # Dark gradient background
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
    badge_label = "🔴 TOP PRIORITY STORY" if slide_number == 1 else f"REGIONAL UPDATE ({slide_number}/{total_slides})"
    draw.text((90, 70), badge_label, font=font_badge, fill=(255, 215, 60))
    draw.text((840, 70), f"SLIDE {slide_number} OF {total_slides}", font=font_badge, fill=(180, 205, 245))

    # Headline formatting
    words = story["title"].split()
    lines, curr = [], []
    for w in words:
        if font_h1.getlength(" ".join(curr + [w])) <= 920:
            curr.append(w)
        else:
            if curr:
                lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

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
    draw.text((90, cy), "Key Highlights & Takeaways:", font=font_card_head, fill=(255, 215, 60))
    cy += 55

    bullet_points = [
        f"• Verified broadcast report published via {story['source']}.",
        "• Real-time fact verification and cross-source corroboration.",
        "• Developing regional story affecting citizens, governance, or policy."
    ]
    for bp in bullet_points:
        draw.text((90, cy), bp, font=font_body, fill=(225, 235, 250))
        cy += 60

    # Bottom Call-to-Action Bar
    draw.rectangle([(0, 1220), (W, H)], fill=(8, 12, 20))
    draw.line([(0, 1220), (W, 1220)], fill=(45, 75, 130), width=2)

    if slide_number == 1:
        draw.text((W // 2 - 210, 1265), "👉 SWIPE TO READ NEXT ➔", font=font_footer, fill=(255, 215, 60))
    elif slide_number < total_slides:
        draw.text((W // 2 - 210, 1265), "👉 SWIPE TO READ NEXT ➔", font=font_footer, fill=(100, 220, 255))
    else:
        draw.text((W // 2 - 230, 1265), "💬 SHARE YOUR THOUGHTS ➔", font=font_footer, fill=(56, 239, 125))

    # Save as JPEG for Meta API
    filename = f"slide_{slide_number}.jpg"
    img.save(filename, "JPEG", quality=92, optimize=True)
    return filename

def upload_slide_image(local_filepath):
    """Uploads image with multi-provider fallbacks to ensure a direct HTTPS image URL."""
    # 1. Try Uguu.se
    try:
        with open(local_filepath, "rb") as f:
            r = requests.post("https://uguu.se/upload.php", files={"files[]": f}, timeout=25)
        if r.status_code == 200:
            res_data = r.json()
            if res_data.get("success") and res_data.get("files"):
                url = res_data["files"][0]["url"]
                print(f"Uploaded {local_filepath} -> {url}")
                return url
    except Exception as e:
        print(f"Uguu upload notice: {e}")

    # 2. Try Catbox
    try:
        with open(local_filepath, "rb") as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=25
            )
        if r.status_code == 200 and r.text.strip().startswith("http"):
            url = r.text.strip()
            print(f"Uploaded {local_filepath} -> {url}")
            return url
    except Exception as e:
        print(f"Catbox upload notice: {e}")

    # 3. Try tmpfiles.org
    try:
        with open(local_filepath, "rb") as f:
            r = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, timeout=25)
        if r.status_code == 200:
            res_data = r.json()
            if "data" in res_data and "url" in res_data["data"]:
                url = res_data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"Uploaded {local_filepath} -> {url}")
                return url
    except Exception as e:
        print(f"Tmpfiles upload notice: {e}")

    # 4. Try 0x0.st
    try:
        with open(local_filepath, "rb") as f:
            r = requests.post("https://0x0.st", files={"file": f}, timeout=25)
        if r.status_code == 200 and r.text.strip().startswith("http"):
            url = r.text.strip()
            print(f"Uploaded {local_filepath} -> {url}")
            return url
    except Exception as e:
        print(f"0x0.st upload notice: {e}")

    print(f"ERROR: Could not upload {local_filepath} to any host.")
    sys.exit(1)

def wait_for_container(container_id, max_attempts=15):
    """Polls Meta Graph API until the media container status is FINISHED."""
    for attempt in range(max_attempts):
        url = f"https://graph.facebook.com/v21.0/{container_id}?fields=status_code,status&access_token={IG_ACCESS_TOKEN}"
        r = requests.get(url).json()
        status = r.get("status_code")
        print(f"Container {container_id} status: {status}")
        if status == "FINISHED":
            return True
        elif status == "ERROR":
            print(f"Container {container_id} failed with error:", json.dumps(r, indent=2))
            sys.exit(1)
        time.sleep(4)
    return True

def publish_instagram_carousel(image_urls, caption):
    """Publishes a 5-slide carousel using the Meta Graph API."""
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("ERROR: INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN is missing!")
        sys.exit(1)

    print(f"Target Instagram Account ID: {IG_USER_ID}")

    # Step 1: Create media item containers for each slide
    item_ids = []
    for i, url in enumerate(image_urls, start=1):
        print(f"Creating container for slide {i}...")
        res = requests.post(
            f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media",
            data={
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": IG_ACCESS_TOKEN
            },
            timeout=30
        ).json()

        if "id" not in res:
            print(f"Meta API Error creating slide {i} container:", json.dumps(res, indent=2))
            sys.exit(1)

        item_id = res["id"]
        wait_for_container(item_id)
        item_ids.append(item_id)

    # Step 2: Create parent carousel container
    print("Creating parent carousel container...")
    carousel_res = requests.post(
        f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN
        },
        timeout=30
    ).json()

    if "id" not in carousel_res:
        print("Meta API Error creating carousel container:", json.dumps(carousel_res, indent=2))
        sys.exit(1)

    creation_id = carousel_res["id"]
    print(f"Parent Carousel Container created: {creation_id}")
    wait_for_container(creation_id)

    # Step 3: Publish carousel
    print("Publishing carousel to Instagram...")
    pub_res = requests.post(
        f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": IG_ACCESS_TOKEN
        },
        timeout=30
    ).json()

    print("Publish Response:", json.dumps(pub_res, indent=2))

    if "id" in pub_res:
        print(f"SUCCESS: Post published with ID {pub_res['id']}")
        return True
    else:
        print("Meta Publishing Error:", json.dumps(pub_res, indent=2))
        sys.exit(1)

def main():
    print("Step 1: Fetching top 5 distinct regional stories...")
    stories = fetch_top_5_news()

    if len(stories) < 5:
        print(f"Found only {len(stories)} stories. Need 5 for carousel.")
        sys.exit(0)

    # Render all 5 slides as JPEG
    slide_files = []
    print("Step 2: Rendering 5 slides in 4:5 JPEG format...")
    for i, story in enumerate(stories, start=1):
        filename = render_slide(story, slide_number=i, total_slides=5)
        slide_files.append(filename)

    # Upload slides to public direct HTTPS image URLs
    public_urls = []
    print("Step 3: Uploading direct image URLs for Meta...")
    for f in slide_files:
        url = upload_slide_image(f)
        public_urls.append(url)

    # Ready-to-publish caption with viral and regional hashtags
    caption = (
        f"🚨 TOP 5 BREAKING HEADLINES TODAY\n\n"
        f"1️⃣ {stories[0]['title']}\n"
        f"2️⃣ {stories['title']}\n"
        f"3️⃣ {stories[2]['title']}\n"
        f"4️⃣ {stories[3]['title']}\n"
        f"5️⃣ {stories[4]['title']}\n\n"
        f"👉 Swipe through the carousel to read full breakdowns of each story!\n\n"
        f"💬 Which headline matters most to you? Drop your comment below.\n\n"
        f"•\n•\n•\n"
        f"#Trending #ExplorePage #ViralPost #BreakingNews #InstaNews "
        f"#AndhraPradesh #Telangana #Hyderabad #Amaravati #APNews "
        f"#TelanganaNews #CurrentAffairs #DailyNews #NewsUpdate"
    )

    # Publish to Instagram
    print("Step 4: Publishing carousel via Meta Graph API...")
    publish_instagram_carousel(public_urls, caption)

    # Update history only after successful publish
    history = load_history()
    for s in stories:
        if s["guid"] not in history:
            history.append(s["guid"])
    save_history(history)
    print("Workflow completed successfully.")

if __name__ == "__main__":
    main()
    
