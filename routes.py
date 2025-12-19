from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime, timedelta
from .forms import LoginForm, MFAForm
import random
import string
import pyotp
import qrcode
import base64
from io import BytesIO
from .models import User, db

main = Blueprint("main", __name__)

def _ip():
    return request.remote_addr or "unknown"

def _log_info(msg):
    from flask import current_app
    current_app.logger.info(f"{msg} ip={_ip()} time={datetime.utcnow().isoformat()}")

def _log_warn(msg):
    from flask import current_app
    current_app.logger.warning(f"{msg} ip={_ip()} time={datetime.utcnow().isoformat()}")

@main.route("/", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    now = datetime.utcnow()

    captcha_code = session.get("captcha_code")
    captcha_needed = captcha_code is not None

    if request.method == "POST" and form.validate_on_submit():

        ip_attempts = session.get("ip_attempts", [])
        now_ts = datetime.utcnow().timestamp()
        ip_attempts = [t for t in ip_attempts if now_ts - t < 60]
        ip_attempts.append(now_ts)
        session["ip_attempts"] = ip_attempts

        if len(ip_attempts) > 7:
            flash("Too many login attempts. Please wait a moment.", "error")
            _log_warn("RATE_LIMIT_EXCEEDED")
            return render_template("login.html", form=form,
                                   captcha_needed=captcha_needed, captcha_code=captcha_code)

        user = User.query.filter_by(username=form.username.data).first()

        if user and user.locked_until and now < user.locked_until:
            flash("Account locked. Try again later.", "error")
            _log_warn(f"LOCKED_ATTEMPT username={user.username}")
            return render_template("login.html", form=form,
                                   captcha_needed=captcha_needed, captcha_code=captcha_code)

        if not user or not user.check_password(form.password.data):
            if user:
                user.failed_attempts += 1

                if user.failed_attempts >= 3:
                    if not captcha_code:
                        captcha_code = ''.join(random.choices(string.ascii_uppercase, k=5))
                        session["captcha_code"] = captcha_code
                        captcha_needed = True
                        _log_info(f"CAPTCHA_TRIGGER username={user.username}")

                if user.failed_attempts >= 5:
                    user.locked_until = now + timedelta(minutes=5)
                    _log_warn(f"ACCOUNT_LOCKED username={user.username}")

                db.session.commit()

            flash("Invalid username or password", "error")
            _log_warn(f"LOGIN_FAIL username={form.username.data}")
            return render_template("login.html", form=form,
                                   captcha_needed=captcha_needed,
                                   captcha_code=captcha_code)

        if captcha_code:
            if not form.captcha.data or form.captcha.data.strip().upper() != captcha_code:
                captcha_code = ''.join(random.choices(string.ascii_uppercase, k=5))
                session["captcha_code"] = captcha_code
                captcha_needed = True
                flash("Incorrect CAPTCHA. New code generated.", "error")
                _log_warn(f"CAPTCHA_FAIL username={user.username}")
                return render_template("login.html", form=form,
                                       captcha_needed=True,
                                       captcha_code=captcha_code)

        user.failed_attempts = 0
        db.session.commit()
        session.pop("captcha_code", None)

        _log_info(f"PASSWORD_OK username={user.username}")

        session.clear()
        session["mfa_user_id"] = user.id

        if not user.mfa_enabled or not user.totp_secret:
            user.totp_secret = pyotp.random_base32()
            db.session.commit()
            return redirect(url_for("main.mfa_setup"))

        return redirect(url_for("main.mfa_verify"))

    return render_template("login.html", form=form,
                           captcha_needed=captcha_needed,
                           captcha_code=captcha_code)


@main.route("/mfa/setup", methods=["GET", "POST"])
def mfa_setup():
    uid = session.get("mfa_user_id")
    if not uid:
        return redirect(url_for("main.login"))

    user = User.query.get(uid)
    form = MFAForm()

    totp = pyotp.TOTP(user.totp_secret)
    uri = totp.provisioning_uri(user.username, issuer_name="Task2")

    qr = qrcode.QRCode(box_size=7, border=4)
    qr.add_data(uri)
    qr.make()
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode()

    if form.validate_on_submit():
        if totp.verify(form.code.data.strip()):
            user.mfa_enabled = True
            db.session.commit()
            login_user(user)
            session.pop("mfa_user_id", None)
            flash("MFA enabled", "success")
            _log_info(f"MFA_SETUP_SUCCESS username={user.username}")
            return redirect(url_for("main.dashboard"))

        flash("Invalid code", "error")
        _log_warn(f"MFA_SETUP_INVALID_CODE username={user.username}")

    return render_template("mfa_setup.html", form=form, secret=user.totp_secret, qr_base64=qr_base64)

@main.route("/mfa/verify", methods=["GET", "POST"])
def mfa_verify():
    uid = session.get("mfa_user_id")
    if not uid:
        return redirect(url_for("main.login"))

    user = User.query.get(uid)
    form = MFAForm()

    if form.validate_on_submit():
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(form.code.data.strip()):
            login_user(user)
            session.pop("mfa_user_id", None)
            session.pop("captcha_code", None)
            flash("Login successful", "success")
            _log_info(f"LOGIN_SUCCESS username={user.username}")
            return redirect(url_for("main.dashboard"))

        flash("Invalid code", "error")
        _log_warn(f"TOTP_INVALID username={user.username}")

    return render_template("mfa_verify.html", form=form)

@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@main.route("/logout")
@login_required
def logout():
    uname = current_user.username
    logout_user()
    session.clear()
    flash("Logged out", "success")
    _log_info(f"LOGOUT username={uname}")
    return redirect(url_for("main.login"))
