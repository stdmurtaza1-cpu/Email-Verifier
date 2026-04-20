import os
import re

# 1. Update requirements.txt
req_path = "d:/Quantx/Email Verifier/requirements.txt"
with open(req_path, "r", encoding="utf-8") as f:
    if "stripe" not in f.read():
        with open(req_path, "a", encoding="utf-8") as fw:
            fw.write("\nstripe")

# 2. Add vars to .env and .env.example
env_str = """
STRIPE_SECRET_KEY=sk_test_YOUR_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET
FRONTEND_URL=https://yourdomain.com
"""
for path in [".env", ".env.example"]:
    p = f"d:/Quantx/Email Verifier/{path}"
    mode = "a" if os.path.exists(p) else "w"
    with open(p, mode, encoding="utf-8") as f:
        f.write(env_str)

# 3. Create routes/billing.py
billing_code = """from fastapi import APIRouter, Depends, Request, HTTPException
import stripe
import os
from sqlalchemy.orm import Session
from database import get_db, User, Subscription
from middleware.auth import get_current_user

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
ENDPOINT_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")

PACKS = {
    "basic": {"name": "Basic Pack", "price": 999, "credits": 50000},
    "pro": {"name": "Pro Pack", "price": 1499, "credits": 150000},
    "growth": {"name": "Growth Pack", "price": 3999, "credits": 500000},
    "enterprise": {"name": "Enterprise Pack", "price": 6999, "credits": 1000000},
}

@router.post("/create-checkout")
async def create_checkout(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    pack_id = data.get("pack")
    
    if pack_id not in PACKS:
        raise HTTPException(status_code=400, detail="Invalid pack selected")
        
    pack = PACKS[pack_id]
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': pack['name'],
                        'description': f"{pack['credits']} Verification Credits"
                    },
                    'unit_amount': pack['price'],
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=FRONTEND_URL + '/success.html',
            cancel_url=FRONTEND_URL + '/',
            metadata={
                "user_id": str(current_user.id),
                "credits_to_add": str(pack['credits']),
                "pack_name": pack['name']
            }
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, ENDPOINT_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        user_id = session.get('metadata', {}).get('user_id')
        credits_to_add = int(session.get('metadata', {}).get('credits_to_add', 0))
        pack_name = session.get('metadata', {}).get('pack_name', 'Unknown')
        
        if user_id and credits_to_add > 0:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                user.credits += credits_to_add
                user.plan = pack_name
                
                # Insert row into subscriptions table for history
                new_sub = Subscription(
                    user_id=user.id,
                    plan=pack_name,
                    credits_limit=credits_to_add
                )
                db.add(new_sub)
                db.commit()
    
    # Return 200 immediately to Stripe
    return {"status": "success"}
"""
with open("d:/Quantx/Email Verifier/routes/billing.py", "w", encoding="utf-8") as f:
    f.write(billing_code)

# 4. Integrate into main.py
main_path = "d:/Quantx/Email Verifier/main.py"
with open(main_path, "r", encoding="utf-8") as f:
    main_content = f.read()

if "billing_router" not in main_content:
    main_content = main_content.replace(
        "from routes.partner import router as partner_router",
        "from routes.partner import router as partner_router\nfrom routes.billing import router as billing_router"
    )
    main_content = main_content.replace(
        "app.include_router(partner_router, prefix=\"/api/partner\")",
        "app.include_router(partner_router, prefix=\"/api/partner\")\napp.include_router(billing_router, prefix=\"/billing\")"
    )
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_content)

# 5. Create static/success.html
success_code = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Successful - Veridrax</title>
    <link rel="stylesheet" href="styles.css">
    <style>
        body { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0b0c10; color: white; text-align: center; }
        .success-box { background: rgba(30,30,40,0.8); padding: 3rem; border-radius: 12px; border: 1px solid #00f260; max-width: 500px; }
        h1 { color: #00f260; margin-bottom: 1rem; }
    </style>
</head>
<body>
    <div class="success-box glass">
        <h1 style="font-size:3rem;">✅</h1>
        <h1>Payment Successful!</h1>
        <p class="text-muted mt-2">Your credits have been added to your account instantly.</p>
        <a href="/" class="btn btn-primary mt-4" style="text-decoration:none; display:inline-block;">Return to Dashboard</a>
    </div>
</body>
</html>"""
with open("d:/Quantx/Email Verifier/static/success.html", "w", encoding="utf-8") as f:
    f.write(success_code)

# 6. Update static/index.html to include pack cards
html_path = "d:/Quantx/Email Verifier/static/index.html"
with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()

target_html = """                            <button class="btn btn-outline w-100 mt-5" onclick="showPage('pricing')">Upgrade Matrix</button>"""
packs_html = """                            <button class="btn btn-outline w-100 mt-5" onclick="showPage('pricing')">Upgrade Matrix</button>
                        </div>
                        
                        <!-- NEW BILLING PACKS UI -->
                        <h2 class="mt-5">Buy Credits</h2>
                        <div class="grid-4 mt-4">
                            <div class="glass p-3 rounded text-center">
                                <h3>Basic</h3><p class="text-muted">50,000 Credits</p>
                                <h2 class="mt-2">$9.99</h2>
                                <button class="btn btn-primary w-100 mt-3" onclick="buyPack('basic')">Buy Now</button>
                            </div>
                            <div class="glass p-3 rounded text-center" style="border-color:var(--primary);">
                                <h3>Pro</h3><p class="text-muted">150,000 Credits</p>
                                <h2 class="mt-2">$14.99</h2>
                                <button class="btn btn-primary w-100 mt-3" onclick="buyPack('pro')">Buy Now</button>
                            </div>
                            <div class="glass p-3 rounded text-center">
                                <h3>Growth</h3><p class="text-muted">500,000 Credits</p>
                                <h2 class="mt-2">$39.99</h2>
                                <button class="btn btn-primary w-100 mt-3" onclick="buyPack('growth')">Buy Now</button>
                            </div>
                            <div class="glass p-3 rounded text-center">
                                <h3>Enterprise</h3><p class="text-muted">1M Credits</p>
                                <h2 class="mt-2">$69.99</h2>
                                <button class="btn btn-primary w-100 mt-3" onclick="buyPack('enterprise')">Buy Now</button>
                            </div>"""
if "<!-- NEW BILLING PACKS UI -->" not in html_content:
    html_content = html_content.replace(target_html, packs_html)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

# 7. Add Buy function to JS
js_path = "d:/Quantx/Email Verifier/static/app.js"
with open(js_path, "r", encoding="utf-8") as f:
    js_content = f.read()

buy_func = """
window.buyPack = async function(packName) {
    if(!authToken) return alert("Please login first");
    try {
        const res = await fetch('/billing/create-checkout', {
            method: 'POST',
            headers: {'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json'},
            body: JSON.stringify({pack: packName})
        });
        const data = await res.json();
        if(data.checkout_url) {
            window.location.href = data.checkout_url;
        } else {
            alert("Error: " + data.detail);
        }
    } catch(e) {
        alert("Payment Error: " + e.message);
    }
};
"""
if "window.buyPack =" not in js_content:
    with open(js_path, "a", encoding="utf-8") as f:
        f.write(buy_func)

print("Billing integration deployed!")
