import re
import os

# 1. ADD ENDPOINTS TO routes/auth.py
auth_path = "d:/Quantx/Email Verifier/routes/auth.py"
with open(auth_path, "r", encoding="utf-8") as f:
    auth_code = f.read()

new_routes = """
class ForgotPasswordDTO(BaseModel):
    email: str

@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordDTO, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        import secrets
        import os
        from cache import cache_set
        token = secrets.token_urlsafe(32)
        await cache_set(f"reset:{token}", user.id, ttl=900)
        
        FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")
        reset_link = f"{FRONTEND_URL}/reset-password.html?token={token}"
        
        html_content = f\"\"\"
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px; text-align: center;">
            <h2 style="color: #333;">Reset Your Password</h2>
            <p style="color: #555; font-size: 16px;">We received a request to reset your password. Click the button below to set a new password.</p>
            <div style="margin: 30px 0;">
                <a href="{reset_link}" style="background-color: #4A90E2; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Reset Password</a>
            </div>
            <p style="color: #888; font-size: 12px;">This link expires in 15 minutes.</p>
            <p style="color: #888; font-size: 12px; margin-top: 20px;">If you didn't request this, you can safely ignore this email.</p>
        </div>
        \"\"\"
        
        if SENDGRID_API_KEY:
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail
                message = Mail(
                    from_email=FROM_EMAIL,
                    to_emails=user.email,
                    subject='Password Reset - Veridrax',
                    html_content=html_content)
                sg = SendGridAPIClient(SENDGRID_API_KEY)
                sg.send(message)
            except Exception as e:
                print(f"Failed to send reset email: {e}")
        else:
            print(f"DEV MODE - Reset link for {user.email}: {reset_link}")

    return {"message": "If this email is registered, a reset link has been sent."}

class ResetPasswordDTO(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordDTO, db: Session = Depends(get_db)):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        
    from cache import cache_get, cache_delete
    user_id = await cache_get(f"reset:{data.token}")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
        
    user.password_hash = get_password_hash(data.new_password)
    db.commit()
    
    await cache_delete(f"reset:{data.token}")
    
    return {"message": "Password updated. Please login with your new password."}
"""

if "@router.post(\"/forgot-password\")" not in auth_code:
    with open(auth_path, "a", encoding="utf-8") as f:
        f.write(new_routes)

# 2. UPDATE index.html FOR MODAL AND LINK
index_path = "d:/Quantx/Email Verifier/static/index.html"
with open(index_path, "r", encoding="utf-8") as f:
    index_code = f.read()

target_login_p = """<p class="text-center mt-3 text-muted" style="font-size: 0.9rem;">
                    No account? <a href="#" id="switch-to-signup" style="color: var(--primary);">Create one safely.</a>
                </p>"""
replace_login_p = """<p class="text-center mt-3 text-muted" style="font-size: 0.9rem;">
                    No account? <a href="#" id="switch-to-signup" style="color: var(--primary);">Create one safely.</a>
                </p>
                <p class="text-center mt-2 text-muted" style="font-size: 0.9rem;">
                    Forgot password? <a href="#" onclick="showForgotModal()" style="color: var(--warning);">Reset it here.</a>
                </p>"""

if "Forgot password?" not in index_code:
    index_code = index_code.replace(target_login_p, replace_login_p)


target_modal = """<!-- SIGNUP MODAL -->"""
replace_modal = """<!-- FORGOT MODAL -->
        <div id="forgot-modal" class="modal-card glass hidden">
            <div class="flex flex-between align-center mb-4">
                <h2>Reset Password</h2>
                <button class="close-modal text-muted" onclick="document.getElementById('forgot-modal').classList.add('hidden')">✖</button>
            </div>
            <form id="forgot-form" class="flex flex-col gap-3">
                <input type="email" id="forgot-email" class="input-modern" placeholder="Account Email" required>
                <button type="submit" class="btn btn-warning mt-2" style="background: var(--warning); color: black; border: none; font-weight:bold;">
                    <span id="forgot-btn-txt">Send Reset Link</span>
                    <div class="loader hidden" id="forgot-loader" style="border-top-color:#000;"></div>
                </button>
                <p id="forgot-msg" class="hidden mt-2" style="font-size: 0.85rem; text-align: center; color: var(--success); background:rgba(0,255,0,0.1); padding:10px; border-radius:5px;"></p>
                <p class="text-center mt-3 text-muted" style="font-size: 0.9rem;">
                    Remembered? <a href="#" onclick="showLoginModal()" style="color: var(--primary);">Go back to login.</a>
                </p>
            </form>
        </div>

        <!-- SIGNUP MODAL -->"""

if "FORGOT MODAL" not in index_code:
    index_code = index_code.replace(target_modal, replace_modal)

with open(index_path, "w", encoding="utf-8") as f:
    f.write(index_code)

# 3. UPDATE app.js 
appjs_path = "d:/Quantx/Email Verifier/static/app.js"
with open(appjs_path, "r", encoding="utf-8") as f:
    appjs_code = f.read()

target_show_login = "DOM.signupModal.classList.add('hidden');"
replace_show_login = "DOM.signupModal.classList.add('hidden');\n    const fm = document.getElementById('forgot-modal');\n    if(fm) fm.classList.add('hidden');"
if "forgot-modal" not in appjs_code:
    appjs_code = appjs_code.replace(target_show_login, replace_show_login)

target_show_signup = "DOM.loginModal.classList.add('hidden');"
replace_show_signup = "DOM.loginModal.classList.add('hidden');\n    const fm2 = document.getElementById('forgot-modal');\n    if(fm2) fm2.classList.add('hidden');"
if "fm2.classList.add('hidden')" not in appjs_code:
    appjs_code = appjs_code.replace(target_show_signup, replace_show_signup)

forgot_logic = """
window.showForgotModal = function() {
    DOM.overlay.classList.remove('hidden');
    DOM.loginModal.classList.add('hidden');
    DOM.signupModal.classList.add('hidden');
    const fm = document.getElementById('forgot-modal');
    if (fm) fm.classList.remove('hidden');
}

const forgotForm = document.getElementById('forgot-form');
if(forgotForm) {
    forgotForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btnText = document.getElementById('forgot-btn-txt');
        const loader = document.getElementById('forgot-loader');
        const msgObj = document.getElementById('forgot-msg');
        
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
        msgObj.classList.add('hidden');

        try {
            const res = await fetch('/api/forgot-password', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    email: document.getElementById('forgot-email').value
                })
            });

            const data = await res.json();
            if(!res.ok) throw new Error(data.detail || "Request Failed.");

            msgObj.textContent = data.message;
            msgObj.style.color = "var(--success)";
            msgObj.style.backgroundColor = "rgba(0,255,0,0.1)";
            msgObj.classList.remove('hidden');
        } catch(err) {
            msgObj.textContent = err.message;
            msgObj.style.color = "var(--danger)";
            msgObj.style.backgroundColor = "rgba(255,0,0,0.1)";
            msgObj.classList.remove('hidden');
        } finally {
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
        }
    });
}
"""

if "window.showForgotModal" not in appjs_code:
    with open(appjs_path, "a", encoding="utf-8") as f:
        f.write("\n" + forgot_logic)
else:
    with open(appjs_path, "w", encoding="utf-8") as f:
        f.write(appjs_code)

# 4. CREATE reset-password.html
reset_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Set New Password</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body style="display:flex; justify-content:center; align-items:center; height:100vh; background:#0b0c10; color:white;">
    <div class="glass" style="padding: 2.5rem; border-radius: 12px; width: 100%; max-width: 400px; text-align:center;">
        <h2 style="color:var(--primary); margin-bottom: 1rem;">Set New Password</h2>
        <div id="error-msg" style="color: var(--danger); background:rgba(255,0,0,0.1); padding:10px; border-radius:5px; margin-bottom:1rem; display:none; font-size:0.9rem;"></div>
        <div id="success-msg" style="color: var(--success); background:rgba(0,255,0,0.1); padding:10px; border-radius:5px; margin-bottom:1rem; display:none; font-size:0.9rem;"></div>
        
        <form id="reset-form" style="display:flex; flex-direction:column; gap:1rem;">
            <input type="password" id="new-password" class="input-modern" placeholder="New Password (min 8 chars)" required minlength="8">
            <input type="password" id="confirm-password" class="input-modern" placeholder="Confirm Password" required minlength="8">
            <button type="submit" class="btn btn-primary" id="submit-btn" style="width:100%;">Update Password</button>
        </form>
    </div>

    <script>
        const params = new URLSearchParams(window.location.search);
        const token = params.get('token');
        const form = document.getElementById('reset-form');
        const err = document.getElementById('error-msg');
        const success = document.getElementById('success-msg');
        const btn = document.getElementById('submit-btn');

        if (!token) {
            err.textContent = "Invalid link. No secure token found.";
            err.style.display = 'block';
            form.style.display = 'none';
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            err.style.display = 'none';
            success.style.display = 'none';
            
            const pwd = document.getElementById('new-password').value;
            const pwd2 = document.getElementById('confirm-password').value;

            if(pwd !== pwd2) {
                err.textContent = "Passwords do not match!";
                err.style.display = 'block';
                return;
            }

            btn.disabled = true;
            btn.textContent = "Saving...";

            try {
                const res = await fetch('/api/reset-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ token: token, new_password: pwd })
                });

                const data = await res.json();
                if(!res.ok) throw new Error(data.detail || data.message || "Request Failed");

                success.textContent = data.message + " Redirecting...";
                success.style.display = 'block';
                form.style.display = 'none';

                setTimeout(() => {
                    window.location.href = '/?login=true';
                }, 3000);

            } catch (error) {
                err.textContent = error.message;
                err.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.textContent = "Update Password";
            }
        });
    </script>
</body>
</html>
"""
with open("d:/Quantx/Email Verifier/static/reset-password.html", "w", encoding="utf-8") as f:
    f.write(reset_html)

print("Forgot Password Flow Integrated!")
