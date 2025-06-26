# app.py

from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv
import os
import requests
from openai import OpenAI
import sqlite3
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import io

app = Flask(__name__, static_folder='static')

# --- API KEYS ---
load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")
MORALIS_API_KEY = os.environ.get("MORALIS_API_KEY")
BIRDEYE_API_KEY = os.environ.get("BIRDEYE_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Whitelist for testing wallet
WHITELISTED_WALLETS = ["HgLjKiQoWK4HU4dBo9y1mP6QNu4af5vT51fFc6LupaVt"]

# --- Database & Helper Functions (Unchanged) ---
def init_db():
    with sqlite3.connect('mooner.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS scans
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         wallet_address TEXT NOT NULL,
                         token_address TEXT NOT NULL,
                         initial_market_cap REAL NOT NULL,
                         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
init_db()

def fetch_ipfs_metadata(json_uri):
    try:
        response = requests.get(json_uri, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching IPFS metadata: {e}")
        return {}

def fetch_birdeye_price(token_address):
    try:
        url = f"https://public-api.birdeye.so/public/price?address={token_address}"
        headers = {"X-API-KEY": BIRDEYE_API_KEY}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("value", 0)
    except requests.exceptions.RequestException as e:
        print(f"Birdeye Error: {e}")
        return 0

def check_scan_limit(wallet_address):
    if wallet_address in WHITELISTED_WALLETS: return True
    with sqlite3.connect('mooner.db') as conn:
        twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
        count = conn.execute('SELECT COUNT(*) FROM scans WHERE wallet_address = ? AND timestamp > ?', (wallet_address, twenty_four_hours_ago)).fetchone()[0]
        return count < 2

def get_market_cap(token_address):
    try:
        helius_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        helius_payload = {"jsonrpc": "2.0", "id": "audit", "method": "getAsset", "params": {"id": token_address}}
        helius_res = requests.post(helius_url, json=helius_payload, timeout=10)
        helius_res.raise_for_status()
        helius_data = helius_res.json().get("result", {})
        if helius_data and helius_data.get("token_info", {}).get("supply") and helius_data.get("token_info", {}).get("price_info", {}).get("price_per_token"):
            supply = helius_data["token_info"]["supply"] / (10 ** helius_data["token_info"]["decimals"])
            price_per_token = helius_data["token_info"]["price_info"]["price_per_token"]
            return supply * price_per_token
    except: pass
    try:
        response = requests.get(f"https://api.helius.xyz/v0/tokens/{token_address}/price?api-key={HELIUS_API_KEY}")
        if response.status_code == 200: return response.json().get('price_info', {}).get('market_cap', 0)
    except: pass
    try:
        price = fetch_birdeye_price(token_address)
        if price: return price * 10**9
    except: pass
    return 0

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_token():
    # This is your original working analyze function that returns an HTML string
    data = request.json
    token_address = data.get("token_address", "").strip()
    user_wallet = data.get("user_wallet", "")
    try:
        if not check_scan_limit(user_wallet): return jsonify({'error': 'Scan limit reached'}), 429
        
        helius_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        helius_payload = {"jsonrpc": "2.0", "id": "audit", "method": "getAsset", "params": {"id": token_address}}
        helius_res = requests.post(helius_url, json=helius_payload, timeout=10)
        helius_res.raise_for_status()
        helius_data = helius_res.json().get("result", {})
        if not helius_data: raise ValueError("No Helius data")

        json_uri = helius_data.get("content", {}).get("json_uri")
        ipfs_metadata = fetch_ipfs_metadata(json_uri) if json_uri else {}
        fdv = "N/A"
        
        moralis_url = f"https://solana-gateway.moralis.io/token/mainnet/{token_address}/metadata"
        moralis_headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
        try:
            moralis_res = requests.get(moralis_url, headers=moralis_headers, timeout=10)
            moralis_res.raise_for_status()
            fdv_raw = moralis_res.json().get("fullyDilutedValue", 0)
            fdv = float(fdv_raw) if isinstance(fdv_raw, (int, float, str)) and str(fdv_raw).replace(".", "").isdigit() else 0
        except: pass
        
        if fdv == "N/A": fdv = get_market_cap(token_address)
        
        with sqlite3.connect('mooner.db') as conn: conn.execute('INSERT INTO scans (wallet_address, token_address, initial_market_cap) VALUES (?, ?, ?)',(user_wallet, token_address, fdv if fdv != "N/A" else 0)); conn.commit()
        
        content = helius_data.get("content", {}); metadata = content.get("metadata", {}) or ipfs_metadata
        links = content.get("links", {}) or ipfs_metadata.get("properties", {}).get("links", {})
        token_name = metadata.get("name", "N/A").strip('\x00'); symbol = metadata.get("symbol", "N/A").strip('\x00')
        website_url = links.get('website', 'N/A'); twitter_url = links.get('twitter', 'N/A')
        
        degen_score = 0
        if not helius_data.get('mutable', True): degen_score += 5
        if website_url != 'N/A' and website_url: degen_score += 3
        if twitter_url != 'N/A' and twitter_url: degen_score += 2
        
        report_data = {"Name": token_name, "Symbol": f"${symbol}", "Market Cap (FDV)": f"${fdv:,.2f}" if fdv != "N/A" else "N/A", "Website": f'<a href="{website_url}" target="_blank">Link</a>' if website_url != 'N/A' else "N/A", "Twitter": f'<a href="{twitter_url}" target="_blank">Link</a>' if twitter_url != 'N/A' else "N/A", "Contract Status": "Immutable / Renounced" if not helius_data.get('mutable', True) else "Mutable"}
        
        html_details = "<ul>"
        for k, v in report_data.items(): html_details += f"<li><strong>{k}:</strong> <span class='value'>{v}</span></li>"
        html_details += "</ul>"
        
        filled_emojis = "⬜  " * degen_score + "⬜  " * (10 - degen_score)
        
        structured_report_html = f"""<div class="report-container card"><h2>Token Report: {token_name} (${symbol})</h2>{html_details}<h3>Score: {filled_emojis}</h3><button id="refreshBtn">Refresh Audit</button>"""
        
        recommendation = "A true mystery"
        if fdv != "N/A":
            fdv_value = float(fdv) if isinstance(fdv, (int, float)) else float(str(fdv).replace(",", ""))
            if fdv_value < 10000: recommendation = "Run, You Fool!"
            else: recommendation = "Moon Lambo Time, Idiots!"

        prompt = f"""You are a witty Solana degen. ${symbol} scored {degen_score}/10 with an FDV recommendation of "{recommendation}". Write a funny, one-sentence HTML verdict with <h3>Final Verdict</h3>, no code blocks."""
        
        openai_response = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
        final_html = openai_response.choices[0].message.content.strip()
        
        full_report = structured_report_html + final_html + "</div>"
        
        return jsonify({"report": full_report})

    except Exception as e:
        return jsonify({"report": f"<div class='report-container card'><p style='color:red;'>Server error: {str(e)}</p></div>"}), 500

@app.route('/generate_ai_card', methods=['POST'])
def generate_ai_card():
    data = request.json
    token_name = data.get('name', 'N/A')
    symbol = data.get('symbol', '$???').replace('$', '')
    market_cap = data.get('fdv', 'N/A')
    degen_score = int(data.get('degen_score', 0))

    if degen_score <= 3:
        visual_prompt = "A sad, crying Pepe the Frog (Pepehands) looking at a downward crashing red crypto chart on his computer in a dark, messy room."
    elif degen_score <= 7:
        visual_prompt = "A Pepe the Frog in a hoodie, looking thoughtfully at a stable crypto chart on his computer."
    else:
        visual_prompt = "A very happy, rich Pepe the Frog wearing a tuxedo and pixelated 'Thug Life' sunglasses, with a green sports car on the moon."
    
    prompt_for_dalle = f"Create a high-quality, wide digital art piece in the style of a crypto meme. The main scene must be: '{visual_prompt}'. The image should be clean, vibrant, and have space for text to be added later. No text in the image."
    
    try:
        print("Generating base meme image with DALL-E...")
        image_response = openai_client.images.generate(model="dall-e-3", prompt=prompt_for_dalle, size="1792x1024", quality="standard", n=1)
        image_url = image_response.data[0].url

        print("Downloading generated image...")
        response = requests.get(image_url)
        response.raise_for_status()
        image_bytes = response.content

        print("Resizing and adding details to the image...")
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            draw = ImageDraw.Draw(img)

            try:
                main_font = ImageFont.truetype("PressStart2P-Regular.ttf", 55)
                details_font = ImageFont.truetype("PressStart2P-Regular.ttf", 40)
                watermark_font = ImageFont.truetype("PressStart2P-Regular.ttf", 25)
            except IOError:
                return jsonify({"error": "Font file not found on server."}), 500
            
            ticker_text = f"${symbol}"
            mc_text = f"MC: {market_cap}"
            watermark_text = "Scanned by Retarded Auditor"

            # Watermark at bottom right
            watermark_bbox = draw.textbbox((0, 0), watermark_text, font=watermark_font)
            watermark_width = watermark_bbox[2] - watermark_bbox[0]
            # --- THIS IS THE LINE THAT WAS MISSING ---
            watermark_height = watermark_bbox[3] - watermark_bbox[1]
            
            x_pos = img.width - watermark_width - 40
            y_pos = img.height - watermark_height - 30
            
            # Ticker at top left
            draw.text((42, 42), ticker_text, font=main_font, fill="black")
            draw.text((40, 40), ticker_text, font=main_font, fill="white")
            
            # Market Cap below Ticker
            draw.text((42, 102), mc_text, font=details_font, fill="black")
            draw.text((40, 100), mc_text, font=details_font, fill="white")
            
            # Watermark
            draw.text((x_pos + 2, y_pos + 2), watermark_text, font=watermark_font, fill="black")
            draw.text((x_pos, y_pos), watermark_text, font=watermark_font, fill="white")
            
            final_image_buffer = io.BytesIO()
            img.save(final_image_buffer, format="PNG")
            final_image_buffer.seek(0)

        print("Sending final image to user for download.")
        return send_file(
            final_image_buffer,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'{symbol}_degen_card.png'
        )
    except Exception as e:
        print(f"An error occurred in generate_ai_card: {e}")
        return jsonify({"error": "Failed to create and process the AI card."}), 500

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
