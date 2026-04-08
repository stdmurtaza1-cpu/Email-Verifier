from fastapi import APIRouter, Depends, Request, HTTPException
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
    "starter": {"name": "Starter Plan", "price": 499, "credits": 50000},
    "pro": {"name": "Pro Plan", "price": 1499, "credits": 100000},
    "ultimate": {"name": "Ultimate Plan", "price": 4299, "credits": 500000},
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
