from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF
import sqlite3
import os
import datetime
import io

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "gas.db")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "change-this-secret-key"

GAS_OPTIONS = [
    {"label": "6kg Cylinder", "type": "6kg"},
    {"label": "13kg Cylinder", "type": "13kg"},
    {"label": "3kg Cylinder", "type": "3kg"},
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_products():
    with get_db() as conn:
        try:
            products = conn.execute("SELECT * FROM gas_products ORDER BY id ASC").fetchall()
        except sqlite3.OperationalError:
            return GAS_OPTIONS
    return products or GAS_OPTIONS


def init_db():
    tables = []
    with get_db() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = [row[0] for row in rows]

        if "users" not in tables:
            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    approved INTEGER DEFAULT 1,
                    is_main_seller INTEGER DEFAULT 0
                )
                """
            )

        if "orders" not in tables:
            conn.execute(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    gas_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

        if "gas_products" not in tables:
            conn.execute(
                """
                CREATE TABLE gas_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    type TEXT NOT NULL,
                    image_url TEXT,
                    description TEXT,
                    available_cylinders INTEGER DEFAULT 0,
                    created_by INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                )
                """
            )

        existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(gas_products)").fetchall()]
        if "description" not in existing_columns:
            conn.execute("ALTER TABLE gas_products ADD COLUMN description TEXT")
        if "available_cylinders" not in existing_columns:
            conn.execute("ALTER TABLE gas_products ADD COLUMN available_cylinders INTEGER DEFAULT 0")
        conn.commit()

        existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "approved" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN approved INTEGER DEFAULT 1")
        if "is_main_seller" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_main_seller INTEGER DEFAULT 0")
        if "photo_url" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN photo_url TEXT")
        conn.commit()

        main_seller = conn.execute(
            "SELECT id FROM users WHERE role = 'seller' AND is_main_seller = 1"
        ).fetchone()

        if not main_seller:
            admin_user = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                ("admin",),
            ).fetchone()

            if admin_user:
                conn.execute(
                    "UPDATE users SET role = 'seller', approved = 1, is_main_seller = 1, email = ?, password = ? WHERE id = ?",
                    ("seller@example.com", generate_password_hash("admin123"), admin_user["id"]),
                )
                main_seller_id = admin_user["id"]
            else:
                conn.execute(
                    "INSERT INTO users (username, password, role, email, phone, approved, is_main_seller) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "admin",
                        generate_password_hash("admin123"),
                        "seller",
                        "seller@example.com",
                        "0000000000",
                        1,
                        1,
                    ),
                )
                main_seller_id = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()[0]

            product_count = conn.execute("SELECT COUNT(*) FROM gas_products").fetchone()[0]
            if product_count == 0:
                default_products = [
                    ("6kg Cylinder", "6kg", "", "Standard 6kg gas cylinder for home use", 50, main_seller_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    ("13kg Cylinder", "13kg", "", "Medium 13kg gas cylinder for cooking", 30, main_seller_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    ("3kg Cylinder", "3kg", "", "Small 3kg gas cylinder for camping", 20, main_seller_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ]
                conn.executemany(
                    "INSERT INTO gas_products (label, type, image_url, description, available_cylinders, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    default_products,
                )
                conn.commit()


def ensure_database():
    init_db()

ensure_database()


def current_user():
    if "user_id" not in session:
        return None

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        return user


@app.context_processor
def inject_seller_stats():
    user = current_user()
    if not user or user["role"] != "seller":
        return {}

    with get_db() as conn:
        total_sold_row = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS total_sold FROM orders"
        ).fetchone()
        total_sold = total_sold_row["total_sold"] if total_sold_row else 0

        products = get_products()
        sold_by_type = {
            row["gas_type"]: row["sold_qty"]
            for row in conn.execute(
                "SELECT gas_type, COALESCE(SUM(quantity), 0) AS sold_qty FROM orders GROUP BY gas_type"
            ).fetchall()
        }

        product_stats = []
        total_remaining = 0
        for product in products:
            remaining = product["available_cylinders"] or 0
            sold = sold_by_type.get(product["type"], 0)
            total_remaining += remaining
            maximum = sold + remaining
            sold_percent = int((sold / maximum) * 100) if maximum > 0 else 0
            product_stats.append({
                "label": product["label"],
                "type": product["type"],
                "sold": sold,
                "remaining": remaining,
                "sold_percent": sold_percent,
            })

        top_product = None
        if product_stats:
            top_product = max(product_stats, key=lambda p: p["sold"])["type"]

    return {
        "seller_stats": {
            "total_sold": total_sold,
            "total_remaining": total_remaining,
            "product_count": len(products),
            "top_product": top_product,
            "product_stats": product_stats,
        }
    }


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "buyer")

        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if not user:
            flash("User not found. Please sign up or check your username.", "error")
            return redirect(url_for("login"))

        if user["role"] != role:
            flash("Role does not match. Use the correct buyer or seller login.", "error")
            return redirect(url_for("login"))

        if user["role"] == "seller" and user["approved"] == 0:
            flash("Your seller account is pending approval from the main seller.", "error")
            return redirect(url_for("login"))

        if check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

        flash("Incorrect password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "buyer")

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("signup"))

        hashed_password = generate_password_hash(password)
        try:
            with get_db() as conn:
                approved = 1
                is_main_seller = 0
                if role == "seller":
                    main_seller = conn.execute(
                        "SELECT id FROM users WHERE role = 'seller' AND is_main_seller = 1"
                    ).fetchone()
                    if main_seller:
                        approved = 0
                    else:
                        approved = 1
                        is_main_seller = 1

                conn.execute(
                    "INSERT INTO users (username, password, role, email, phone, approved, is_main_seller) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        username,
                        hashed_password,
                        role,
                        email or None,
                        phone or None,
                        approved,
                        is_main_seller,
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            flash("That username is already taken. Choose another one.", "error")
            return redirect(url_for("signup"))

        if role == "seller" and approved == 0:
            flash("Seller account created successfully. Await main seller approval.", "success")
        else:
            flash("Account created successfully. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    with get_db() as conn:
        products = get_products()
        # Convert Row objects to dictionaries for JSON serialization
        gas_options = [dict(product) for product in products]
        if user["role"] == "seller":
            orders = conn.execute(
                "SELECT orders.*, users.username FROM orders JOIN users ON orders.user_id = users.id ORDER BY orders.created_at DESC"
            ).fetchall()
            total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            buyer_count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM orders").fetchone()[0]
        else:
            orders = conn.execute(
                "SELECT orders.*, users.username FROM orders JOIN users ON orders.user_id = users.id WHERE user_id = ? ORDER BY orders.created_at DESC",
                (user["id"],),
            ).fetchall()
            total_orders = len(orders)
            buyer_count = 1

    return render_template(
        "dashboard.html",
        user=user,
        gas_options=gas_options,
        orders=orders,
        total_orders=total_orders,
        buyer_count=buyer_count,
    )


@app.route("/confirmations")
def confirmations():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller" or user["is_main_seller"] != 1:
        flash("Only the main seller may approve new seller accounts.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        pending_sellers = conn.execute(
            "SELECT id, username, email, phone FROM users WHERE role = 'seller' AND approved = 0 ORDER BY username ASC"
        ).fetchall()

    return render_template("confirmations.html", user=user, pending_sellers=pending_sellers)


@app.route("/confirmations/approve/<int:user_id>", methods=["POST"])
def approve_seller(user_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller" or user["is_main_seller"] != 1:
        flash("Only the main seller may approve new seller accounts.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        target = conn.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'seller' AND approved = 0",
            (user_id,),
        ).fetchone()
        if not target:
            flash("Seller request not found.", "error")
            return redirect(url_for("confirmations"))
        conn.execute(
            "UPDATE users SET approved = 1 WHERE id = ?",
            (user_id,),
        )
        conn.commit()

    flash("Seller request approved.", "success")
    return redirect(url_for("confirmations"))


@app.route("/confirmations/reject/<int:user_id>", methods=["POST"])
def reject_seller(user_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller" or user["is_main_seller"] != 1:
        flash("Only the main seller may reject new seller accounts.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        target = conn.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'seller' AND approved = 0",
            (user_id,),
        ).fetchone()
        if not target:
            flash("Seller request not found.", "error")
            return redirect(url_for("confirmations"))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    flash("Seller request rejected and removed.", "success")
    return redirect(url_for("confirmations"))


@app.route("/sellers")
def sellers():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller" or user["is_main_seller"] != 1:
        flash("Only the main seller may manage seller accounts.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        seller_accounts = conn.execute(
            "SELECT id, username, email, phone, approved, is_main_seller FROM users WHERE role = 'seller' ORDER BY username ASC"
        ).fetchall()

    return render_template("sellers.html", user=user, seller_accounts=seller_accounts)


@app.route("/seller_stats")
def seller_stats_page():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller":
        flash("Only sellers may view seller statistics.", "error")
        return redirect(url_for("dashboard"))

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    with get_db() as conn:
        base_query = "SELECT COALESCE(SUM(quantity), 0) AS total_sold FROM orders"
        params = []
        conditions = []

        if start_date:
            conditions.append("DATE(created_at) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(created_at) <= ?")
            params.append(end_date)

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        total_sold_row = conn.execute(base_query, tuple(params)).fetchone()
        total_sold = total_sold_row["total_sold"] if total_sold_row else 0

        products = get_products()
        sold_query = "SELECT gas_type, COALESCE(SUM(quantity), 0) AS sold_qty FROM orders"
        sold_params = params.copy()
        sold_conditions = conditions.copy()

        if sold_conditions:
            sold_query += " WHERE " + " AND ".join(sold_conditions)

        sold_query += " GROUP BY gas_type"
        sold_by_type = {
            row["gas_type"]: row["sold_qty"]
            for row in conn.execute(sold_query, tuple(sold_params)).fetchall()
        }

        product_stats = []
        total_remaining = 0
        for product in products:
            remaining = product["available_cylinders"] or 0
            sold = sold_by_type.get(product["type"], 0)
            total_remaining += remaining
            maximum = sold + remaining
            sold_percent = int((sold / maximum) * 100) if maximum > 0 else 0
            product_stats.append({
                "label": product["label"],
                "type": product["type"],
                "sold": sold,
                "remaining": remaining,
                "sold_percent": sold_percent,
            })

        top_product = None
        if product_stats:
            top_product = max(product_stats, key=lambda p: p["sold"])["type"]

    seller_stats = {
        "total_sold": total_sold,
        "total_remaining": total_remaining,
        "product_count": len(products),
        "top_product": top_product,
        "product_stats": product_stats,
    }

    return render_template("seller_stats.html", 
                         user=user, 
                         seller_stats=seller_stats,
                         start_date=start_date,
                         end_date=end_date)


@app.route("/sellers/delete/<int:user_id>", methods=["POST"])
def delete_seller(user_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller" or user["is_main_seller"] != 1:
        flash("Only the main seller may delete seller accounts.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        target = conn.execute(
            "SELECT id, username, is_main_seller FROM users WHERE id = ? AND role = 'seller'",
            (user_id,),
        ).fetchone()
        if not target:
            flash("Seller not found.", "error")
            return redirect(url_for("sellers"))
        if target["is_main_seller"] == 1:
            flash("You cannot delete the main seller account.", "error")
            return redirect(url_for("sellers"))

        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    flash("Seller account deleted successfully.", "success")
    return redirect(url_for("sellers"))


@app.route("/account", methods=["GET", "POST"])
def account():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_username = request.form.get("new_username", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        new_photo_url = request.form.get("photo_url", "").strip()

        if not current_password:
            flash("Current password is required to update account.", "error")
            return redirect(url_for("account"))

        if not check_password_hash(user["password"], current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("account"))

        if new_password:
            if new_password != confirm_password:
                flash("New password and confirmation do not match.", "error")
                return redirect(url_for("account"))

        update_values = []
        updates = []

        file = request.files.get("photo_file")
        new_photo_url = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            stored_name = f"{timestamp}_{filename}"
            upload_path = os.path.join(BASE_DIR, "static", "uploads", stored_name)
            file.save(upload_path)
            new_photo_url = f"/static/uploads/{stored_name}"
            updates.append("photo_url = ?")
            update_values.append(new_photo_url)

        if new_username and new_username != user["username"]:
            with get_db() as conn:
                existing = conn.execute("SELECT id FROM users WHERE username = ?", (new_username,)).fetchone()
            if existing:
                flash("That username is already taken.", "error")
                return redirect(url_for("account"))
            updates.append("username = ?")
            update_values.append(new_username)

        if new_password:
            updates.append("password = ?")
            update_values.append(generate_password_hash(new_password))

        if not updates:
            flash("No changes were submitted.", "error")
            return redirect(url_for("account"))

        update_values.append(user["id"])
        with get_db() as conn:
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(update_values))
            conn.commit()

        if new_username:
            session["username"] = new_username

        flash("Account information updated successfully.", "success")
        return redirect(url_for("account"))

    return render_template("account.html", user=user)


@app.route("/report")
def report():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    with get_db() as conn:
        base_query = """
            SELECT orders.*, users.username 
            FROM orders 
            JOIN users ON orders.user_id = users.id
        """
        params = []
        conditions = []

        if user["role"] != "seller":
            conditions.append("orders.user_id = ?")
            params.append(user["id"])

        if start_date:
            conditions.append("DATE(orders.created_at) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(orders.created_at) <= ?")
            params.append(end_date)

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        base_query += " ORDER BY orders.created_at DESC"

        orders = conn.execute(base_query, tuple(params)).fetchall()

    total_orders = len(orders)
    buyer_count = 1 if user["role"] != "seller" else len({order["user_id"] for order in orders})

    # Chart data for interactive report
    gas_totals = {}
    user_totals = {}
    for order in orders:
        gas_totals[order["gas_type"]] = gas_totals.get(order["gas_type"], 0) + order["quantity"]
        user_totals[order["username"]] = user_totals.get(order["username"], 0) + 1
    
    chart_data = {
        "gas_totals": gas_totals,
        "user_totals": user_totals
    }

    return render_template("report.html", 
                         user=user, 
                         orders=orders, 
                         total_orders=total_orders, 
                         buyer_count=buyer_count,
                         start_date=start_date,
                         end_date=end_date,
                         chart_data=chart_data)


@app.route("/report/pdf")
def download_report():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    with get_db() as conn:
        base_query = """
            SELECT orders.*, users.username 
            FROM orders 
            JOIN users ON orders.user_id = users.id
        """
        params = []
        conditions = []

        if user["role"] != "seller":
            conditions.append("orders.user_id = ?")
            params.append(user["id"])

        if start_date:
            conditions.append("DATE(orders.created_at) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(orders.created_at) <= ?")
            params.append(end_date)

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        base_query += " ORDER BY orders.created_at DESC"

        orders = conn.execute(base_query, tuple(params)).fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Gas Order Report", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Generated for: {user['username']}", ln=True)
    pdf.cell(0, 8, f"Report generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
    
    if start_date or end_date:
        date_range = ""
        if start_date and end_date:
            date_range = f"Date range: {start_date} to {end_date}"
        elif start_date:
            date_range = f"From: {start_date}"
        elif end_date:
            date_range = f"To: {end_date}"
        pdf.cell(0, 8, date_range, ln=True)
    
    pdf.ln(8)

    if orders:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(40, 8, "User", border=1)
        pdf.cell(35, 8, "Gas", border=1)
        pdf.cell(35, 8, "Action", border=1)
        pdf.cell(30, 8, "Qty", border=1)
        pdf.cell(50, 8, "Date", border=1, ln=True)
        pdf.set_font("Arial", "", 11)

        for order in orders:
            pdf.cell(40, 8, str(order["username"]), border=1)
            pdf.cell(35, 8, str(order["gas_type"]), border=1)
            pdf.cell(35, 8, str(order["action"]), border=1)
            pdf.cell(30, 8, str(order["quantity"]), border=1)
            pdf.cell(50, 8, str(order["created_at"]), border=1, ln=True)
    else:
        pdf.cell(0, 8, "No ordered gas records found.", ln=True)

    # Simple bar chart for gas totals (no FPDF outline/link - fpdf2 limitation)
    pdf.ln(10)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Gas Type Totals Chart", ln=True)
    pdf.set_font("Arial", "", 10)
    
    gas_totals = {}
    for order in orders:
        gas_totals[order["gas_type"]] = gas_totals.get(order["gas_type"], 0) + order["quantity"]
    
    max_qty = max(gas_totals.values()) if gas_totals else 1
    bar_width = 30
    bar_height_scale = 100 / max_qty
    
    y_pos = pdf.get_y()
    for gas_type, qty in gas_totals.items():
        x = 20 + (list(gas_totals.keys()).index(gas_type) * 35)
        bar_height = qty * bar_height_scale
        pdf.set_fill_color(52, 152, 219)
        pdf.rect(x, y_pos + 100 - bar_height, bar_width, bar_height, 'F')
        pdf.set_xy(x, y_pos + 105)
        pdf.cell(bar_width, 5, gas_type, 0, 0, 'C')
    
    # Table with icons (text only - no emojis for fpdf2 compatibility)
    pdf.ln(20)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(40, 8, "User", border=1)
    pdf.cell(35, 8, "Gas", border=1)
    pdf.cell(35, 8, "Action", border=1)
    pdf.cell(30, 8, "Qty", border=1)
    pdf.cell(50, 8, "Date", border=1, ln=True)
    pdf.set_font("Arial", "", 11)
    
    for order in orders:
        pdf.set_text_color(0, 0, 0)
        pdf.cell(40, 8, str(order["username"]), border=1)
        pdf.cell(35, 8, str(order["gas_type"]), border=1)
        pdf.cell(35, 8, str(order["action"]), border=1)
        pdf.cell(30, 8, str(order["quantity"]), border=1)
        pdf.cell(50, 8, str(order["created_at"]), border=1, ln=True)
    
    # Hyperlink footer
    pdf.ln(10)
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 255)
    pdf.cell(0, 10, f"View dashboard: {url_for('dashboard', _external=True)}", 0, 1, 'C', link=url_for('dashboard', _external=True))
    
    pdf_bytes = pdf.output(dest='S')
    output = io.BytesIO(pdf_bytes)
    output.seek(0)
    filename = f"gas-report-{user['username']}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/seller_stats/pdf")
def download_seller_stats_report():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user["role"] != "seller":
        flash("Only sellers may download seller statistics reports.", "error")
        return redirect(url_for("dashboard"))

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    with get_db() as conn:
        base_query = "SELECT COALESCE(SUM(quantity), 0) AS total_sold FROM orders"
        params = []
        conditions = []

        if start_date:
            conditions.append("DATE(created_at) >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(created_at) <= ?")
            params.append(end_date)

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        total_sold_row = conn.execute(base_query, tuple(params)).fetchone()
        total_sold = total_sold_row["total_sold"] if total_sold_row else 0

        products = get_products()
        sold_query = "SELECT gas_type, COALESCE(SUM(quantity), 0) AS sold_qty FROM orders"
        sold_params = params.copy()
        sold_conditions = conditions.copy()

        if sold_conditions:
            sold_query += " WHERE " + " AND ".join(sold_conditions)

        sold_query += " GROUP BY gas_type"
        sold_by_type = {
            row["gas_type"]: row["sold_qty"]
            for row in conn.execute(sold_query, tuple(sold_params)).fetchall()
        }

        product_stats = []
        total_remaining = 0
        for product in products:
            remaining = product["available_cylinders"] or 0
            sold = sold_by_type.get(product["type"], 0)
            total_remaining += remaining
            maximum = sold + remaining
            sold_percent = int((sold / maximum) * 100) if maximum > 0 else 0
            product_stats.append({
                "label": product["label"],
                "type": product["type"],
                "sold": sold,
                "remaining": remaining,
                "sold_percent": sold_percent,
            })

        top_product = None
        if product_stats:
            top_product = max(product_stats, key=lambda p: p["sold"])["type"]

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Seller Statistics Report", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Generated for: {user['username']}", ln=True)
    pdf.cell(0, 8, f"Report generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
    
    if start_date or end_date:
        date_range = ""
        if start_date and end_date:
            date_range = f"Date range: {start_date} to {end_date}"
        elif start_date:
            date_range = f"From: {start_date}"
        elif end_date:
            date_range = f"To: {end_date}"
        pdf.cell(0, 8, date_range, ln=True)
    
    pdf.ln(8)

    # Summary statistics
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Summary Statistics", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 6, f"Total Sold: {total_sold} cylinders", ln=True)
    pdf.cell(0, 6, f"Total Remaining: {total_remaining} cylinders", ln=True)
    pdf.cell(0, 6, f"Number of Products: {len(products)}", ln=True)
    pdf.cell(0, 6, f"Top Product: {top_product or 'None'}", ln=True)
    
    pdf.ln(8)

    # Product details
    if product_stats:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Product Details", ln=True)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(50, 8, "Gas Type", border=1)
        pdf.cell(25, 8, "Sold", border=1)
        pdf.cell(30, 8, "Remaining", border=1)
        pdf.cell(25, 8, "Progress", border=1, ln=True)
        pdf.set_font("Arial", "", 10)

        for product in product_stats:
            pdf.cell(50, 8, str(product["label"]), border=1)
            pdf.cell(25, 8, str(product["sold"]), border=1)
            pdf.cell(30, 8, str(product["remaining"]), border=1)
            pdf.cell(25, 8, f"{product['sold_percent']}%", border=1, ln=True)
    else:
        pdf.cell(0, 8, "No product statistics available.", ln=True)

    pdf_bytes = pdf.output(dest='S')
    output = io.BytesIO(pdf_bytes)
    output.seek(0)
    filename = f"seller-stats-{user['username']}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/product/add", methods=["POST"])
def add_product():
    user = current_user()
    if not user or user["role"] != "seller":
        flash("Only sellers may add gas products.", "error")
        return redirect(url_for("dashboard"))

    label = request.form.get("label", "").strip()
    gas_type = request.form.get("type", "").strip()
    description = request.form.get("description", "").strip()
    available_cylinders = request.form.get("available_cylinders", "0")
    image_url = request.form.get("image_url", "").strip()

    if not label or not gas_type:
        flash("Product label and type are required.", "error")
        return redirect(url_for("dashboard"))

    try:
        available_cylinders = int(available_cylinders)
    except ValueError:
        available_cylinders = 0

    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO gas_products (label, type, description, available_cylinders, image_url, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (label, gas_type, description or None, available_cylinders, image_url or None, user["id"], created_at),
        )
        conn.commit()

    flash("Product added successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/order", methods=["POST"])
def order_gas():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    gas_type = request.form.get("gas_type")
    action = request.form.get("action")
    quantity = int(request.form.get("quantity", 1))

    if not gas_type or not action:
        flash("Please select a gas type and action.", "error")
        return redirect(url_for("dashboard"))

    # Check available quantity
    with get_db() as conn:
        product = conn.execute("SELECT available_cylinders FROM gas_products WHERE type = ?", (gas_type,)).fetchone()
        if product and product["available_cylinders"] < quantity:
            flash(f"Only {product['available_cylinders']} cylinders available. Please reduce quantity.", "error")
            return redirect(url_for("dashboard"))

    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO orders (user_id, gas_type, action, quantity, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], gas_type, action, quantity, created_at),
        )
        # Update available cylinders
        if product:
            conn.execute(
                "UPDATE gas_products SET available_cylinders = available_cylinders - ? WHERE type = ?",
                (quantity, gas_type),
            )
        conn.commit()

    flash("Gas order recorded successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/edit_product/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    user = current_user()
    if not user or user["role"] != "seller":
        flash("Only sellers may edit products.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        product = conn.execute("SELECT * FROM gas_products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            flash("Product not found.", "error")
            return redirect(url_for("dashboard"))
        
        if product["created_by"] != user["id"]:
            flash("You can only edit your own products.", "error")
            return redirect(url_for("dashboard"))

    if request.method == "POST":
        label = request.form.get("label", "").strip()
        description = request.form.get("description", "").strip()
        available_cylinders = request.form.get("available_cylinders", "0")
        
        try:
            available_cylinders = int(available_cylinders)
        except ValueError:
            available_cylinders = 0

        if not label:
            flash("Product label is required.", "error")
            return redirect(url_for("edit_product", product_id=product_id))

        with get_db() as conn:
            conn.execute(
                "UPDATE gas_products SET label = ?, description = ?, available_cylinders = ? WHERE id = ?",
                (label, description, available_cylinders, product_id),
            )
            conn.commit()

        flash("Product updated successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_product.html", product=product)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
