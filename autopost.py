import os
import sys
import json
import time
import re
import html
from io import BytesIO
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

IG_USER_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
IG_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
TRIGGER_TYPE = os.getenv("TRIGGER_TYPE", "")
IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_FILE = "posted_history.json"

FEEDS = [
    "https://www.thehindu.com/news/national/andhra-pradesh/feeder/default.rss",
    "https://www.thehindu.com/news/national/telangana/feeder/default.rss"
]

UNIQUE_FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=1080&q=80",
    "https://images.unsplash.com/photo-1605379399642-870262d3d051?w=1080&q=80",
    "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=1080&q=80",
    "https://images.unsplash.com/photo-1609766857041-ed402ea8069a?w=1080&q=80",
    "https://images.unsplash.com/photo-1519692933481-e162a57d6721?w=1080&q=80",
]

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

def clean_text(raw_html):
    clean = re.sub(r'<[^>]+>', '', raw_html)
    clean = html.unescape(clean)
    return " ".join(clean.split())

def get_profile_photo():
    for local_name in ["profile.jpg", "profile.png", "avatar.jpg", "avatar.png"]:
        if os.path.exists(local_name):
            try:
                print(f"Loaded local profile photo from repository: {local_name}")
                return Image.open(local_name).convert("RGB")
            except Exception:
                pass

    if IG_USER_ID and IG_ACCESS_TOKEN:
        try:
            url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}?fields=profile_picture_url&access_token={IG_ACCESS_TOKEN}"
            res = requests.get(url, timeout=8).json()
            if "profile_picture_url" in res:
                p_url = res["profile_picture_url"]
                r = requests.get(p_url, timeout=8)
                if r.status_code == 200:
                    print("Fetched profile photo from Instagram account profile.")
                    return Image.open(BytesIO(r.content)).convert("RGB")
        except Exception as e:
            print(f"Notice fetching Instagram profile photo: {e}")

    try:
        r = requests.get("https://images.unsplash.com/photo-1605379399642-870262d3d051?w=1080&q=80", timeout=8)
        if r.status_code == 200:
            return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        pass
    return None

def fetch_top_5_news():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    history = load_history()
    new_stories = []
    fallback_stories = []

    for feed_url in FEEDS:
        try:
            res = requests.get(feed_url, headers=headers, timeout=12)
            root = ET.fromstring(res.content)
            items = root.findall(".//item")

            for item in items:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                guid = item.find("guid").text if item.find("guid") is not None else link

                desc_elem = item.find("description")
                desc_text = clean_text(desc_elem.text) if desc_elem is not None and desc_elem.text else ""

                if not title or not link:
                    continue

                direct_img = ""
                for elem in item.iter():
                    if elem.tag.endswith("content") and "url" in elem.attrib:
                        direct_img = elem.attrib["url"]
                        break
                    if elem.tag == "enclosure" and "url" in elem.attrib:
                        direct_img = elem.attrib["url"]
                        break

                clean_title = title.split(" - ")[0].strip()

                story = {
                    "guid": guid,
                    "title": clean_title,
                    "description": desc_text,
                    "source": "The Hindu",
                    "link": link,
                    "rss_img": direct_img
                }

                if len(fallback_stories) < 5:
                    fallback_stories.append(story)

                if guid not in history and story not in new_stories:
                    new_stories.append(story)

        except Exception as e:
            print(f"Error reading feed {feed_url}: {e}")

    # Combine new stories first, then fill remaining slots with latest fallback stories
    final_stories = list(new_stories)
    for fb in fallback_stories:
        if len(final_stories) >= 5:
            break
        if fb["guid"] not in [s["guid"] for s in final_stories]:
            final_stories.append(fb)

    print(f"Found {len(new_stories)} new stories. Total prepared slides: {len(final_stories)}")
    return final_stories[:5]

def render_cover_slide(profile_photo, total_slides=6):
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), (6, 10, 18))

    if profile_photo:
        photo_w, photo_h = profile_photo.size
        ratio = max(W / photo_w, H / photo_h)
        new_size = (int(photo_w * ratio), int(photo_h * ratio))
        photo_resized = profile_photo.resize(new_size, Image.Resampling.LANCZOS)
        left = (photo_resized.width - W) // 2
        top = (photo_resized.height - H) // 2
        bg_crop = photo_resized.crop((left, top, left + W, top + H))
        canvas.paste(bg_crop, (0, 0))

    overlay = Image.new("RGBA", (W, H), (6, 10, 18, 205))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    try:
        font_tag = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_h1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 52)
        font_subtitle = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        font_footer = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except Exception:
        font_tag = font_h1 = font_subtitle = font_footer = ImageFont.load_default()

    draw.rounded_rectangle([(60, 50), (1020, 110)], radius=14, fill=(12, 18, 32), outline=(50, 85, 140), width=2)
    draw.text((85, 70), "🔴 DAILY REGIONAL ROUNDUP  |  COVER", font=font_tag, fill=(255, 215, 60))
    draw.text((860, 70), f"SLIDE 1/{total_slides}", font=font_tag, fill=(180, 210, 255))

    if profile_photo:
        avatar_size = 280
        avatar_x = (W - avatar_size) // 2
        avatar_y = 190
        thumb = profile_photo.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.ellipse([(0, 0), (avatar_size, avatar_size)], fill=255)

        draw.ellipse([(avatar_x - 6, avatar_y - 6), (avatar_x + avatar_size + 6, avatar_y + avatar_size + 6)], fill=(255, 215, 60))
        draw.ellipse([(avatar_x - 2, avatar_y - 2), (avatar_x + avatar_size + 2, avatar_y + avatar_size + 2)], fill=(10, 16, 28))
        canvas.paste(thumb, (avatar_x, avatar_y), mask)

    card_y = 530
    draw.rounded_rectangle([(60, card_y), (1020, 1150)], radius=24, fill=(10, 16, 28), outline=(45, 75, 125), width=2)
    draw.rectangle([(60, card_y), (1020, card_y + 54)], fill=(18, 28, 50))
    draw.text((85, card_y + 15), "EXECUTIVE BRIEFING  •  ANDHRA & TELANGANA", font=font_tag, fill=(255, 215, 60))

    t_y = card_y + 95
    draw.text((85, t_y), "TODAY'S TOP HEADLINES", font=font_h1, fill=(255, 215, 60))
    t_y += 75
    draw.text((85, t_y), "OF ANDHRA PRADESH", font=font_h1, fill=(255, 255, 255))
    t_y += 75
    draw.text((85, t_y), "& TELANGANA", font=font_h1, fill=(0, 240, 255))
    t_y += 110

    today_str = datetime.now(IST).strftime("%d %B %Y").upper()
    draw.text((85, t_y), "•  5 MAJOR REGIONAL DEVELOPMENTS", font=font_subtitle, fill=(200, 225, 255))
    t_y += 48
    draw.text((85, t_y), f"•  DATE: {today_str}", font=font_subtitle, fill=(180, 205, 240))
    t_y += 48
    draw.text((85, t_y), "•  VERIFIED BY THE HINDU BUREAU", font=font_subtitle, fill=(56, 239, 125))

    draw.rectangle([(0, 1220), (W, H)], fill=(8, 12, 20))
    draw.line([(0, 1220), (W, 1220)], fill=(45, 75, 130), width=2)
    draw.text((W // 2 - 220, 1265), "👉 SWIPE TO READ STORIES ➔", font=font_footer, fill=(255, 215, 60))

    filename = "slide_1.jpg"
    canvas.save(filename, "JPEG", quality=92, optimize=True)
    return filename

def get_unique_slide_image(story, story_index):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    if story.get("rss_img") and story["rss_img"].startswith("http"):
        try:
            r = requests.get(story["rss_img"], headers=headers, timeout=8)
            if r.status_code == 200 and len(r.content) > 5000:
                return Image.open(BytesIO(r.content)).convert("RGB")
        except Exception:
            pass

    try:
        if story.get("link"):
            res = requests.get(story["link"], headers=headers, timeout=6)
            if res.status_code == 200:
                html_text = res.text
                m_desc = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                if m_desc and len(m_desc.group(1).strip()) > len(story.get("description", "")):
                    story["description"] = clean_text(m_desc.group(1).strip())

                m_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                if not m_img:
                    m_img = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html_text, re.IGNORECASE)

                if m_img:
                    img_url = m_img.group(1).strip()
                    blocked = ["googleusercontent.com", "google.com", "gstatic.com", "favicon", "logo"]
                    if img_url.startswith("http") and not any(b in img_url.lower() for b in blocked):
                        r = requests.get(img_url, headers=headers, timeout=8)
                        if r.status_code == 200 and len(r.content) > 5000:
                            return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"Story {story_index}: og:image error: {e}")

    fallback_url = UNIQUE_FALLBACK_IMAGES[(story_index - 1) % len(UNIQUE_FALLBACK_IMAGES)]
    try:
        r = requests.get(fallback_url, headers=headers, timeout=8)
        if r.status_code == 200:
            return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        pass

    return None

def render_news_slide(story, slide_number, story_index, total_slides=6):
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), (6, 10, 16))

    photo = get_unique_slide_image(story, story_index)
    if photo:
        photo_w, photo_h = photo.size
        target_w, target_h = W, 720
        ratio = max(target_w / photo_w, target_h / photo_h)
        new_size = (int(photo_w * ratio), int(photo_h * ratio))
        photo_resized = photo.resize(new_size, Image.Resampling.LANCZOS)
        left = (photo_resized.width - target_w) // 2
        top = (photo_resized.height - target_h) // 2
        photo_cropped = photo_resized.crop((left, top, left + target_w, top + target_h))
        canvas.paste(photo_cropped, (0, 0))

    gradient = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)

    for y in range(160):
        alpha = int(190 * (1 - (y / 160)))
        g_draw.line([(0, y), (W, y)], fill=(4, 6, 10, alpha))

    for y in range(380, H):
        factor = min(1.0, (y - 380) / 280)
        alpha = int(factor * 252)
        g_draw.line([(0, y), (W, y)], fill=(6, 10, 18, alpha))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), gradient).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    try:
        font_badge = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_h1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 44)
        font_card_head = ImageFont.truetype("DejaVuSans-Bold.ttf", 23)
        font_body = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_footer = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        font_tick = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except Exception:
        font_badge = font_h1 = font_card_head = font_body = font_footer = font_tick = ImageFont.load_default()

    draw.rounded_rectangle([(60, 45), (1020, 105)], radius=14, fill=(10, 16, 28), outline=(50, 85, 140), width=2)
    badge_label = "🔴 TOP PRIORITY STORY" if story_index == 1 else f"AP & TS UPDATE (STORY {story_index}/5)"
    draw.text((85, 65), badge_label, font=font_badge, fill=(255, 215, 60))
    draw.text((860, 65), f"SLIDE {slide_number}/{total_slides}", font=font_badge, fill=(180, 210, 255))

    words = story["title"].split()
    lines, curr = [], []
    for w in words:
        if font_h1.getlength(" ".join(curr + [w])) <= 920:
            curr.append(w)
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]
    if curr: lines.append(" ".join(curr))

    hy = 640
    for i, line in enumerate(lines[:3]):
        color = (255, 215, 60) if (story_index == 1 and i == 0) else (255, 255, 255)
        draw.text((60, hy), line, font=font_h1, fill=color)
        hy += 58

    card_y = max(820, hy + 25)
    card_h = 360
    draw.rounded_rectangle([(60, card_y), (1020, card_y + card_h)], radius=18, fill=(12, 18, 30), outline=(40, 65, 110), width=2)
    draw.rectangle([(60, card_y), (1020, card_y + 52)], fill=(18, 30, 52))

    draw.text((85, card_y + 14), "DESCRIPTION", font=font_card_head, fill=(255, 215, 60))
    draw.text((275, card_y + 14), "•  THE HINDU", font=font_card_head, fill=(200, 225, 255))

    badge_x = 445
    badge_y = card_y + 16
    draw.ellipse([(badge_x, badge_y), (badge_x + 22, badge_y + 22)], fill=(29, 155, 240))
    draw.text((badge_x + 4, badge_y + 2), "✓", font=font_tick, fill=(255, 255, 255))

    cy = card_y + 75
    draw.text((85, cy), "Important Points & Core Details:", font=font_card_head, fill=(100, 220, 255))
    cy += 45

    raw_desc = story.get("description", "").strip()
    if not raw_desc or len(raw_desc) < 25:
        raw_desc = f"{story['title']}. Official developing report covered by The Hindu bureau across Andhra Pradesh and Telangana."

    desc_words = raw_desc.split()
    desc_lines = []
    curr_l = []
    for w in desc_words:
        if font_body.getlength(" ".join(curr_l + [w])) <= 880:
            curr_l.append(w)
        else:
            if curr_l: desc_lines.append(" ".join(curr_l))
            curr_l = [w]
    if curr_l: desc_lines.append(" ".join(curr_l))

    for line in desc_lines[:5]:
        draw.text((85, cy), f"•  {line}", font=font_body, fill=(225, 235, 250))
        cy += 44

    draw.rectangle([(0, 1220), (W, H)], fill=(8, 12, 20))
    draw.line([(0, 1220), (W, 1220)], fill=(45, 75, 130), width=2)

    if slide_number < total_slides:
        draw.text((W // 2 - 210, 1265), "👉 SWIPE TO READ NEXT ➔", font=font_footer, fill=(255, 215, 60))
    else:
        draw.text((W // 2 - 230, 1265), "💬 SHARE YOUR THOUGHTS ➔", font=font_footer, fill=(56, 239, 125))

    filename = f"slide_{slide_number}.jpg"
    canvas.save(filename, "JPEG", quality=92, optimize=True)
    return filename

def upload_slide_image(local_filepath):
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

    try:
        with open(local_filepath, "rb") as f:
            r = requests.post("https://catbox.moe/user/api.php", data={"reqtype": "fileupload"}, files={"fileToUpload": f}, timeout=25)
        if r.status_code == 200 and r.text.strip().startswith("http"):
            url = r.text.strip()
            print(f"Uploaded {local_filepath} -> {url}")
            return url
    except Exception as e:
        print(f"Catbox upload notice: {e}")

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

    print(f"ERROR: Could not upload {local_filepath} to any host.")
    sys.exit(1)

def wait_for_container(container_id, max_attempts=15):
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
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("ERROR: INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN is missing!")
        sys.exit(1)

    print(f"Target Instagram Account ID: {IG_USER_ID}")

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

    print("Creating parent carousel container for 6 slides...")
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

    print("Publishing 6-slide carousel to Instagram...")
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
    print("Step 1: Fetching top 5 Andhra Pradesh & Telangana stories...")
    stories = fetch_top_5_news()

    if len(stories) < 5:
        print("Not enough stories available to generate carousel. Exiting.")
        sys.exit(0)

    print(f"Step 2: Preparing profile photo and cover slide...")
    profile_photo = get_profile_photo()
    cover_file = render_cover_slide(profile_photo, total_slides=6)

    slide_files = [cover_file]
    print(f"Step 3: Rendering 5 story slides...")
    for idx, story in enumerate(stories, start=1):
        slide_file = render_news_slide(story, slide_number=idx + 1, story_index=idx, total_slides=6)
        slide_files.append(slide_file)

    print(f"Step 4: Uploading {len(slide_files)} slides to public host...")
    uploaded_urls = []
    for f in slide_files:
        url = upload_slide_image(f)
        uploaded_urls.append(url)

    caption = (
        "🔴 DAILY REGIONAL ROUNDUP | Andhra Pradesh & Telangana\n\n"
        f"1️⃣ {stories[0]['title']}\n"
        f"2️⃣ {stories['title']}\n"
        f"3️⃣ {stories['title']}\n"
        f"4️⃣ {stories['title']}\n"
        f"5️⃣ {stories['title']}\n\n"
        "Swipe across the carousel to read full verified briefs from The Hindu bureau.\n\n"
        "#AndhraPradesh #Telangana #APNews #TelanganaNews #HyderabadNews #Amaravati #DailyNews"
    )

    print("Step 5: Publishing carousel to Instagram...")
    publish_instagram_carousel(uploaded_urls, caption)

    # Save posted guids so duplicate posts are avoided
    history = load_history()
    for s in stories:
        if s["guid"] not in history:
            history.append(s["guid"])
    save_history(history)
    print("Execution completed successfully.")

if __name__ == "__main__":
    main()
