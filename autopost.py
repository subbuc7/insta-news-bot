import os
import sys
import json
import time
import re
import html
import random
from io import BytesIO
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

IG_USER_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "") or os.getenv("INSTAGRAM_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
TRIGGER_TYPE = os.getenv("TRIGGER_TYPE", "")
IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_FILE = "posted_history.json"

# Authentic Telugu News RSS Feeds covering AP & Telangana
FEEDS = [
    "https://news.google.com/rss?hl=te&gl=IN&ceid=IN:te",
    "https://www.eenadu.net/rss/andhra-pradesh-news.xml",
    "https://www.eenadu.net/rss/telangana-news.xml",
    "https://telugu.oneindia.com/rss/telugu-news-fb.xml"
]

# High-resolution Andhra Pradesh & Telangana fallback images
UNIQUE_FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=1080&q=80",
    "https://images.unsplash.com/photo-1570125909232-eb263c188f7e?w=1080&q=80",
    "https://images.unsplash.com/photo-1577495508048-b635879837f1?w=1080&q=80",
    "https://images.unsplash.com/photo-1590402494587-44b71d7772f6?w=1080&q=80",
    "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1080&q=80"
]

# Pools of dynamic viral hashtags
VIRAL_HASHTAG_POOLS = {
    "core": [
        "#APNews", "#TelanganaNews", "#AndhraPradesh", "#Telangana",
        "#HyderabadNews", "#AmaravatiNews", "#APTSNews", "#TeluguNews"
    ],
    "politics": [
        "#ChandrababuNaidu", "#PawanKalyan", "#RevanthReddy", "#NaraLokesh",
        "#APPolitics", "#TSPolitics", "#TDP", "#Janasena", "#KTR"
    ],
    "breaking": [
        "#TeluguFlashNews", "#BreakingNewsTelugu", "#LatestTeluguNews",
        "#TrendingNewsTelugu", "#TelanganaUpdates", "#AndhraUpdates"
    ],
    "discovery": [
        "#ViralNews", "#DailyNewsUpdate", "#InstaNewsTelugu", "#NewsReels",
        "#ExplorePage", "#TrendingNow", "#ViralPost", "#CurrentAffairsTelugu"
    ]
}

def generate_viral_hashtags():
    """Generates a randomized mix of 8-10 high-engagement hashtags."""
    selected = []
    selected.extend(random.sample(VIRAL_HASHTAG_POOLS["core"], 3))
    selected.extend(random.sample(VIRAL_HASHTAG_POOLS["politics"], 2))
    selected.extend(random.sample(VIRAL_HASHTAG_POOLS["breaking"], 2))
    selected.extend(random.sample(VIRAL_HASHTAG_POOLS["discovery"], 2))
    random.shuffle(selected)
    return " ".join(selected)

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

def ensure_telugu_font():
    font_filename = "NotoSansTelugu-Bold.ttf"
    if not os.path.exists(font_filename):
        try:
            url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Bold.ttf"
            r = requests.get(url, timeout=12)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(font_filename, "wb") as f:
                    f.write(r.content)
                print("Downloaded NotoSansTelugu-Bold.ttf successfully.")
        except Exception as e:
            print(f"Notice downloading Telugu font: {e}")

def get_font(size, bold=True):
    candidates = [
        "NotoSansTelugu-Bold.ttf" if bold else "NotoSansTelugu-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf",
        "/usr/share/fonts/truetype/fonts-telu/lohit_te.ttf",
        "/usr/share/fonts/truetype/lohit-telugu/Lohit-Telugu.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

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
        r = requests.get("https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=1080&q=80", timeout=8)
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
                    "source": "AP TS NEWS",
                    "link": link,
                    "rss_img": direct_img
                }

                if len(fallback_stories) < 5:
                    fallback_stories.append(story)

                if guid not in history and story not in new_stories:
                    new_stories.append(story)

        except Exception as e:
            print(f"Error reading feed {feed_url}: {e}")

    final_stories = list(new_stories)
    for fb in fallback_stories:
        if len(final_stories) >= 5:
            break
        if fb["guid"] not in [s["guid"] for s in final_stories]:
            final_stories.append(fb)

    print(f"Found {len(new_stories)} new stories. Total prepared slides: {len(final_stories)}")
    return final_stories[:5]

def get_unique_slide_image(story, story_index):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1. Direct RSS Image
    if story.get("rss_img") and story["rss_img"].startswith("http"):
        try:
            r = requests.get(story["rss_img"], headers=headers, timeout=8)
            if r.status_code == 200 and len(r.content) > 5000:
                return Image.open(BytesIO(r.content)).convert("RGB")
        except Exception:
            pass

    # 2. Extract og:image from the article link
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
        print(f"Story {story_index}: image extraction notice: {e}")

    # 3. High-Quality Fallback
    fallback_url = UNIQUE_FALLBACK_IMAGES[(story_index - 1) % len(UNIQUE_FALLBACK_IMAGES)]
    try:
        r = requests.get(fallback_url, headers=headers, timeout=8)
        if r.status_code == 200:
            return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        pass

    return None

def draw_channel_logo(draw, x=60, y=40):
    draw.rounded_rectangle([(x, y), (x + 230, y + 60)], radius=12, fill=(10, 16, 32), outline=(220, 38, 38), width=2)
    draw.ellipse([(x + 10, y + 10), (x + 50, y + 50)], fill=(20, 80, 200), outline=(255, 215, 60), width=2)
    font_logo_ap = get_font(26, bold=True)
    font_logo_ts = get_font(18, bold=True)
    draw.text((x + 62, y + 8), "AP", font=font_logo_ap, fill=(235, 30, 30))
    draw.text((x + 62, y + 34), "TS NEWS", font=font_logo_ts, fill=(255, 215, 60))

def render_cover_slide(profile_photo, total_slides=6):
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), (14, 5, 8))

    if profile_photo:
        photo_w, photo_h = profile_photo.size
        ratio = max(W / photo_w, H / photo_h)
        new_size = (int(photo_w * ratio), int(photo_h * ratio))
        photo_resized = profile_photo.resize(new_size, Image.Resampling.LANCZOS)
        left = (photo_resized.width - W) // 2
        top = (photo_resized.height - H) // 2
        bg_crop = photo_resized.crop((left, top, left + W, top + H))
        canvas.paste(bg_crop, (0, 0))

    overlay = Image.new("RGBA", (W, H), (14, 5, 8, 210))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    font_tag = get_font(22, bold=True)
    font_h1 = get_font(52, bold=True)
    font_subtitle = get_font(28, bold=True)
    font_footer = get_font(26, bold=True)

    draw_channel_logo(draw, x=60, y=45)
    draw.text((860, 60), f"SLIDE 1/{total_slides}", font=font_tag, fill=(180, 210, 255))

    if profile_photo:
        avatar_size = 260
        avatar_x = (W - avatar_size) // 2
        avatar_y = 170
        thumb = profile_photo.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.ellipse([(0, 0), (avatar_size, avatar_size)], fill=255)

        draw.ellipse([(avatar_x - 6, avatar_y - 6), (avatar_x + avatar_size + 6, avatar_y + avatar_size + 6)], fill=(255, 215, 60))
        draw.ellipse([(avatar_x - 2, avatar_y - 2), (avatar_x + avatar_size + 2, avatar_y + avatar_size + 2)], fill=(14, 5, 8))
        canvas.paste(thumb, (avatar_x, avatar_y), mask)

    card_y = 490
    draw.rounded_rectangle([(60, card_y), (1020, 1140)], radius=24, fill=(18, 8, 12), outline=(120, 30, 35), width=2)
    draw.rectangle([(60, card_y), (1020, card_y + 56)], fill=(180, 25, 30))
    draw.text((85, card_y + 14), "🔴 AP & TS NEWS BULLETIN  |  నేటి తాజా వార్తలు", font=font_tag, fill=(255, 255, 255))

    t_y = card_y + 90
    draw.text((85, t_y), "ఆంధ్రప్రదేశ్ & తెలంగాణ", font=font_h1, fill=(255, 220, 0))
    t_y += 75
    draw.text((85, t_y), "నేటి టాప్ 5 ముఖ్యాంశాలు", font=font_h1, fill=(255, 255, 255))
    t_y += 100

    today_str = datetime.now(IST).strftime("%d %B %Y").upper()
    draw.text((85, t_y), "•  5 ప్రధాన తాజా పరిణామాలు & వార్తలు", font=font_subtitle, fill=(240, 230, 210))
    t_y += 48
    draw.text((85, t_y), f"•  తేదీ: {today_str}", font=font_subtitle, fill=(255, 215, 60))
    t_y += 48
    draw.text((85, t_y), "•  AP TS NEWS - ప్రజల కోసం.. ప్రజలతో", font=font_subtitle, fill=(56, 239, 125))

    draw.rectangle([(0, 1220), (W, H)], fill=(10, 4, 6))
    draw.line([(0, 1220), (W, 1220)], fill=(180, 25, 30), width=2)
    draw.text((W // 2 - 210, 1265), "👉 SWIPE TO READ STORIES ➔", font=font_footer, fill=(255, 215, 60))

    filename = "slide_1.jpg"
    canvas.save(filename, "JPEG", quality=92, optimize=True)
    return filename

def render_news_slide(story, slide_number, story_index, total_slides=6):
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), (14, 5, 8))

    # 1. Top Photo of Leader / Event (Takes upper 48% of the canvas)
    photo = get_unique_slide_image(story, story_index)
    if photo:
        photo_w, photo_h = photo.size
        target_w, target_h = W, 640
        ratio = max(target_w / photo_w, target_h / photo_h)
        new_size = (int(photo_w * ratio), int(photo_h * ratio))
        photo_resized = photo.resize(new_size, Image.Resampling.LANCZOS)
        left = (photo_resized.width - target_w) // 2
        top = (photo_resized.height - target_h) // 2
        photo_cropped = photo_resized.crop((left, top, left + target_w, top + target_h))
        canvas.paste(photo_cropped, (0, 0))

    # 2. Gradient transition: blends photo bottom into dark crimson base
    gradient = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(320, 640):
        factor = (y - 320) / 320.0
        alpha = int(factor * 255)
        g_draw.line([(0, y), (W, y)], fill=(14, 5, 8, alpha))
    for y in range(640, H):
        g_draw.line([(0, y), (W, y)], fill=(14, 5, 8, 255))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), gradient).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 3. Channel Logo at Top Right
    draw_channel_logo(draw, x=800, y=35)

    # 4. Slide Badge at Top Left
    font_badge = get_font(20, bold=True)
    draw.rounded_rectangle([(50, 40), (220, 85)], radius=12, fill=(10, 16, 32), outline=(255, 215, 60), width=2)
    draw.text((70, 52), f"STORY {story_index}/5", font=font_badge, fill=(255, 215, 60))

    # 5. Bold Telugu Headline (Yellow Top Line, White Following Lines)
    font_h1 = get_font(42, bold=True)
    font_sub_banner = get_font(22, bold=True)
    font_body = get_font(24, bold=False)
    font_footer = get_font(22, bold=True)

    words = story["title"].split()
    lines, curr = [], []
    for w in words:
        if font_h1.getlength(" ".join(curr + [w])) <= 960:
            curr.append(w)
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]
    if curr: lines.append(" ".join(curr))

    hy = 580
    for i, line in enumerate(lines[:3]):
        color = (255, 225, 0) if i == 0 else (255, 255, 255)
        # Drop shadow for readability
        draw.text((52, hy + 2), line, font=font_h1, fill=(0, 0, 0))
        draw.text((50, hy), line, font=font_h1, fill=color)
        hy += 56

    # 6. Stylized Sub-Headline Banner / Quote Ribbon
    banner_y = max(750, hy + 20)
    draw.rounded_rectangle([(50, banner_y), (1030, banner_y + 60)], radius=12, fill=(255, 245, 220), outline=(255, 215, 60), width=2)
    sub_title = "తాజా ప్రకటన & ముఖ్యాంశాలు • AP TS NEWS SPECIAL"
    draw.text((75, banner_y + 16), sub_title, font=font_sub_banner, fill=(150, 15, 20))

    # 7. Detailed Bullet Points Container (Dark Crimson Card)
    card_y = banner_y + 80
    card_h = min(360, 1220 - card_y)
    draw.rounded_rectangle([(50, card_y), (1030, card_y + card_h)], radius=20, fill=(20, 8, 12), outline=(120, 30, 35), width=2)
    draw.rectangle([(50, card_y), (1030, card_y + 46)], fill=(150, 20, 25))
    draw.text((75, card_y + 12), "ముఖ్యమైన వివరాలు (KEY HIGHLIGHTS)", font=font_badge, fill=(255, 255, 255))

    cy = card_y + 65
    raw_desc = story.get("description", "").strip()
    if not raw_desc or len(raw_desc) < 20:
        raw_desc = f"{story['title']}. ఆంధ్రప్రదేశ్ మరియు తెలంగాణ సమగ్ర తాజా సమాచారం వివరాలు."

    desc_words = raw_desc.split()
    desc_lines = []
    curr_l = []
    for w in desc_words:
        if font_body.getlength(" ".join(curr_l + [w])) <= 920:
            curr_l.append(w)
        else:
            if curr_l: desc_lines.append(" ".join(curr_l))
            curr_l = [w]
    if curr_l: desc_lines.append(" ".join(curr_l))

    for line in desc_lines[:4]:
        draw.ellipse([(75, cy + 8), (87, cy + 20)], fill=(230, 40, 40))
        draw.text((105, cy), line, font=font_body, fill=(245, 240, 230))
        cy += 50

    # 8. Bottom Footer Banner
    draw.rectangle([(0, 1245), (W, H)], fill=(8, 3, 5))
    draw.line([(0, 1245), (W, 1245)], fill=(200, 30, 35), width=2)
    draw.text((60, 1285), "AP TS NEWS - ప్రజల కోసం.. ప్రజలతో", font=font_footer, fill=(255, 215, 60))
    draw.text((780, 1285), "SWIPE FOR NEXT ➔", font=font_footer, fill=(240, 240, 240))

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
        time.sleep(2)

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
    ensure_telugu_font()

    print("Step 1: Fetching top 5 Andhra Pradesh & Telangana stories in Telugu...")
    stories = fetch_top_5_news()

    if len(stories) < 5:
        print("Not enough stories available to generate carousel. Exiting.")
        sys.exit(0)

    print("Step 2: Preparing profile photo and cover slide...")
    profile_photo = get_profile_photo()
    cover_file = render_cover_slide(profile_photo, total_slides=6)

    slide_files = [cover_file]
    print("Step 3: Rendering 5 story slides matching AP TS NEWS template...")
    for idx, story in enumerate(stories, start=1):
        slide_file = render_news_slide(story, slide_number=idx + 1, story_index=idx, total_slides=6)
        slide_files.append(slide_file)

    print(f"Step 4: Uploading {len(slide_files)} slides to public host...")
    uploaded_urls = []
    for f in slide_files:
        url = upload_slide_image(f)
        uploaded_urls.append(url)

    headline_lines = "\n".join([f"{i}️⃣ {s['title']}" for i, s in enumerate(stories[:5], 1)])
    viral_tags = generate_viral_hashtags()

    caption = (
        "🔴 నేటి తాజా వార్తలు | AP & TS NEWS SPECIAL\n\n"
        f"{headline_lines}\n\n"
        "ఆంధ్రప్రదేశ్ మరియు తెలంగాణ సమగ్ర తాజా వార్తలు, విశ్లేషణల కోసం స్వైప్ చేయండి.\n\n"
        f"{viral_tags}"
    )

    print("Step 5: Publishing carousel to Instagram...")
    publish_instagram_carousel(uploaded_urls, caption)

    history = load_history()
    for s in stories:
        if s["guid"] not in history:
            history.append(s["guid"])
    save_history(history)
    print("Execution completed successfully.")

if __name__ == "__main__":
    main()
