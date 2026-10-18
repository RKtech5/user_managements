from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import secrets
import smtplib
from email.message import EmailMessage

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_pymongo import PyMongo
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config

load_dotenv()
app = Flask(__name__)
app.config.from_object(Config)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

mongo = PyMongo(app, uri=app.config["MONGO_URI"])
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_AGE = 120
ROLES = ["Top", "Bottom", "Vers"]
PLACES = ["Yes", "No"]

def utcnow():
    return datetime.now(timezone.utc)

def ensure_indexes():
    """Create helpful indexes. MongoDB must be running when the app starts."""
    db = mongo.db
    db.accounts.create_index("email", unique=True)
    db.user_records.create_index([("created_by", 1), ("name", 1)])
    db.password_resets.create_index("expires_at", expireAfterSeconds=0)

with app.app_context():
    ensure_indexes()

def logged_in():
    return bool(session.get("account_id"))

def current_account():
    if not logged_in():
        return None
    try:
        return mongo.db.accounts.find_one({"_id": ObjectId(session["account_id"])})
    except Exception:
        session.clear()
        return None

def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in() or current_account() is None:
            session.clear()
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def save_photo(file_storage):
    """Save an optional image and return its relative URL, or None."""
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    if not original or "." not in original:
        raise ValueError("Choose a valid image file.")
    extension = original.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Photo must be JPG, JPEG, PNG, or WEBP.")
    # Random name avoids collisions and prevents user-controlled paths.
    filename = f"{secrets.token_hex(16)}.{extension}"
    target = Path(app.config["UPLOAD_FOLDER"]) / filename
    file_storage.save(target)
    return f"uploads/{filename}"

def delete_photo(photo_url):
    if not photo_url or not photo_url.startswith("uploads/"):
        return
    path = Path(app.config["UPLOAD_FOLDER"]) / Path(photo_url).name
    try:
        path.resolve().relative_to(Path(app.config["UPLOAD_FOLDER"]).resolve())
        if path.is_file():
            path.unlink()
    except (ValueError, OSError):
        pass

def parse_record_form():
    name = request.form.get("name", "").strip()
    age_raw = request.form.get("age", "").strip()
    city = request.form.get("city", "").strip()
    number = request.form.get("number", "").strip()
    role = request.form.get("role", "").strip()
    place = request.form.get("place", "").strip()
    if not name or not city or not number:
        raise ValueError("Name, city, and number are required.")
    try:
        age = int(age_raw)
    except ValueError:
        raise ValueError("Age must be a whole number.")
    if age < 0 or age > 120:
        raise ValueError("Enter an age between 0 and 120.")
    if role not in ROLES:
        raise ValueError("Choose a valid role.")
    if place not in PLACES:
        raise ValueError("Choose Yes or No for place.")
    if len(name) > 100 or len(city) > 100 or len(number) > 30:
        raise ValueError("One or more fields are too long.")
    return {"name": name, "age": age, "city": city, "number": number,
            "role": role, "place": place}

def send_reset_email(email, link):
    cfg = app.config
    if not (cfg["MAIL_SERVER"] and cfg["MAIL_DEFAULT_SENDER"]):
        # Local development fallback: never use this mode on a public deployment.
        print(f"\n[LOCAL PASSWORD RESET] For {email}: {link}\n")
        return False
    msg = EmailMessage()
    msg["Subject"] = "Reset your User Management password"
    msg["From"] = cfg["MAIL_DEFAULT_SENDER"]
    msg["To"] = email
    msg.set_content(f"Use this link within 30 minutes to reset your password:\n\n{link}\n\nIf you did not request this, ignore this email.")
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=15) as smtp:
        if cfg["MAIL_USE_TLS"]:
            smtp.starttls()
        if cfg["MAIL_USERNAME"]:
            smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        smtp.send_message(msg)
    return True

@app.context_processor
def inject_layout_data():
    account = current_account() if logged_in() else None
    return {"current_user": account, "now_year": datetime.now().year}

@app.route("/")
def index():
    return redirect(url_for("records") if logged_in() else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if logged_in() and current_account():
        return redirect(url_for("records"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        account = mongo.db.accounts.find_one({"email": email})
        if account and check_password_hash(account["password_hash"], password):
            session.clear()
            session["account_id"] = str(account["_id"])
            session.permanent = True
            app.permanent_session_lifetime = timedelta(hours=8)
            flash("Login successful. Welcome back!", "success")
            return redirect(url_for("records"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        age_raw = request.form.get("age", "").strip()
        city = request.form.get("city", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        photo_url = None
        try:
            if not full_name or not email or not password:
                raise ValueError("Name, email, and password are required.")
            if len(full_name) > 100 or len(email) > 254:
                raise ValueError("Name or email is too long.")
            if len(password) < 10:
                raise ValueError("Use a password with at least 10 characters.")
            if password != confirm:
                raise ValueError("Passwords do not match.")
            if mongo.db.accounts.find_one({"email": email}):
                raise ValueError("An account with this email already exists.")
            age = None
            if age_raw:
                age = int(age_raw)
                if age < 13 or age > 120:
                    raise ValueError("Enter an age between 13 and 120.")
            photo_url = save_photo(request.files.get("profile_photo"))
            doc = {
                "full_name": full_name, "email": email, "phone": phone,
                "age": age, "city": city, "profile_photo": photo_url,
                "password_hash": generate_password_hash(password),
                "created_at": utcnow()
            }
            mongo.db.accounts.insert_one(doc)
            flash("Account created. You can now log in.", "success")
            return redirect(url_for("login"))
        except ValueError as exc:
            if photo_url:
                delete_photo(photo_url)
            flash(str(exc), "error")
        except Exception:
            if photo_url:
                delete_photo(photo_url)
            flash("Registration could not be completed. Please check your details and try again.", "error")
    return render_template("register.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        account = mongo.db.accounts.find_one({"email": email})
        # Same public response whether or not the email exists.
        flash("If an account exists for that email, password reset instructions have been sent.", "success")
        if account:
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            expires = utcnow() + timedelta(minutes=30)
            mongo.db.password_resets.insert_one({
                "account_id": account["_id"], "token_hash": token_hash,
                "expires_at": expires, "created_at": utcnow()
            })
            link = f"{app.config['APP_BASE_URL'].rstrip('/')}{url_for('reset_password', token=raw_token)}"
            try:
                sent = send_reset_email(email, link)
                if not sent:
                    flash("Local development mode: the reset link was printed in the terminal running Flask.", "info")
            except Exception:
                app.logger.exception("Could not send reset email")
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    reset = mongo.db.password_resets.find_one({"token_hash": token_hash, "expires_at": {"$gt": utcnow()}})
    if not reset:
        flash("That reset link is invalid or expired. Request a new one.", "error")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 10:
            flash("Use a password with at least 10 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            mongo.db.accounts.update_one({"_id": reset["account_id"]},
                                         {"$set": {"password_hash": generate_password_hash(password)}})
            mongo.db.password_resets.delete_many({"account_id": reset["account_id"]})
            flash("Password reset successful. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/records")
@login_required
def records():
    q = request.args.get("q", "").strip()
    query = {"created_by": ObjectId(session["account_id"])}
    if q:
        safe_q = q[:100]
        query["$or"] = [
            {"name": {"$regex": safe_q, "$options": "i"}},
            {"city": {"$regex": safe_q, "$options": "i"}},
            {"number": {"$regex": safe_q, "$options": "i"}},
            {"role": {"$regex": safe_q, "$options": "i"}},
        ]
    rows = list(mongo.db.user_records.find(query).sort("created_at", -1).limit(500))
    return render_template("records.html", records=rows, search=q)

@app.route("/users/add", methods=["GET", "POST"])
@login_required
def add_user():
    if request.method == "POST":
        photo_url = None
        try:
            data = parse_record_form()
            photo_url = save_photo(request.files.get("photo"))
            data.update({"photo": photo_url, "created_by": ObjectId(session["account_id"]), "created_at": utcnow()})
            mongo.db.user_records.insert_one(data)
            flash("User record added.", "success")
            return redirect(url_for("records"))
        except ValueError as exc:
            if photo_url:
                delete_photo(photo_url)
            flash(str(exc), "error")
    return render_template("user_form.html", mode="Add", record=None, roles=ROLES, places=PLACES)

@app.route("/users/<record_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(record_id):
    record = get_owned_record(record_id)
    if request.method == "POST":
        new_photo = None
        try:
            data = parse_record_form()
            new_photo = save_photo(request.files.get("photo"))
            if new_photo:
                data["photo"] = new_photo
            data["updated_at"] = utcnow()
            mongo.db.user_records.update_one({"_id": record["_id"], "created_by": ObjectId(session["account_id"])},
                                             {"$set": data})
            if new_photo and record.get("photo"):
                delete_photo(record["photo"])
            flash("User record updated.", "success")
            return redirect(url_for("records"))
        except ValueError as exc:
            if new_photo:
                delete_photo(new_photo)
            flash(str(exc), "error")
    return render_template("user_form.html", mode="Edit", record=record, roles=ROLES, places=PLACES)

@app.route("/users/<record_id>/delete", methods=["POST"])
@login_required
def delete_user(record_id):
    record = get_owned_record(record_id)
    mongo.db.user_records.delete_one({"_id": record["_id"], "created_by": ObjectId(session["account_id"])})
    delete_photo(record.get("photo"))
    flash("User record deleted.", "success")
    return redirect(url_for("records"))

def get_owned_record(record_id):
    try:
        oid = ObjectId(record_id)
    except Exception:
        abort(404)
    record = mongo.db.user_records.find_one({"_id": oid, "created_by": ObjectId(session["account_id"])})
    if not record:
        abort(404)
    return record

@app.errorhandler(413)
def file_too_large(_error):
    flash("Upload too large. Maximum request size is 5 MB.", "error")
    return redirect(request.referrer or url_for("records"))

@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404

if __name__ == "__main__":
    # Debug is useful locally; turn it off for deployment.
    app.run(host="127.0.0.1", port=5000, debug=True)
