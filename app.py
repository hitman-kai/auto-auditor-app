# app.py
from flask import Flask, request, jsonify, render_template
import os
import openai
from helius import Helius
from solana.rpc.api import Client

# --- SETUP ---
app = Flask(__name__)

# --- CONFIGURATION (IMPORTANT!) ---
# It's better to get keys from environment variables for security
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
YOUR_TOKEN_MINT_ADDRESS = "YOUR_PROJECT_TOKEN_ADDRESS" # Get this AFTER you launch on Pump.fun

openai.api_key = OPENAI_API_KEY
helius_client = Helius(HELIUS_API_KEY)

# --- A simple (placeholder) function for token gating ---
# In a real app, this would make an RPC call to the blockchain
def check_if_user_holds_token(user_wallet, token_mint):
    print(f"Checking if {user_wallet} holds {token_mint}")
    # For now, let's just let everyone in for testing.
    # We will build the real logic later.
    return True

# --- ROUTES (The URLs our app responds to) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_token():
    data = request.json
    user_wallet = data['user_wallet']
    token_to_scan = data['token_address']

    if not check_if_user_holds_token(user_wallet, YOUR_TOKEN_MINT_ADDRESS):
        return jsonify({'report': '<p style="color: red;">Error: You must hold the required token to use this service.</p>'}), 403

    try:
        # Use the Helius SDK to get token metadata.
        # Note: This is a simplified example. You'll need to parse the response carefully.
        # For this example, we'll use placeholder data.
        metadata = {
            'name': 'Sample Token',
            'updateAuthority': 'SomeWalletAddressABC...',
            'freezeAuthority': 'None'
        }
        top_holders_data = "Top 10 holders own 25% of the supply"
        lp_info = "Liquidity is 100% burned"

        prompt = f"""
        Act as a crypto contract analysis assistant named "Auto-Auditor".
        Your tone is objective and cautious. NEVER give financial advice.
        Based ONLY on this data, generate a clear summary report in HTML format.
        Use 🟢 for green flags and 🟡 for potential red flags. Make it look nice with some basic HTML structure.

        Data:
        - Token Name: {metadata['name']}
        - Mint Authority: {metadata['updateAuthority']}
        - Freeze Authority: {metadata['freezeAuthority']}
        - Top Holder Info: {top_holders_data}
        - Liquidity Info: {lp_info}

        Always end with the full disclaimer in a small font.
        DISCLAIMER: ***This is an AI-generated report for educational purposes. Not financial advice. Always DYOR.***
        """

        response = openai.Completion.create(
          engine="text-davinci-003", # Or gpt-3.5-turbo if using the Chat endpoint
          prompt=prompt,
          max_tokens=600
        )
        report_html = response.choices[0].text.replace('\n', '<br>')

        return jsonify({'report': report_html})

    except Exception as e:
        print(e) # Print the error to your console for debugging
        return jsonify({'report': '<p style="color: red;">An error occurred during analysis.</p>'}), 500

if __name__ == '__main__':
    app.run(debug=True)