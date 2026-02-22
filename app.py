"""
VibeMacros — Hybrid AI Nutrition Tracker
A mobile-responsive Streamlit app that uses Gemini Vision (Forensic Nutritionist)
to analyze food photos, calculates macros via local DB + USDA API fallback,
and lets users adjust quantities with unit toggles before saving to a
detailed nutrient log.
"""

import streamlit as st
from google import genai
from google.genai import types
import json
import os
import re
import requests
import textwrap
import pandas as pd
from datetime import datetime, date
from PIL import Image, ImageOps
import concurrent.futures
from io import BytesIO
from fuzzywuzzy import process

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VibeMacros",
    page_icon="logo",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
    --bg-primary: #020204;
    --bg-card: #080a10;
    --bg-card-hover: #0c101a;
    --accent-gradient: linear-gradient(135deg, #00f3ff 0%, #0066ff 100%);
    --accent-red-grad: linear-gradient(135deg, #ff3366 0%, #ff0033 100%);
    --accent-green-grad: linear-gradient(135deg, #00ffcc 0%, #00cc99 100%);
    --accent-green: #00ffcc;
    --accent-blue: #00f3ff;
    --accent-purple: #0066ff;
    --accent-orange: #ff9900;
    --accent-pink: #ff00ff;
    --text-primary: #e0f2fe;
    --text-secondary: #94a3b8;
    --text-muted: #475569;
    --border-subtle: rgba(0, 243, 255, 0.15);
    --glow-primary: rgba(0, 243, 255, 0.3);
}

/* ── Global ────────────────────────────────────── */
.stApp {
    background: var(--bg-primary) !important;
    font-family: 'Inter', sans-serif !important;
}

.block-container {
    max-width: 720px !important;
    padding: 1rem 1.2rem !important;
}

h1, h2, h3, h4, h5, h6, p {
    font-family: 'Inter', sans-serif !important;
}

/* ── Header ────────────────────────────────────── */
.app-header {
    text-align: center;
    padding: 2rem 0 1.5rem;
}
.app-header h1 {
    font-size: 2.6rem;
    font-weight: 900;
    background: var(--accent-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    letter-spacing: -1px;
}
.app-header p {
    color: var(--text-secondary);
    font-size: 0.95rem;
    margin-top: 0.3rem;
    font-weight: 400;
}

/* ── Cards ─────────────────────────────────────── */
.macro-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 1.3rem;
    margin-bottom: 1rem;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.macro-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--accent-gradient);
    border-radius: 16px 16px 0 0;
}
.food-name {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 0.2rem;
}
.food-source {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 0.8rem;
}
.source-local {
    background: rgba(0, 214, 143, 0.15);
    color: var(--accent-green);
    border: 1px solid rgba(0, 214, 143, 0.3);
}
.source-usda {
    background: rgba(255, 159, 67, 0.15);
    color: var(--accent-orange);
    border: 1px solid rgba(255, 159, 67, 0.3);
}
.source-ai {
    background: rgba(255, 107, 157, 0.15);
    color: var(--accent-pink);
    border: 1px solid rgba(255, 107, 157, 0.3);
}

.history-card {
    background: var(--bg-card);
    border-radius: 16px;
    padding: 1.2rem;
    margin-bottom: 1rem;
    border: 1px solid var(--border-subtle);
    transition: all 0.3s ease-out;
}

.history-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 15px var(--glow-primary);
    border-color: rgba(0, 243, 255, 0.4);
}

.macro-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem;
    margin-top: 0.5rem;
}
.macro-item {
    text-align: center;
    padding: 0.6rem 0.3rem;
    background: rgba(255,255,255,0.03);
    border-radius: 10px;
    border: 1px solid var(--border-subtle);
}
.macro-value {
    font-size: 1.2rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.2;
}
.macro-label {
    font-size: 0.65rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}

/* ── Summary Card ──────────────────────────────── */
.summary-card {
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.12) 0%, rgba(118, 75, 162, 0.12) 100%);
    border: 1px solid rgba(102, 126, 234, 0.25);
    border-radius: 20px;
    padding: 1.5rem;
    margin: 1.5rem 0;
    text-align: center;
}
.summary-title {
    font-size: 0.8rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.8rem;
    font-weight: 600;
}
.summary-calories {
    font-size: 3rem;
    font-weight: 900;
    background: var(--accent-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1;
    margin-bottom: 0.5rem;
}
.summary-macros {
    display: flex;
    justify-content: center;
    gap: 2rem;
    margin-top: 0.8rem;
}
.summary-macro-item {
    text-align: center;
}
.summary-macro-value {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--text-primary);
}
.summary-macro-label {
    font-size: 0.7rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Progress bar ──────────────────────────────── */
.daily-progress-wrap {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 1.2rem;
    margin: 1rem 0;
}
.progress-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.6rem;
}
.progress-label {
    font-size: 0.8rem;
    color: var(--text-secondary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.progress-value {
    font-size: 0.85rem;
    color: var(--text-primary);
    font-weight: 700;
}
.progress-bar-bg {
    background: rgba(255,255,255,0.06);
    border-radius: 10px;
    height: 12px;
    overflow: hidden;
    position: relative;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 10px;
    transition: width 0.6s ease;
}
.fill-green { background: var(--accent-green-grad); }
.fill-red { background: var(--accent-red-grad); }
.fill-blue { background: var(--accent-gradient); }

/* ── Upload zone ───────────────────────────────── */
[data-testid="stFileUploader"] {
    border: 2px dashed rgba(102, 126, 234, 0.3) !important;
    border-radius: 16px !important;
    background: rgba(102, 126, 234, 0.04) !important;
    padding: 1rem !important;
    transition: all 0.3s ease !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(102, 126, 234, 0.5) !important;
    background: rgba(102, 126, 234, 0.08) !important;
}

/* ── Buttons ───────────────────────────────────── */
.stButton > button {
    background: var(--accent-gradient) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.7rem 2rem !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.3px !important;
    transition: all 0.3s ease !important;
    width: 100% !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px var(--glow-purple) !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
# Ideal Nutrient Targets for a 27-year-old active male
IDEAL_TARGETS = {
    "calories": 2500,
    "protein": 180,  # g
    "carbs": 300,    # g
    "fat": 80,       # g
}

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_log.csv")
MEAL_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meal_logs.csv")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "food_db.json")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# Unit conversion factors (to grams)
UNIT_FACTORS = {
    "grams": 1,
    "handful": 40,
    "cup": 150,
    "spoon": 15,
    "ml": 1,
}

# ─── Load Food Database ──────────────────────────────────────────────────────
@st.cache_data
def load_food_db():
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ─── Gemini Setup ─────────────────────────────────────────────────────────────
def get_gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

GEMINI_MODEL = "gemini-2.5-flash"

# ─── USDA API ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usda_macros(food_name: str) -> dict | None:
    """Fetch macros from USDA FoodData Central API."""
    try:
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {
            "api_key": st.secrets["USDA_API_KEY"],
            "query": food_name,
            "pageSize": 1,
            "dataType": ["Survey (FNDDS)"],
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("foods"):
            return None

        nutrients = data["foods"][0].get("foodNutrients", [])
        macros = {
            "calories_per_100g": 0,
            "protein_per_100g": 0,
            "carbs_per_100g": 0,
            "fat_per_100g": 0,
            "fiber_per_100g": 0,
        }
        nutrient_map = {
            "Energy": "calories_per_100g",
            "Protein": "protein_per_100g",
            "Carbohydrate, by difference": "carbs_per_100g",
            "Total lipid (fat)": "fat_per_100g",
            "Fiber, total dietary": "fiber_per_100g",
        }
        for n in nutrients:
            name = n.get("nutrientName", "")
            for key, field in nutrient_map.items():
                if key in name:
                    macros[field] = round(n.get("value", 0), 1)
                    break
        return macros
    except Exception:
        return None

# ─── Fuzzy Match ──────────────────────────────────────────────────────────────
def fuzzy_match_db(item_name: str, db: list) -> tuple:
    """Return (matched_entry, score) or (None, 0)."""
    # Special handling for "Hidden Fat" or oil
    if "hidden fat" in item_name.lower() or "oil" in item_name.lower():
         return {
            "name": "Hidden Fat (Oil)",
            "calories_per_100g": 884,
            "protein_per_100g": 0,
            "carbs_per_100g": 0,
            "fat_per_100g": 100,
            "fiber_per_100g": 0
         }, 100

    names = [f["name"] for f in db]
    result = process.extractOne(item_name, names)
    if result and result[1] >= 75:
        matched = next(f for f in db if f["name"] == result[0])
        return matched, result[1]
    return None, 0

# ─── Calculate Macros ────────────────────────────────────────────────────────
def calculate_macros(macro_entry: dict, weight_g: float) -> dict:
    """Scale macros from per-100g to actual weight."""
    factor = weight_g / 100.0
    return {
        "calories": round(macro_entry["calories_per_100g"] * factor, 1),
        "protein": round(macro_entry["protein_per_100g"] * factor, 1),
        "carbs": round(macro_entry["carbs_per_100g"] * factor, 1),
        "fat": round(macro_entry["fat_per_100g"] * factor, 1),
        "fiber": round(macro_entry.get("fiber_per_100g", 0) * factor, 1),
    }

# ─── Analyze with Gemini ─────────────────────────────────────────────────────
def analyze_food_images(images: list) -> list:
    """Send images to Gemini and return detected food items."""
    client = get_gemini_client()

    prompt = """You are an Elite Forensic Nutritionist. Your primary directive is to synthesize multiple images into a singular volumetric estimate.

1. Surface Analysis (Oil Detection):
Scrutinize the 'Top-Down' image for specular highlights (sheen), surface tension markers, and 'pooling' at the base of ingredients.
Classify oil levels: 'None' (dry), 'Light' (misted/steamed), 'Medium' (sautéed/shiny), 'Heavy' (deep-fried/pooled).
If oil is detected, automatically add a 'Hidden Fat' entry in the JSON based on the surface area of the shine.

2. Volumetric Synthesis:
Compare the 'Top View' (X-Y axis) with the 'Side View' (Z-axis).
Calculate the 'mound height' relative to the rim of the container.
If the food is flat (e.g., a pancake), prioritize the Top View. If the food is piled (e.g., pasta), use the Side View to calculate a 'pile multiplier' (1.5x - 3x surface area).

3. Accuracy Guardrails:
Cross-reference the identified items with the local 'food_db.json'.
If the user's 'Side View' contradicts the 'Top View' (e.g., a shallow bowl that looked deep), prioritize the side view for volume.

Return ONLY a valid JSON array. No other text, no markdown, no code fences.
Each element must have exactly these keys:
- "name": string (common food name, e.g. "Chicken Breast", "White Rice")
- "estimated_weight_g": number (integer, estimated grams)

Example output:
[{"name": "Chicken Breast", "estimated_weight_g": 150}, {"name": "Hidden Fat", "estimated_weight_g": 15}]
"""

    # Build content parts for the new SDK
    contents = [prompt]
    for img in images:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True)
        buf.seek(0)
        image_part = types.Part.from_bytes(data=buf.read(), mime_type="image/jpeg")
        contents.append(image_part)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
        )
        text = response.text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        items = json.loads(text)
        if isinstance(items, list):
            return items
    except Exception as e:
        st.error(f"Gemini analysis error: {e}")

    return []

def generate_meal_summary(image_path: str, ingredients: list, total_macros: dict) -> dict:
    """Generate a high-level summary of the meal using Gemini."""
    client = get_gemini_client()
    
    ingredients_text = ", ".join([f"{i['name']} ({i['weight_g']:.0f}g)" for i in ingredients])
    macro_text = f"{total_macros['calories']:.0f}kcal, P:{total_macros['protein']:.1f}g, C:{total_macros['carbs']:.1f}g, F:{total_macros['fat']:.1f}g"

    prompt = f"""Analyze this meal image and ingredient data.
Ingredients: {ingredients_text}
Macros: {macro_text}

Return query a valid JSON object (no markdown) with these keys:
- "name": Creative and appetizing name for the dish (e.g. "Spicy Chicken Burrito Bowl")
- "portion_desc": Brief size description (e.g. "Generous Portion", "Light Snack")
- "rating": Integer 1-10 rating of nutritional quality (10=perfectly balanced/healthy)
- "reason": Short 1-sentence reason for the rating.
"""
    
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        
        contents = [
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg" if image_path.endswith(".jpg") else "image/png")
        ]
        
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
        )
        text = response.text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as e:
        print(f"Summary Gen Error: {e}")
        return {
            "name": "Meal Log",
            "portion_desc": "Standard",
            "rating": 5,
            "reason": "AI summary failed."
        }

# ─── Daily Log Helpers ────────────────────────────────────────────────────────
def load_daily_log() -> pd.DataFrame:
    if os.path.exists(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE)
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def load_meal_log() -> pd.DataFrame:
    if os.path.exists(MEAL_LOG_FILE):
        try:
            return pd.read_csv(MEAL_LOG_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def delete_meal(dt_str: str):
    """Delete a meal from both logs based on its ISO datetime string."""
    if os.path.exists(MEAL_LOG_FILE):
        df = pd.read_csv(MEAL_LOG_FILE)
        df = df[df["datetime"] != dt_str]
        df.to_csv(MEAL_LOG_FILE, index=False)
        
    if os.path.exists(LOG_FILE):
        try:
            d_df = pd.read_csv(LOG_FILE)
            dt_date = dt_str[:10]
            dt_time = dt_str[11:16]
            d_df = d_df[~((d_df["date"] == dt_date) & (d_df["meal_time"] == dt_time))]
            d_df.to_csv(LOG_FILE, index=False)
        except Exception:
            pass

def get_today_totals() -> dict:
    df = load_daily_log()
    if df.empty or "date" not in df.columns:
        return {k: 0 for k in IDEAL_TARGETS}
    today_str = date.today().isoformat()
    today_df = df[df["date"] == today_str]
    totals = {k: 0 for k in IDEAL_TARGETS}
    if not today_df.empty:
        for k in totals:
            if k in today_df.columns:
                totals[k] = today_df[k].sum()
    return totals

@st.cache_data(ttl=1800, show_spinner=False)
def get_daily_insights(totals: dict, current_time: str) -> str:
    if sum(totals.values()) == 0:
        return "Systems initialized. No nutritional data logged today. Upload a meal to begin."
    
    client = get_gemini_client()
    prompt = f"""
    You are VibeMacros, an elite, highly-advanced AI nutritionist with a sleek, cyberpunk persona.
    Current time: {current_time}.
    User's intake today: {totals['calories']:.0f}kcal, Protein: {totals['protein']:.1f}g, Carbs: {totals['carbs']:.1f}g, Fat: {totals['fat']:.1f}g.
    Daily Goal: 2500kcal, 180g P, 300g C, 80g F.
    
    In precisely 2-3 short sentences:
    1. Briefly analyze their progress so far against their target.
    2. Give a sharp, actionable recommendation on what macros to prioritize for the rest of the day.
    Keep the tone lean, sharp, and encouraging.
    """
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception:
        return "Systems optimal. Log your next meal to continue tracking."

def save_uploaded_image(uploaded_file) -> str:
    """Save uploaded image to local storage as compressed JPEG and return path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"meal_{timestamp}.jpg"
    path = os.path.join(IMAGES_DIR, filename)
    
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    img = resize_image(img, max_dimension=1024)
    img.save(path, format="JPEG", quality=80, optimize=True)
    
    return path

def save_meal(items_data: list, image_path: str = None):
    today_str = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    timestamp = datetime.now().isoformat()
    
    # 1. Calc Totals
    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for item in items_data:
        for k in totals:
            totals[k] += item["macros"][k]

    # 2. Generate Summary if image exists
    summary = {
        "name": "Manual Log",
        "portion_desc": "-",
        "rating": 0,
        "reason": "No image provided"
    }
    if image_path:
        summary = generate_meal_summary(image_path, items_data, totals)

    # 3. Save to Meal Log
    new_meal = pd.DataFrame([{
        "datetime": timestamp,
        "image_path": image_path if image_path else "",
        "name": summary.get("name", "Unknown Meal"),
        "portion_desc": summary.get("portion_desc", "-"),
        "rating": summary.get("rating", 0),
        "reason": summary.get("reason", ""),
        "total_cals": totals["calories"],
        "total_protein": totals["protein"],
        "total_carbs": totals["carbs"],
        "total_fat": totals["fat"]
    }])
    
    if os.path.exists(MEAL_LOG_FILE):
        existing = pd.read_csv(MEAL_LOG_FILE)
        combined = pd.concat([existing, new_meal], ignore_index=True)
    else:
        combined = new_meal
    combined.to_csv(MEAL_LOG_FILE, index=False)

    # 4. Save Ingredients to Daily Log (Legacy but useful for granularity)
    rows = []
    for item in items_data:
        rows.append({
            "date": today_str,
            "meal_time": now_str,
            "item": item["name"],
            "weight_g": item["weight_g"],
            "calories": item["macros"]["calories"],
            "protein": item["macros"]["protein"],
            "carbs": item["macros"]["carbs"],
            "fat": item["macros"]["fat"],
        })
    new_df = pd.DataFrame(rows)
    if os.path.exists(LOG_FILE):
        existing = pd.read_csv(LOG_FILE)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(LOG_FILE, index=False)

# ─── Image Helpers ────────────────────────────────────────────────────────────
def resize_image(image: Image.Image, max_dimension: int = 1024) -> Image.Image:
    """Resize image to max dimension while maintaining aspect ratio."""
    # Fix orientation if needed (EXIF data)
    image = ImageOps.exif_transpose(image)
    
    width, height = image.size
    if width <= max_dimension and height <= max_dimension:
        return image
    
    if width > height:
        new_width = max_dimension
        new_height = int(height * (max_dimension / width))
    else:
        new_height = max_dimension
        new_width = int(width * (max_dimension / height))
    
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

# ─── Render Helpers ───────────────────────────────────────────────────────────
def render_macro_card(name, source, macros, color_class):
    st.markdown(f"""
    <div class="macro-card">
        <div class="food-name">{name}</div>
        <span class="food-source {color_class}">{source}</span>
        <div class="macro-grid">
            <div class="macro-item">
                <div class="macro-value">{macros['calories']:.0f}</div>
                <div class="macro-label">kcal</div>
            </div>
            <div class="macro-item">
                <div class="macro-value">{macros['protein']:.1f}g</div>
                <div class="macro-label">Protein</div>
            </div>
            <div class="macro-item">
                <div class="macro-value">{macros['carbs']:.1f}g</div>
                <div class="macro-label">Carbs</div>
            </div>
            <div class="macro-item">
                <div class="macro-value">{macros['fat']:.1f}g</div>
                <div class="macro-label">Fat</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_summary_card(total_macros):
    st.markdown(f"""
    <div class="summary-card">
        <div class="summary-title">Meal Total</div>
        <div class="summary-calories">{total_macros['calories']:.0f}</div>
        <div style="color: var(--text-secondary); font-size: 0.85rem; margin-top: -0.3rem;">calories</div>
        <div class="summary-macros">
            <div class="summary-macro-item">
                <div class="summary-macro-value">{total_macros['protein']:.1f}g</div>
                <div class="summary-macro-label">Protein</div>
            </div>
            <div class="summary-macro-item">
                <div class="summary-macro-value">{total_macros['carbs']:.1f}g</div>
                <div class="summary-macro-label">Carbs</div>
            </div>
            <div class="summary-macro-item">
                <div class="summary-macro-value">{total_macros['fat']:.1f}g</div>
                <div class="summary-macro-label">Fat</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def get_progress_bar_html(label, current, goal, unit="g", small=False):
    pct = (current / goal * 100) if goal > 0 else 0
    display_pct = min(pct, 100)
    
    color_class = "fill-green"
    if pct > 100: color_class = "fill-red"
    elif pct < 20: color_class = "fill-blue"

    height = "6px" if small else "12px"
    font_size = "0.75rem" if small else "0.85rem"
    padding = "0.3rem 0" if small else "0.8rem 1rem"
    margin = "0" if small else "0.5rem 0"
    
    html_str = f"""
    <div class="daily-progress-wrap" style="padding: {padding}; margin: {margin};">
        <div class="progress-header">
            <span class="progress-label" style="font-size: {font_size}; white-space: nowrap;">{label}</span>
            <span class="progress-value" style="font-size: {font_size};">{current:.0f}/{goal}{unit}</span>
        </div>
        <div class="progress-bar-bg" style="height: {height}; background: rgba(255,255,255,0.1);">
            <div class="progress-bar-fill {color_class}" style="width: {display_pct:.1f}%"></div>
        </div>
    </div>
    """
    return re.sub(r"^[ \t]+", "", html_str, flags=re.MULTILINE)

def render_progress_bar(label, current, goal, unit="g", small=False):
    html = get_progress_bar_html(label, current, goal, unit, small)
    st.markdown(html, unsafe_allow_html=True)

def render_history_item(row):
    """Render a single history item with consolidated meal info."""
    
    # Generate bar HTMLs
    cal_bar = get_progress_bar_html("Cal", row['total_cals'], 800, "kcal", small=True)
    prot_bar = get_progress_bar_html("Prot", row['total_protein'], 40, "g", small=True)
    carb_bar = get_progress_bar_html("Carb", row['total_carbs'], 80, "g", small=True)
    fat_bar = get_progress_bar_html("Fat", row['total_fat'], 25, "g", small=True)

    with st.container():
        html_str = f"""
        <div class="history-card">
            <div style="display: flex; gap: 1rem; align-items: start;">
                 <div style="flex: 1;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <div style="font-size: 1.1rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">{row['name']}</div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">{row['portion_desc']} • {str(row['datetime'])[:16].replace('T', ' ')}</div>
                        </div>
                        <div style="text-align: right;">
                             <div style="background: rgba(102, 126, 234, 0.1); color: var(--accent-blue); padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 0.9rem; border: 1px solid rgba(0,243,255,0.2);">
                                {row['rating']}/10
                             </div>
                        </div>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-muted); font-style: italic; margin-bottom: 0.8rem;">
                        "{row['reason']}"
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.8rem; margin-top: 0.5rem;">
                        {cal_bar}
                        {prot_bar}
                        {carb_bar}
                        {fat_bar}
                    </div>
                </div>
            </div>
        </div>
        """
        clean_html = re.sub(r"^[ \t]+", "", html_str, flags=re.MULTILINE)
        st.markdown(clean_html, unsafe_allow_html=True)
        
        # Action row (Expander + Delete) stacked nicely
        col_exp, col_del = st.columns([4, 1])
        with col_exp:
            if row['image_path'] and os.path.exists(row['image_path']):
                 with st.expander("View Meal Photo"):
                    st.image(row['image_path'], use_container_width=True)
        with col_del:
            if st.button("🗑️ Delete", key=f"del_{row['datetime']}", use_container_width=True):
                delete_meal(row['datetime'])
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    # ── Header ────────────────────────────────────
    st.markdown("""
    <div class="app-header">
        <h1>VibeMacros</h1>
        <p>Forensic Nutrition Analysis AI</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Daily Progress (Nutrient Specific) ────────
    totals = get_today_totals()
    with st.expander("Today's Progress", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            render_progress_bar("Calories", totals['calories'], IDEAL_TARGETS['calories'], "kcal")
            render_progress_bar("Protein", totals['protein'], IDEAL_TARGETS['protein'], "g")
        with col2:
            render_progress_bar("Carbs", totals['carbs'], IDEAL_TARGETS['carbs'], "g")
            render_progress_bar("Fat", totals['fat'], IDEAL_TARGETS['fat'], "g")

    # ── History Toggle ────────────────────────────
    if st.toggle("Show Past Meals", key="history_toggle"):
        st.markdown("#### Meal History")
        
        # Prefer Meal Log (New Smart History)
        mdf = load_meal_log()
        if not mdf.empty:
            for _, row in mdf.iloc[::-1].iterrows():
                render_history_item(row)
        else:
            # Fallback to Legacy Daily Log if Meal Log empty
            st.info("No smart meal logs yet. Showing raw entries...")
            df = load_daily_log()
            if not df.empty:
                st.dataframe(df.sort_index(ascending=False), use_container_width=True)
            else:
                 st.info("No history found.")
        
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── AI Insights ───────────────────────────────
    now_str = datetime.now().strftime("%I:%M %p")
    insights = get_daily_insights(totals, now_str)
    st.markdown(f"""
    <div style="background: rgba(0, 243, 255, 0.05); border-left: 4px solid var(--accent-blue); padding: 1.2rem; margin-bottom: 2rem; border-radius: 4px; border-right: 1px solid rgba(0,243,255,0.1); border-top: 1px solid rgba(0,243,255,0.1); border-bottom: 1px solid rgba(0,243,255,0.1);">
        <div style="color: var(--accent-blue); font-weight: 700; font-size: 0.85rem; margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 1.5px;">System Analysis • {now_str}</div>
        <div style="color: var(--text-primary); font-size: 1rem; line-height: 1.5;">{insights}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Upload Section ────────────────────────────
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    st.markdown("#### Log a Meal")

    col1, col2 = st.columns(2)
    with col1:
        img1 = st.file_uploader(
            "Top-Down View (Required)",
            type=["jpg", "jpeg", "png", "webp"],
            key="img_top",
        )
    with col2:
        img2 = st.file_uploader(
            "Side View (Optional)",
            type=["jpg", "jpeg", "png", "webp"],
            key="img_side",
        )

    # Show previews
    if img1 or img2:
        preview_cols = st.columns(2)
        if img1:
            with preview_cols[0]:
                st.image(Image.open(img1), caption="Top-Down", width=300)
        if img2:
            with preview_cols[1]:
                st.image(Image.open(img2), caption="Side View", width=300)

    # ── Analyze Button ────────────────────────────
    if img1:
        analyze_clicked = st.button("Analyze Food", use_container_width=True)
    else:
        analyze_clicked = False
        st.info("Upload a top-down photo to begin forensic analysis.")

    # ── Process Analysis ──────────────────────────
    if analyze_clicked and img1:
        with st.spinner("Analyzing surface oils & volumetric data..."):
            pil_images = []
            
            # Resize Main Image
            i1 = Image.open(img1)
            i1_resized = resize_image(i1)
            pil_images.append(i1_resized)
            
            if img2:
                i2 = Image.open(img2)
                i2_resized = resize_image(i2)
                pil_images.append(i2_resized)

            detected = analyze_food_images(pil_images)

        if not detected:
            st.warning("Could not detect any food items.")
            return

        db = load_food_db()
        items_data = []

        # 1. Identify items needing USDA lookup
        usda_candidates = []
        final_results = {}

        for i, item in enumerate(detected):
            name = item.get("name", "Unknown")
            matched, score = fuzzy_match_db(name, db)
            
            if matched:
                final_results[i] = {
                    "source": "Local DB",
                    "macro_entry": matched
                }
            else:
                usda_candidates.append((i, name))
        
        # 2. Parallel Fetch for USDA
        if usda_candidates:
             with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_idx = {
                    executor.submit(fetch_usda_macros, name): i 
                    for i, name in usda_candidates
                }
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        usda_macros = future.result()
                        if usda_macros:
                            final_results[idx] = {
                                "source": "USDA API",
                                "macro_entry": usda_macros
                            }
                        else:
                            final_results[idx] = {
                                "source": "AI Estimate",
                                "macro_entry": {
                                    "calories_per_100g": 150, "protein_per_100g": 8.0, 
                                    "carbs_per_100g": 20.0, "fat_per_100g": 5.0
                                }
                            }
                    except Exception:
                        final_results[idx] = {
                                "source": "AI Estimate (Err)",
                                "macro_entry": {
                                    "calories_per_100g": 150, "protein_per_100g": 8.0, 
                                    "carbs_per_100g": 20.0, "fat_per_100g": 5.0
                                }
                            }

        # 3. Assemble Final List in Order
        for i, item in enumerate(detected):
            res = final_results.get(i)
            items_data.append({
                "name": item.get("name", "Unknown"),
                "ai_weight_g": item.get("estimated_weight_g", 100),
                "source": res["source"],
                "macro_entry": res["macro_entry"],
            })

        st.session_state["detected_items"] = items_data

    # ── Slider UI (Trust System) ──────────────────
    if "detected_items" in st.session_state and st.session_state["detected_items"]:
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
        st.markdown("#### Adjust Portions")
        
        items = st.session_state["detected_items"]
        total_meal = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
        final_items = []

        for i, item in enumerate(items):
            # Unit Toggle per item
            col_slide, col_unit = st.columns([3, 2]) # Increased column width for radio
            with col_unit:
                unit = st.radio(
                    "Unit", 
                    options=["grams", "handful", "cup", "spoon", "ml"], 
                    key=f"unit_{i}", 
                    label_visibility="collapsed",
                    horizontal=True
                )
            
            factor = UNIT_FACTORS.get(unit, 1)
            # Convert initial AI weight (g) to unit value for slider
            initial_val = int(item["ai_weight_g"] / factor)
            
            with col_slide:
                slider_val = st.slider(
                    f"{item['name']}",
                    min_value=0,
                    max_value=int(1000/factor) if factor < 100 else 10, # dynamic max
                    value=initial_val,
                    step=1 if factor > 1 else 5,
                    key=f"slider_{i}"
                )
            
            # Convert back to grams for calc
            weight_in_g = slider_val * factor
            
            macros = calculate_macros(item["macro_entry"], weight_in_g)
            
            # Render card
            source_class = {
                "Local DB": "source-local",
                "USDA API": "source-usda",
                "AI Estimate": "source-ai",
            }.get(item["source"], "source-ai")

            render_macro_card(f"{item['name']} ({slider_val} {unit})", item["source"], macros, source_class)

            fork = total_meal
            for k in total_meal:
                total_meal[k] += macros[k]

            final_items.append({
                "name": item["name"],
                "weight_g": weight_in_g,
                "macros": macros,
            })

        # ── Total Summary ─────────────────────────
        render_summary_card(total_meal)

        # ── Save Button ───────────────────────────
        if st.button("Save Meal", use_container_width=True, key="save_meal"):
            saved_path = None
            if img1:
                try:
                    img1.seek(0)
                    saved_path = save_uploaded_image(img1)
                except Exception as e:
                    st.error(f"Image save failed: {e}")
            
            with st.spinner("Generating Smart Meal Summary & Saving..."):
                 save_meal(final_items, saved_path)
            
            st.session_state["detected_items"] = []
            st.success("Meal logged with Smart Summary!")
            st.rerun()

if __name__ == "__main__":
    main()
