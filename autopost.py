import os
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
IG_USER_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
IG_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_FILE = "posted_history.json"

RSS_FEEDS = [
    ("Google News Telugu", "https://news.google.com/rss?hl=te&gl=IN&ceid=IN:te"),
    ("Eenadu AP", "https://www.eenadu.net/rss/andhra-pradesh-news.xml"),
    ("Eenadu TS", "https://www.eenadu.net/rss/telangana-news.xml"),
    ("BBC Telugu", "https://feeds.bbci.co.uk/telugu/rss.xml"),
]

# ==========================================
# FONT LOADER & DUAL-FONT ENGINE
# ==========================================
def setup_fonts():
    """Downloads NotoSansTelugu if missing, and loads both English & Telugu fonts."""
    telugu_font_path = "NotoSansTelugu-Bold.ttf"
    if not os.path.exists(telugu_font_path):
        print("Downloading NotoSansTelugu-Bold.ttf...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Bold.ttf"
        try:
            r = requests.get(url, timeout=20)
            with open(telugu_font_path, "wb") as f:
                f.write(r.content)
            print("Downloaded Telugu font successfully.")
        except Exception as e:
            print(f"Warning: Could not download Telugu font ({e}). Using system fonts.")

    # Locate English font (DejaVuSans-Bold)
    english_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if not os.path.exists(english_font_path):
        english_font_path = "DejaVuSans-Bold.ttf"

    def fe(size):
        try:
            return ImageFont.truetype(english_font_path, size)
        except Exception:
            return ImageFont.load_default()

    def ft(size):
        try:
            return ImageFont.truetype(telugu_font_path, size)
        except Exception:
            return fe(size)

    return {
        # Single English fonts for UI badges, logos, and footers
        "badge_en": fe(22),
        "logo_en": fe(32),
        "footer_en": fe(20),
        "body_en": fe(24),
        # Font pairs (Telugu, English) for mixed text rendering
        "headline": (ft(40), fe(40)),
        "subhead": (ft(22), fe(22)),
        "card_header": (ft(22), fe(22)),
        "body": (ft(24), fe(24)),
        "footer_te": (ft(20), fe(20))
    }

def is_telugu_char(ch):
    return '\u0c00' <= ch <= '\u0c7f'

def draw_text_mixed(draw, xy, text, font_te, font_en, fill=(255, 255, 255)):
    """Renders mixed Telugu and English text without missing font boxes."""
    x, y = xy
    tokens = []
    curr = []
    curr_is_te = None

    for ch in text:
        ch_te = is_telugu_char(ch)
        if curr_is_te is None:
            curr_is_te = ch_te
            curr.append(ch)
        elif ch == ' ' or ch in '.,:;!?()-[]/|•%₹+<>':
            curr.append(ch)
        elif ch_te == curr_is_te:
            curr.append(ch)
        else:
            tokens.append((''.join(curr), curr_is_te))
            curr = [ch]
            curr_is_te = ch_te

    if curr:
        tokens.append((''.join(curr), curr_is_te))

    for segment, te_flag in tokens:
        font_to_use = font_te if te_flag else font_en
        draw.text((x, y), segment, font=font_to_use, fill=fill)
        x += font_to_use.getlength(segment)
    return x

def get_mixed_width(text, font_te, font_en):
    w = 0.0
    tokens = []
    curr = []
    curr_is_te = None
    for ch in text:
        ch_te = is_telugu_char(ch)
        if curr_is_te is None:
            curr_is_te = ch_te
            curr.append(ch)
        elif ch == ' ' or ch in '.,:;!?()-[]/|•%₹+<>':
            curr.append(ch)
        elif ch_te == curr_is_te:
            curr.append(ch)
        else:
            tokens.append((''.join(curr), curr_is_te))
            curr = [ch]
            curr_is_te = ch_te
    if curr:
        tokens.append((''.join(curr), curr_is_te))

    for seg, te in tokens:
        f = font_te if te else font_en
        w += f.getlength(seg)
    return w

def wrap_text_mixed(text, font_te, font_en, max_width):
    words = text.split(' ')
    lines = []
    curr_line = []
    for word in words:
        test = ' '.join(curr_line + [word])
        if get_mixed_width(test, font_te, font_en) <= max_width:
            curr_line.append(word)
        else:
            if curr_line:
                lines.append(' '.join(curr_line))
            curr_line = [word]
    if curr_line:
        lines.append(' '.join(curr_line))
    return lines

# ==========================================
# HISTORY & NEWS FETCHING
# ==========================================
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
        json.dump(history[-150:], f, indent=2)

def fetch_top_stories(limit=5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    history = load_history()
    stories = []

    print(f"Step 1: Fetching top {limit} Andhra Pradesh & Telangana stories in Telugu...")
    for feed_name, url in RSS_FEEDS:
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code != 200:
                continue
            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            for item in items:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                guid = item.find("guid").text if item.find("guid") is not None else link

                if not title or guid in history:
                    continue

                clean_title = title.split(" - ")[0].strip()
                source = title.split(" - ")[-1].strip() if " - " in title else feed_name

                stories.append({
                    "guid": guid,
                    "title": clean_title,
                    "source": source,
                    "link": link
                })
                if len(stories) >= limit:
                    return stories
        except Exception as e:
            print(f"Error reading feed {url}: {e}")

    return stories

# ==========================================
# SLIDE RENDERING (AP TS NEWS TEMPLATE)
# ==========================================
def render_story_slide(story, index, total, fonts, output_filename):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), (14, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background image (upper 48%)
    bg_height = int(H * 0.48)
    bg_photo_path = "profile.jpg" if os.path.exists("profile.jpg") else None
    
    if bg_photo_path:
        try:
            photo = Image.open(bg_photo_path).convert("RGB")
            photo = photo.resize((W, bg_height), Image.Resampling.LANCZOS)
            img.paste(photo, (0, 0))
        except Exception:
            pass

    # Smooth dark crimson gradient
    grad = Image.new("RGBA", (W, bg_height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for y in range(bg_height):
        alpha = int((y / bg_height) ** 2.2 * 255)
        gdraw.line([(0, y), (W, y)], fill=(20, 0, 2, alpha))
    img.paste(grad, (0, 0), grad)

    # 2. Top UI Badges
    draw.rounded_rectangle([(50, 45), (250, 95)], radius=10, fill=(20, 20, 20), outline=(255, 215, 0), width=2)
    draw.text((70, 58), f"STORY {index}/{total}", font=fonts["badge_en"], fill=(255, 215, 0))

    # AP TS NEWS Logo
    draw.rounded_rectangle([(800, 45), (1030, 100)], radius=12, fill=(15, 20, 30), outline=(220, 40, 40), width=2)
    draw.text((820, 54), "AP", font=fonts["logo_en"], fill=(235, 45, 45))
    draw.text((875, 54), "TS NEWS", font=fonts["logo_en"], fill=(255, 215, 0))

    # 3. Dual-Color Telugu Headline
    ft_h, fe_h = fonts["headline"]
    wrapped_headlines = wrap_text_mixed(story["title"], ft_h, fe_h, 980)
    hy = bg_height + 25

    for i, line in enumerate(wrapped_headlines[:2]):
        color = (255, 220, 20) if i == 0 else (255, 255, 255)
        draw_text_mixed(draw, (50, hy), line, ft_h, fe_h, fill=color)
        hy += 62

    # 4. Contrast Sub-Headline Ribbon
    ribbon_y = hy + 15
    draw.rounded_rectangle([(50, ribbon_y), (1030, ribbon_y + 55)], radius=8, fill=(255, 245, 220))
    ft_sub, fe_sub = fonts["subhead"]
    sub_text = f"తాజా ప్రకటన  |  ముఖ్యాంశాలు  |  {story['source']}"
    draw_text_mixed(draw, (70, ribbon_y + 14), sub_text, ft_sub, fe_sub, fill=(110, 5, 10))

    # 5. Bullet Points Card Container
    card_y = ribbon_y + 75
    card_h = 490
    draw.rounded_rectangle([(50, card_y), (1030, card_y + card_h)], radius=14, fill=(26, 2, 4), outline=(130, 15, 20), width=2)
    
    # Red Card Header
    draw.rounded_rectangle([(50, card_y), (1030, card_y + 50)], radius=14, fill=(160, 15, 20))
    ft_ch, fe_ch = fonts["card_header"]
    draw_text_mixed(draw, (75, card_y + 12), "ముఖ్యమైన వివరాలు (KEY HIGHLIGHTS)", ft_ch, fe_ch, fill=(255, 255, 255))

    # Bullets Content
    ft_b, fe_b = fonts["body"]
    by = card_y + 75
    sample_bullets = [
        "ఈ కథనం గురించిన పూర్తి వివరాలు పరిశీలించండి.",
        f"సోర్స్ రిపోర్ట్: {story['source']} ద్వారా ధృవీకరించబడిన సమాచారం.",
        "ప్రజా ప్రయోజనార్థం అందించిన తాజా బులిటెన్ అప్‌డేట్.",
        "మరిన్ని నిరంతర వార్తల కోసం మా పేజీని ఫాలో అవ్వండి."
    ]

    for bullet in sample_bullets:
        draw.text((75, by), "•", font=fonts["body_en"], fill=(235, 45, 45))
        draw_text_mixed(draw, (105, by), bullet, ft_b, fe_b, fill=(240, 240, 240))
        draw.line([(75, by + 44), (1005, by + 44)], fill=(45, 8, 12), width=1)
        by += 68

    # 6. Footer Ribbon
    draw.rectangle([(0, 1260), (W, H)], fill=(10, 0, 2))
    draw.line([(0, 1260), (W, 1260)], fill=(180, 20, 25), width=2)
    
    draw.text((50, 1285), "AP TS NEWS", font=fonts["footer_en"], fill=(255, 215, 0))
    ft_f, fe_f = fonts["footer_te"]
    draw_text_mixed(draw, (190, 1285), "- ప్రజల కోసం.. ప్రజలతో", ft_f, fe_f, fill=(200, 200, 200))
    draw.text((810, 1285), "SWIPE FOR MORE >", font=fonts["footer_en"], fill=(255, 215, 0))

    img.save(output_filename, "JPEG", quality=95)
    return output_filename

# ==========================================
# PUBLIC IMAGE UPLOADER
# ==========================================
def upload_slide(filepath):
    try:
        with open(filepath, "rb") as f:
            res = requests.post("https://d.upaw.se/", files={"file": f}, timeout=30)
            if res.status_code in [200, 201]:
                data = res.json()
                return data.get("url")
    except Exception as e:
        print(f"Error uploading {filepath}: {e}")
    return None

# ==========================================
# INSTAGRAM GRAPH API PUBLISHING
# ==========================================
def publish_carousel_to_instagram(image_urls, caption):
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("Instagram credentials not found. Saved images locally.")
        return

    print(f"Step 5: Publishing carousel with {len(image_urls)} slides to Instagram...")
    container_ids = []

    for i, url in enumerate(image_urls):
        print(f"Creating container for slide {i+1}...")
        url_post = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
        payload = {
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": IG_ACCESS_TOKEN
        }
        res = requests.post(url_post, data=payload, timeout=20).json()
        cid = res.get("id")
        if not cid:
            print(f"Failed to create slide container: {res}")
            return
        container_ids.append(cid)
        time.sleep(2)

    print("Creating parent carousel container...")
    parent_payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(container_ids),
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    res_parent = requests.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media", data=parent_payload, timeout=20).json()
    parent_cid = res_parent.get("id")
    if not parent_cid:
        print(f"Failed parent container: {res_parent}")
        return

    time.sleep(10)

    print(f"Publishing carousel container {parent_cid}...")
    publish_payload = {
        "creation_id": parent_cid,
        "access_token": IG_ACCESS_TOKEN
    }
    pub_res = requests.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish", data=publish_payload, timeout=25).json()
    print("Publish Response:", pub_res)

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    fonts = setup_fonts()
    stories = fetch_top_stories(limit=5)
    
    if not stories:
        print("No new stories found. Exiting.")
        sys.exit(0)

    slide_files = []
    print(f"Rendering {len(stories)} story slides...")
    for idx, story in enumerate(stories, start=1):
        filename = f"slide_{idx}.jpg"
        render_story_slide(story, idx, len(stories), fonts, filename)
        slide_files.append(filename)

    uploaded_urls = []
    for sf in slide_files:
        url = upload_slide(sf)
        if url:
            print(f"Uploaded {sf} -> {url}")
            uploaded_urls.append(url)

    if len(uploaded_urls) == len(slide_files):
        today_str = datetime.now(IST).strftime("%d %B %Y")
        caption = (
            f"🔴 నేటి తాజా వార్తలు | AP & TS NEWS SPECIAL ({today_str})\n\n"
            f"ఆంధ్రప్రదేశ్ మరియు తెలంగాణ రాష్ట్రాల తాజా ముఖ్య వార్తలను స్లైడ్ చేయండి.\n\n"
            f"👉 నిరంతర వార్తల కోసం మా పేజీని ఫాలో అవ్వండి: @_ap_ts_news\n\n"
            f"#APNews #TSNews #AndhraPradesh #Telangana #TeluguNews #APTSNews"
        )
        publish_carousel_to_instagram(uploaded_urls, caption)

        history = load_history()
        for s in stories:
            history.append(s["guid"])
        save_history(history)
        print("All stories processed and history saved successfully.")
    else:
        print("Failed to upload all slides. Aborting publish.")

if __name__ == "__main__":
    main()
