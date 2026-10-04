import os
import sqlite3
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Flask, request, redirect, url_for, session,
    flash, render_template_string, abort
)
from werkzeug.security import generate_password_hash, check_password_hash


# ============================================================
# CONFIG
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32)
)

DATABASE = "nova_shop.db"

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "admin@novashop.com"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "ChangeMe123!"
)


# ============================================================
# DATABASE
# ============================================================

def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db():

    db = get_db()

    db.executescript("""

    CREATE TABLE IF NOT EXISTS users (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL,

        email TEXT UNIQUE NOT NULL,

        password TEXT NOT NULL,

        role TEXT NOT NULL DEFAULT 'customer',

        active INTEGER NOT NULL DEFAULT 1,

        created_at TEXT NOT NULL

    );


    CREATE TABLE IF NOT EXISTS products (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        name TEXT NOT NULL,

        slug TEXT UNIQUE NOT NULL,

        category TEXT NOT NULL,

        description TEXT DEFAULT '',

        image TEXT DEFAULT '',

        price REAL NOT NULL,

        stock INTEGER NOT NULL DEFAULT 0,

        featured INTEGER DEFAULT 0,

        active INTEGER DEFAULT 1,

        created_at TEXT NOT NULL

    );


    CREATE TABLE IF NOT EXISTS orders (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        customer_name TEXT NOT NULL,

        customer_email TEXT NOT NULL,

        phone TEXT DEFAULT '',

        address TEXT DEFAULT '',

        total REAL NOT NULL,

        status TEXT DEFAULT 'Pending',

        payment_status TEXT DEFAULT 'Unpaid',

        created_at TEXT NOT NULL,

        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE SET NULL

    );


    CREATE TABLE IF NOT EXISTS order_items (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        order_id INTEGER NOT NULL,

        product_id INTEGER,

        product_name TEXT NOT NULL,

        price REAL NOT NULL,

        quantity INTEGER NOT NULL,

        FOREIGN KEY(order_id)
        REFERENCES orders(id)
        ON DELETE CASCADE

    );


    CREATE TABLE IF NOT EXISTS settings (

        key TEXT PRIMARY KEY,

        value TEXT NOT NULL

    );

    """)


    # --------------------------------------------------------
    # CREATE ADMIN
    # --------------------------------------------------------

    admin = db.execute(
        "SELECT id FROM users WHERE email=?",
        (ADMIN_EMAIL.lower(),)
    ).fetchone()

    if not admin:

        db.execute(
            """
            INSERT INTO users
            (name,email,password,role,created_at)

            VALUES (?,?,?,?,?)
            """,
            (
                "Store Admin",
                ADMIN_EMAIL.lower(),
                generate_password_hash(ADMIN_PASSWORD),
                "admin",
                datetime.utcnow().isoformat()
            )
        )


    # --------------------------------------------------------
    # DEFAULT PRODUCTS
    # --------------------------------------------------------

    count = db.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    if count == 0:

        products = [

            (
                "NovaPulse Headphones",
                "novapulse-headphones",
                "Audio",
                "Premium wireless headphones.",
                "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=85",
                99,
                48,
                1
            ),

            (
                "Urban Backpack",
                "urban-backpack",
                "Bags",
                "Modern everyday backpack.",
                "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=900&q=85",
                45,
                82,
                1
            ),

            (
                "NovaWatch Pro",
                "novawatch-pro",
                "Wearables",
                "Smart everyday watch.",
                "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=900&q=85",
                129,
                26,
                1
            ),

            (
                "Ceramic Water Bottle",
                "ceramic-water-bottle",
                "Lifestyle",
                "Minimal ceramic water bottle.",
                "https://images.unsplash.com/photo-1602143407151-7111542de6e8?auto=format&fit=crop&w=900&q=85",
                22,
                73,
                1
            )

        ]


        for p in products:

            db.execute(
                """
                INSERT INTO products
                (
                    name,
                    slug,
                    category,
                    description,
                    image,
                    price,
                    stock,
                    featured,
                    created_at
                )

                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                p + (datetime.utcnow().isoformat(),)
            )


    # --------------------------------------------------------
    # DEFAULT SETTINGS
    # --------------------------------------------------------

    settings = {

        "store_name": "NOVA SHOP",

        "hero_title":
        "Elevate Your Everyday Style",

        "hero_text":
        "Discover curated products designed for modern living. Quality, style, and innovation delivered to your door."

    }


    for key, value in settings.items():

        db.execute(
            """
            INSERT OR IGNORE INTO settings
            (key,value)

            VALUES (?,?)
            """,
            (key, value)
        )


    db.commit()

    db.close()


init_db()


# ============================================================
# HELPERS
# ============================================================

def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id=? AND active=1",
        (user_id,)
    ).fetchone()

    db.close()

    return user


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user():

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user or user["role"] != "admin":

            abort(403)

        return function(*args, **kwargs)

    return wrapper


def get_settings():

    db = get_db()

    rows = db.execute(
        "SELECT key,value FROM settings"
    ).fetchall()

    db.close()

    return {
        row["key"]: row["value"]
        for row in rows
    }


# ============================================================
# CSS
# ============================================================

CSS = r"""

*{
    box-sizing:border-box;
}

body{

    margin:0;

    font-family:
    Arial,
    Helvetica,
    sans-serif;

    color:white;

    background:

    radial-gradient(
        circle at 5% 80%,
        #4c20ff,
        transparent 25%
    ),

    radial-gradient(
        circle at 95% 35%,
        #c13dff,
        transparent 30%
    ),

    linear-gradient(
        135deg,
        #211047,
        #65429c,
        #29135d
    );

    min-height:100vh;
}

a{

    text-decoration:none;

    color:inherit;
}

button,
input,
textarea,
select{

    font:inherit;
}

button{

    cursor:pointer;
}

.container{

    width:min(
        1250px,
        calc(100% - 28px)
    );

    margin:auto;
}

.glass{

    background:
    linear-gradient(
        135deg,
        rgba(255,255,255,.16),
        rgba(255,255,255,.06)
    );

    border:
    1px solid
    rgba(255,255,255,.25);

    box-shadow:
    0 25px 70px
    rgba(0,0,0,.25),

    inset
    0 1px
    rgba(255,255,255,.2);

    backdrop-filter:
    blur(20px);
}

.header{

    margin-top:25px;

    min-height:95px;

    border-radius:22px;

    display:flex;

    align-items:center;

    padding:20px 30px;

    gap:30px;
}

.logo{

    font-size:32px;

    font-weight:900;

    letter-spacing:-2px;
}

.logo span{

    font-size:22px;

    font-weight:400;
}

.nav{

    display:flex;

    gap:25px;

    margin:auto;
}

.nav a{

    font-weight:bold;

    color:#fff;
}

.actions{

    display:flex;

    gap:8px;
}

.icon{

    width:45px;

    height:45px;

    display:grid;

    place-items:center;

    border-radius:12px;

    border:
    1px solid
    rgba(255,255,255,.25);

    background:
    rgba(255,255,255,.1);

    color:white;
}

.hero{

    margin-top:28px;

    padding:40px;

    border-radius:25px;

    display:grid;

    grid-template-columns:
    1.2fr .8fr;

    gap:20px;
}

.hero h1{

    font-size:48px;

    line-height:1.05;

    letter-spacing:-2px;
}

.hero p{

    color:
    rgba(255,255,255,.75);

    line-height:1.6;

    max-width:650px;
}

.pill{

    display:inline-block;

    padding:9px 14px;

    border-radius:10px;

    font-size:11px;

    font-weight:bold;

    background:
    rgba(255,255,255,.12);

    border:
    1px solid
    rgba(255,255,255,.25);
}

.buttons{

    display:flex;

    gap:12px;

    margin-top:20px;
}

.btn{

    display:inline-block;

    border:0;

    border-radius:10px;

    padding:12px 20px;

    font-weight:bold;

    color:white;
}

.primary{

    background:
    linear-gradient(
        100deg,
        #7432ef,
        #bd4cff
    );
}

.secondary{

    background:
    rgba(255,255,255,.1);

    border:
    1px solid
    rgba(255,255,255,.25);
}

.hero-visual{

    min-height:280px;

    border-radius:18px;

    display:grid;

    place-items:center;

    position:relative;
}

.headphone{

    width:190px;

    height:180px;

    position:relative;
}

.headband{

    position:absolute;

    left:35px;

    top:5px;

    width:120px;

    height:125px;

    border:
    18px solid
    #15121e;

    border-bottom-color:
    transparent;

    border-radius:70px;
}

.ear{

    position:absolute;

    top:75px;

    width:55px;

    height:75px;

    border-radius:22px;

    background:#111;

    border:3px solid #806093;
}

.ear:after{

    content:"";

    position:absolute;

    inset:9px;

    border-radius:50%;

    background:#050505;
}

.ear.left{

    left:5px;
}

.ear.right{

    right:5px;
}

.product-title{

    margin:0 0 6px;
}

.section-title{

    margin:30px 35px 15px;

    display:flex;

    justify-content:space-between;

    align-items:center;
}

.products{

    display:grid;

    grid-template-columns:
    1fr 1fr;

    gap:15px;
}

.product{

    padding:13px;

    border-radius:16px;

    display:grid;

    grid-template-columns:
    1fr 1fr;

    gap:14px;

    align-items:center;
}

.product img{

    width:100%;

    height:140px;

    object-fit:cover;

    border-radius:11px;
}

.price{

    font-weight:900;

    font-size:18px;
}

.rating{

    color:#ddd;

    font-size:11px;

    margin-top:5px;
}

.add{

    display:inline-block;

    margin-top:10px;

    padding:8px 15px;

    border-radius:8px;

    background:
    linear-gradient(
        100deg,
        #7432ef,
        #bd4cff
    );

    color:white;

    font-size:11px;

    font-weight:bold;
}

.trust{

    margin:18px auto 35px;

    max-width:800px;

    border-radius:17px;

    padding:15px;

    display:grid;

    grid-template-columns:
    repeat(3,1fr);

    gap:15px;

    text-align:center;
}

.muted{

    color:
    rgba(255,255,255,.68);

    font-size:12px;
}

.footer{

    text-align:center;

    padding:20px;

    color:#aaa;

    font-size:11px;
}


/* AUTH */

.auth-wrapper{

    min-height:100vh;

    display:grid;

    place-items:center;

    padding:20px;
}

.auth{

    width:min(
        430px,
        100%
    );

    padding:30px;

    border-radius:20px;
}

.auth h1{

    font-size:30px;
}

.field{

    display:grid;

    gap:6px;

    margin:14px 0;

    color:#ddd;

    font-size:12px;
}

input,
textarea,
select{

    width:100%;

    padding:11px;

    border-radius:9px;

    border:
    1px solid
    rgba(255,255,255,.2);

    background:
    rgba(255,255,255,.08);

    color:white;

    outline:none;
}

select option{

    background:#24134f;
}

textarea{

    min-height:100px;

    resize:vertical;
}


/* ADMIN */

.admin-layout{

    min-height:100vh;

    display:grid;

    grid-template-columns:
    240px 1fr;
}

.sidebar{

    padding:22px;

    background:
    rgba(5,2,20,.4);

    border-right:
    1px solid
    rgba(255,255,255,.1);
}

.side-link{

    display:block;

    padding:12px;

    margin:4px 0;

    border-radius:9px;

    color:#ccc;
}

.side-link:hover,
.side-link.active{

    background:
    rgba(150,60,255,.2);

    color:white;
}

.admin-main{

    padding:35px;
}

.admin-header{

    display:flex;

    justify-content:space-between;

    margin-bottom:25px;
}

.stats{

    display:grid;

    grid-template-columns:
    repeat(4,1fr);

    gap:15px;
}

.stat{

    padding:20px;

    border-radius:15px;
}

.stat b{

    display:block;

    font-size:27px;

    margin:8px 0;
}

.admin-card{

    margin-top:18px;

    padding:20px;

    border-radius:16px;
}

table{

    width:100%;

    border-collapse:collapse;
}

th,
td{

    padding:12px 8px;

    border-bottom:
    1px solid
    rgba(255,255,255,.1);

    text-align:left;

    font-size:12px;
}

th{

    color:#aaa;

    font-size:10px;
}

.table-button{

    border:0;

    border-radius:7px;

    padding:7px 10px;

    background:
    rgba(255,255,255,.12);

    color:white;
}

.status{

    display:inline-block;

    padding:5px 8px;

    border-radius:7px;

    background:
    rgba(80,255,170,.13);

    color:#8effc9;

    font-size:10px;
}

.form-card{

    max-width:750px;

    padding:22px;

    border-radius:16px;

    margin-top:18px;
}

.form-grid{

    display:grid;

    grid-template-columns:
    1fr 1fr;

    gap:14px;
}

.full{

    grid-column:
    1 / -1;
}

.flash{

    position:fixed;

    top:15px;

    right:15px;

    z-index:9999;

    padding:13px 18px;

    border-radius:10px;

    background:
    rgba(20,10,40,.9);

    border:
    1px solid
    rgba(255,255,255,.2);
}

.account{

    margin-top:30px;

    padding:30px;

    border-radius:20px;
}

.order{

    margin-top:10px;

    padding:15px;

    border-radius:12px;
}

@media(max-width:900px){

    .admin-layout{

        grid-template-columns:1fr;
    }

    .sidebar{

        display:flex;

        overflow:auto;

        gap:5px;
    }

    .side-link{

        white-space:nowrap;
    }

    .stats{

        grid-template-columns:
        1fr 1fr;
    }

}

@media(max-width:700px){

    .header{

        margin-top:8px;

        padding:15px;

    }

    .nav{

        display:none;
    }

    .hero{

        grid-template-columns:1fr;

        padding:22px;
    }

    .hero h1{

        font-size:35px;
    }

    .products{

        grid-template-columns:1fr;
    }

    .trust{

        grid-template-columns:1fr;
    }

    .stats{

        grid-template-columns:1fr;
    }

    .admin-main{

        padding:18px;
    }

    .form-grid{

        grid-template-columns:1fr;
    }

    .full{

        grid-column:auto;
    }

}
"""


# ============================================================
# BASE TEMPLATE
# ============================================================

BASE = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>
{{ settings.get('store_name','NOVA SHOP') }}
</title>

<style>
""" + CSS + """
</style>

</head>

<body>

{% with messages = get_flashed_messages() %}

{% for message in messages %}

<div class="flash">

{{ message }}

</div>

{% endfor %}

{% endwith %}

""" + "{{ content|safe }}" + """

</body>

</html>
"""


# ============================================================
# HOME
# ============================================================

HOME = """

<div class="container">

<header class="header glass">

<a
href="/"
class="logo"
>
NOVA <span>SHOP</span>
</a>

<nav class="nav">

<a href="/">Home</a>

<a href="#shop">Shop</a>

<a href="#collections">Collections</a>

<a href="#sale">Sale</a>

<a href="#about">About</a>

</nav>

<div class="actions">

<a
class="icon"
href="#shop"
>
⌕
</a>

{% if me %}

<a
class="icon"
href="/account"
>
♙
</a>

<a
class="icon"
href="/logout"
>
⇥
</a>

{% else %}

<a
class="icon"
href="/login"
>
♙
</a>

{% endif %}

</div>

</header>


<section class="hero glass">

<div>

<span class="pill">

✦ SUMMER COLLECTION · UP TO 40% OFF

</span>

<h1>

{{ settings.get(
'hero_title',
'Elevate Your Everyday Style'
) }}

</h1>

<p>

{{ settings.get(
'hero_text',
'Discover curated products designed for modern living.'
) }}

</p>

<div class="buttons">

<a
class="btn primary"
href="#shop"
>
Shop Now →
</a>

<a
class="btn secondary"
href="#collections"
>
Explore Collections
</a>

</div>

</div>


<div class="hero-visual glass">

<div class="headphone">

<div class="headband"></div>

<div class="ear left"></div>

<div class="ear right"></div>

</div>

</div>

</section>


<div
class="section-title"
id="shop"
>

<h2>

Featured Products

</h2>

</div>


<section class="products">

{% for product in products %}

<article class="product glass">

<img
src="{{ product['image'] }}"
alt="{{ product['name'] }}"
>

<div>

<h3 class="product-title">

{{ product['name'] }}

</h3>

<div class="price">

${{ "%.2f"|format(product['price']) }}

</div>

<div class="rating">

★ 4.8 · {{ product['stock'] }} in stock

</div>

<a
class="add"
href="/buy/{{ product['id'] }}"
>
Buy Now
</a>

</div>

</article>

{% endfor %}

</section>


<div
class="trust glass"
id="about"
>

<div>

<b>10K+ Products</b>

<br>

<span class="muted">
Curated for you
</span>

</div>

<div>

<b>50K+ Customers</b>

<br>

<span class="muted">
Trusted Worldwide
</span>

</div>

<div>

<b>Secure Checkout</b>

<br>

<span class="muted">
Safe & Easy Payments
</span>

</div>

</div>


<div class="footer">

© 2026 NOVA SHOP

</div>

</div>
"""


@app.route("/")
def home():

    db = get_db()

    products = db.execute(
        """
        SELECT *
        FROM products

        WHERE active=1

        ORDER BY featured DESC,id DESC
        """
    ).fetchall()

    db.close()

    return render_template_string(

        BASE,

        content=render_template_string(
            HOME,
            products=products,
            settings=get_settings(),
            me=current_user()
        ),

        settings=get_settings()

    )


# ============================================================
# SIGNUP
# ============================================================

AUTH = """

<div class="auth-wrapper">

<div class="auth glass">

<a
href="/"
class="logo"
>
NOVA <span>SHOP</span>
</a>

{% if mode == "signup" %}

<h1>Create Account</h1>

<p class="muted">
Create your NOVA SHOP account.
</p>

<form method="POST">

<label class="field">

Name

<input
name="name"
required
>

</label>


<label class="field">

Email

<input
name="email"
type="email"
required
>

</label>


<label class="field">

Password

<input
name="password"
type="password"
minlength="8"
required
>

</label>


<button
class="btn primary"
style="width:100%"
>
Create Account
</button>

</form>


<p class="muted">

Already have an account?

<a href="/login">
Login
</a>

</p>

{% else %}

<h1>Welcome Back</h1>

<p class="muted">
Login to NOVA SHOP.
</p>

<form method="POST">

<label class="field">

Email

<input
name="email"
type="email"
required
>

</label>


<label class="field">

Password

<input
name="password"
type="password"
required
>

</label>


<button
class="btn primary"
style="width:100%"
>
Login
</button>

</form>


<p class="muted">

Don't have an account?

<a href="/signup">
Create Account
</a>

</p>

{% endif %}

</div>

</div>
"""


@app.route(
    "/signup",
    methods=["GET", "POST"]
)
def signup():

    if request.method == "POST":

        name = request.form["name"].strip()

        email = request.form["email"].strip().lower()

        password = request.form["password"]


        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters."
            )

            return redirect("/signup")


        db = get_db()

        try:

            db.execute(
                """
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    role,
                    created_at
                )

                VALUES (?,?,?,?,?)
                """,

                (
                    name,
                    email,
                    generate_password_hash(password),
                    "customer",
                    datetime.utcnow().isoformat()
                )
            )

            db.commit()

            flash(
                "Account created successfully. Please login."
            )

            return redirect("/login")

        except sqlite3.IntegrityError:

            flash(
                "This email is already registered."
            )

            return redirect("/signup")

        finally:

            db.close()


    return render_template_string(

        BASE,

        content=render_template_string(
            AUTH,
            mode="signup"
        ),

        settings=get_settings()

    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        password = request.form["password"]


        db = get_db()

        user = db.execute(
            """
            SELECT *
            FROM users

            WHERE email=?
            AND active=1
            """,

            (email,)
        ).fetchone()

        db.close()


        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]


            if user["role"] == "admin":

                return redirect("/admin")

            return redirect("/account")


        flash(
            "Invalid email or password."
        )


    return render_template_string(

        BASE,

        content=render_template_string(
            AUTH,
            mode="login"
        ),

        settings=get_settings()

    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ============================================================
# ACCOUNT
# ============================================================

@app.route("/account")
@login_required
def account():

    user = current_user()

    db = get_db()

    orders = db.execute(
        """
        SELECT *
        FROM orders

        WHERE user_id=?

        ORDER BY id DESC
        """,

        (user["id"],)
    ).fetchall()

    db.close()


    content = """

    <div class="container">

    <div class="account glass">

    <h1>My Account</h1>

    <p>
    Welcome,
    {{ user['name'] }}
    </p>

    <p class="muted">
    {{ user['email'] }}
    </p>

    <a
    class="btn primary"
    href="/"
    >
    Continue Shopping
    </a>

    <a
    class="btn secondary"
    href="/logout"
    >
    Logout
    </a>

    <h2>
    My Orders
    </h2>

    {% for order in orders %}

    <div class="order glass">

    <b>
    Order #{{ order['id'] }}
    </b>

    <span style="float:right">

    ${{ "%.2f"|format(order['total']) }}

    </span>

    <br>

    <span class="muted">

    {{ order['status'] }}

    ·

    {{ order['payment_status'] }}

    </span>

    </div>

    {% else %}

    <p class="muted">
    No orders yet.
    </p>

    {% endfor %}

    </div>

    </div>
    """


    return render_template_string(

        BASE,

        content=render_template_string(
            content,
            user=user,
            orders=orders
        ),

        settings=get_settings()

    )


# ============================================================
# BUY
# ============================================================

@app.route("/buy/<int:product_id>")
@login_required
def buy(product_id):

    db = get_db()

    product = db.execute(
        """
        SELECT *
        FROM products

        WHERE id=?
        AND active=1
        """,

        (product_id,)
    ).fetchone()

    db.close()


    if not product:

        abort(404)


    content = """

    <div class="container">

    <div class="account glass">

    <h1>
    Checkout
    </h1>

    <div class="product glass">

    <img
    src="{{ product['image'] }}"
    >

    <div>

    <h2>
    {{ product['name'] }}
    </h2>

    <p>
    {{ product['description'] }}
    </p>

    <div class="price">
    ${{ "%.2f"|format(product['price']) }}
    </div>

    </div>

    </div>


    <form method="POST">

    <label class="field">

    Phone

    <input
    name="phone"
    required
    >

    </label>


    <label class="field">

    Delivery Address

    <textarea
    name="address"
    required
    ></textarea>

    </label>


    <label class="field">

    Quantity

    <input
    name="quantity"
    type="number"
    min="1"
    max="{{ product['stock'] }}"
    value="1"
    required
    >

    </label>


    <button
    class="btn primary"
    >
    Place Order
    </button>

    </form>

    </div>

    </div>
    """


    return render_template_string(

        BASE,

        content=render_template_string(
            content,
            product=product
        ),

        settings=get_settings()

    )


@app.route(
    "/buy/<int:product_id>",
    methods=["POST"]
)
@login_required
def create_order(product_id):

    quantity = int(
        request.form["quantity"]
    )

    db = get_db()

    product = db.execute(
        """
        SELECT *
        FROM products

        WHERE id=?
        AND active=1
        """,

        (product_id,)
    ).fetchone()


    if not product:

        db.close()

        abort(404)


    if quantity <= 0 or quantity > product["stock"]:

        db.close()

        flash("Invalid quantity.")

        return redirect(
            url_for(
                "buy",
                product_id=product_id
            )
        )


    user = current_user()

    total = product["price"] * quantity


    cursor = db.execute(
        """
        INSERT INTO orders

        (
            user_id,
            customer_name,
            customer_email,
            phone,
            address,
            total,
            status,
            payment_status,
            created_at
        )

        VALUES (?,?,?,?,?,?,?,?,?)
        """,

        (
            user["id"],
            user["name"],
            user["email"],
            request.form["phone"],
            request.form["address"],
            total,
            "Pending",
            "Unpaid",
            datetime.utcnow().isoformat()
        )
    )


    order_id = cursor.lastrowid


    db.execute(
        """
        INSERT INTO order_items

        (
            order_id,
            product_id,
            product_name,
            price,
            quantity
        )

        VALUES (?,?,?,?,?)
        """,

        (
            order_id,
            product["id"],
            product["name"],
            product["price"],
            quantity
        )
    )


    db.execute(
        """
        UPDATE products

        SET stock = stock - ?

        WHERE id=?
        """,

        (
            quantity,
            product_id
        )
    )


    db.commit()

    db.close()


    flash(
        f"Order #{order_id} placed successfully."
    )

    return redirect("/account")


# ============================================================
# ADMIN DASHBOARD
# ============================================================

ADMIN_LAYOUT_START = """

<div class="admin-layout">

<aside class="sidebar">

<a
href="/admin"
class="logo"
>
NOVA <span>ADMIN</span>
</a>

<a
href="/admin"
class="side-link"
>
⌂ Dashboard
</a>

<a
href="/admin/products"
class="side-link"
>
▣ Products
</a>

<a
href="/admin/orders"
class="side-link"
>
▤ Orders
</a>

<a
href="/admin/customers"
class="side-link"
>
♙ Customers
</a>

<a
href="/admin/settings"
class="side-link"
>
⚙ Settings
</a>

<a
href="/"
class="side-link"
>
↗ View Store
</a>

<a
href="/logout"
class="side-link"
>
⇥ Logout
</a>

</aside>

<main class="admin-main">

"""


ADMIN_LAYOUT_END = """

</main>

</div>

"""


@app.route("/admin")
@admin_required
def admin():

    db = get_db()


    products = db.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]


    customers = db.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE role='customer'
        """
    ).fetchone()[0]


    orders_count = db.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]


    revenue = db.execute(
        """
        SELECT COALESCE(SUM(total),0)
        FROM orders
        """
    ).fetchone()[0]


    orders = db.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()


    db.close()


    page = ADMIN_LAYOUT_START + """

    <div class="admin-header">

    <div>

    <h1>
    Dashboard
    </h1>

    <p class="muted">
    Full store administration
    </p>

    </div>

    <div>
    ● {{ user['name'] }}
    </div>

    </div>


    <div class="stats">

    <div class="stat glass">

    Revenue

    <b>
    ${{ "%.2f"|format(revenue) }}
    </b>

    </div>


    <div class="stat glass">

    Orders

    <b>
    {{ orders_count }}
    </b>

    </div>


    <div class="stat glass">

    Customers

    <b>
    {{ customers }}
    </b>

    </div>


    <div class="stat glass">

    Products

    <b>
    {{ products }}
    </b>

    </div>

    </div>


    <div class="admin-card glass">

    <h2>
    Recent Orders
    </h2>

    {% for order in orders %}

    <div class="order glass">

    <b>
    #{{ order['id'] }}
    -
    {{ order['customer_name'] }}
    </b>

    <span style="float:right">

    ${{ "%.2f"|format(order['total']) }}

    </span>

    <br>

    <span class="muted">

    {{ order['status'] }}

    </span>

    </div>

    {% endfor %}

    </div>

    """ + ADMIN_LAYOUT_END


    return render_template_string(

        BASE,

        content=render_template_string(
            page,
            user=current_user(),
            products=products,
            customers=customers,
            orders_count=orders_count,
            revenue=revenue,
            orders=orders
        ),

        settings=get_settings()

    )


# ============================================================
# ADMIN PRODUCTS
# ============================================================

@app.route("/admin/products")
@admin_required
def admin_products():

    db = get_db()

    products = db.execute(
        """
        SELECT *
        FROM products
        ORDER BY id DESC
        """
    ).fetchall()

    db.close()


    page = ADMIN_LAYOUT_START + """

    <div class="admin-header">

    <h1>
    Products
    </h1>

    </div>


    <div class="admin-card glass">

    <table>

    <tr>

    <th>Name</th>

    <th>Category</th>

    <th>Price</th>

    <th>Stock</th>

    <th>Active</th>

    <th>Action</th>

    </tr>


    {% for p in products %}

    <tr>

    <td>
    {{ p['name'] }}
    </td>

    <td>
    {{ p['category'] }}
    </td>

    <td>
    ${{ "%.2f"|format(p['price']) }}
    </td>

    <td>
    {{ p['stock'] }}
    </td>

    <td>
    {{ p['active'] }}
    </td>

    <td>

    <form
    method="POST"
    action="/admin/products/delete/{{ p['id'] }}"
    onsubmit="return confirm('Delete this product?')"
    >

    <button class="table-button">
    Delete
    </button>

    </form>

    </td>

    </tr>

    {% endfor %}

    </table>

    </div>


    <div class="form-card glass">

    <h2>
    Add Product
    </h2>

    <form
    method="POST"
    action="/admin/products/save"
    >

    <div class="form-grid">

    <label class="field">

    Product Name

    <input
    name="name"
    required
    >

    </label>


    <label class="field">

    Slug

    <input
    name="slug"
    required
    >

    </label>


    <label class="field">

    Category

    <input
    name="category"
    required
    >

    </label>


    <label class="field">

    Price

    <input
    name="price"
    type="number"
    step="0.01"
    required
    >

    </label>


    <label class="field">

    Stock

    <input
    name="stock"
    type="number"
    required
    >

    </label>


    <label class="field">

    Image URL

    <input
    name="image"
    >

    </label>


    <label class="field full">

    Description

    <textarea
    name="description"
    ></textarea>

    </label>

    </div>


    <label>

    <input
    type="checkbox"
    name="featured"
    >

    Featured Product

    </label>

    <br><br>


    <button
    class="btn primary"
    >
    Add Product
    </button>

    </form>

    </div>

    """ + ADMIN_LAYOUT_END


    return render_template_string(

        BASE,

        content=render_template_string(
            page,
            products=products
        ),

        settings=get_settings()

    )


@app.route(
    "/admin/products/save",
    methods=["POST"]
)
@admin_required
def save_product():

    db = get_db()


    name = request.form["name"]

    slug = request.form["slug"]

    category = request.form["category"]

    description = request.form.get(
        "description",
        ""
    )

    image = request.form.get(
        "image",
        ""
    )

    price = float(
        request.form["price"]
    )

    stock = int(
        request.form["stock"]
    )

    featured = 1 if request.form.get(
        "featured"
    ) else 0


    db.execute(
        """
        INSERT INTO products

        (
            name,
            slug,
            category,
            description,
            image,
            price,
            stock,
            featured,
            active,
            created_at
        )

        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,

        (
            name,
            slug,
            category,
            description,
            image,
            price,
            stock,
            featured,
            1,
            datetime.utcnow().isoformat()
        )
    )


    db.commit()

    db.close()


    return redirect("/admin/products")


@app.route(
    "/admin/products/delete/<int:product_id>",
    methods=["POST"]
)
@admin_required
def delete_product(product_id):

    db = get_db()

    db.execute(
        """
        DELETE FROM products
        WHERE id=?
        """,
        (product_id,)
    )

    db.commit()

    db.close()

    return redirect("/admin/products")


# ============================================================
# ADMIN ORDERS
# ============================================================

@app.route("/admin/orders")
@admin_required
def admin_orders():

    db = get_db()

    orders = db.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        """
    ).fetchall()

    db.close()


    page = ADMIN_LAYOUT_START + """

    <div class="admin-header">

    <h1>
    Orders
    </h1>

    </div>


    <div class="admin-card glass">

    <table>

    <tr>

    <th>Order</th>

    <th>Customer</th>

    <th>Total</th>

    <th>Status</th>

    <th>Payment</th>

    <th>Update</th>

    </tr>


    {% for order in orders %}

    <tr>

    <td>
    #{{ order['id'] }}
    </td>

    <td>

    {{ order['customer_name'] }}

    <br>

    <span class="muted">
    {{ order['customer_email'] }}
    </span>

    </td>

    <td>
    ${{ "%.2f"|format(order['total']) }}
    </td>

    <td>
    {{ order['status'] }}
    </td>

    <td>
    {{ order['payment_status'] }}
    </td>

    <td>

    <form
    method="POST"
    action="/admin/orders/{{ order['id'] }}"
    >

    <select name="status">

    <option>Pending</option>

    <option>Processing</option>

    <option>Shipped</option>

    <option>Delivered</option>

    <option>Cancelled</option>

    </select>


    <select name="payment_status">

    <option>Unpaid</option>

    <option>Paid</option>

    <option>Refunded</option>

    </select>


    <button class="table-button">
    Save
    </button>

    </form>

    </td>

    </tr>

    {% endfor %}

    </table>

    </div>

    """ + ADMIN_LAYOUT_END


    return render_template_string(

        BASE,

        content=render_template_string(
            page,
            orders=orders
        ),

        settings=get_settings()

    )


@app.route(
    "/admin/orders/<int:order_id>",
    methods=["POST"]
)
@admin_required
def update_order(order_id):

    status = request.form["status"]

    payment = request.form[
        "payment_status"
    ]


    db = get_db()

    db.execute(
        """
        UPDATE orders

        SET
        status=?,
        payment_status=?

        WHERE id=?
        """,

        (
            status,
            payment,
            order_id
        )
    )

    db.commit()

    db.close()


    return redirect("/admin/orders")


# ============================================================
# ADMIN CUSTOMERS
# ============================================================

@app.route("/admin/customers")
@admin_required
def admin_customers():

    db = get_db()

    users = db.execute(
        """
        SELECT *
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    db.close()


    page = ADMIN_LAYOUT_START + """

    <div class="admin-header">

    <h1>
    Customers
    </h1>

    </div>


    <div class="admin-card glass">

    <table>

    <tr>

    <th>Name</th>

    <th>Email</th>

    <th>Role</th>

    <th>Active</th>

    <th>Change Role</th>

    </tr>


    {% for user in users %}

    <tr>

    <td>
    {{ user['name'] }}
    </td>

    <td>
    {{ user['email'] }}
    </td>

    <td>
    {{ user['role'] }}
    </td>

    <td>
    {{ user['active'] }}
    </td>

    <td>

    <form
    method="POST"
    action="/admin/customers/{{ user['id'] }}/role"
    >

    <select name="role">

    <option
    value="customer"
    >
    Customer
    </option>

    <option
    value="admin"
    >
    Admin
    </option>

    </select>


    <button class="table-button">
    Change
    </button>

    </form>

    </td>

    </tr>

    {% endfor %}

    </table>

    </div>

    """ + ADMIN_LAYOUT_END


    return render_template_string(

        BASE,

        content=render_template_string(
            page,
            users=users
        ),

        settings=get_settings()

    )


@app.route(
    "/admin/customers/<int:user_id>/role",
    methods=["POST"]
)
@admin_required
def change_role(user_id):

    role = request.form["role"]


    if role not in (
        "customer",
        "admin"
    ):

        abort(400)


    db = get_db()

    db.execute(
        """
        UPDATE users

        SET role=?

        WHERE id=?
        """,

        (
            role,
            user_id
        )
    )

    db.commit()

    db.close()


    return redirect("/admin/customers")


# ============================================================
# ADMIN SETTINGS
# ============================================================

@app.route(
    "/admin/settings",
    methods=["GET", "POST"]
)
@admin_required
def admin_settings():

    db = get_db()


    if request.method == "POST":

        store_name = request.form[
            "store_name"
        ]

        hero_title = request.form[
            "hero_title"
        ]

        hero_text = request.form[
            "hero_text"
        ]


        values = {

            "store_name":
            store_name,

            "hero_title":
            hero_title,

            "hero_text":
            hero_text

        }


        for key, value in values.items():

            db.execute(
                """
                INSERT INTO settings
                (key,value)

                VALUES (?,?)

                ON CONFLICT(key)
                DO UPDATE SET
                value=excluded.value
                """,

                (
                    key,
                    value
                )
            )


        db.commit()

        flash(
            "Store settings updated."
        )


    db.close()


    settings = get_settings()


    page = ADMIN_LAYOUT_START + """

    <div class="admin-header">

    <h1>
    Store Settings
    </h1>

    </div>


    <div class="form-card glass">

    <form method="POST">

    <label class="field">

    Store Name

    <input
    name="store_name"
    value="{{ settings['store_name'] }}"
    >

    </label>


    <label class="field">

    Hero Title

    <input
    name="hero_title"
    value="{{ settings['hero_title'] }}"
    >

    </label>


    <label class="field">

    Hero Description

    <textarea
    name="hero_text"
    >{{ settings['hero_text'] }}</textarea>

    </label>


    <button
    class="btn primary"
    >
    Save Settings
    </button>

    </form>

    </div>

    """ + ADMIN_LAYOUT_END


    return render_template_string(

        BASE,

        content=render_template_string(
            page,
            settings=settings
        ),

        settings=settings

    )


# ============================================================
# ERROR
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return render_template_string(

        BASE,

        content="""

        <div class="auth-wrapper">

        <div class="auth glass">

        <h1>
        403
        </h1>

        <p>
        Admin access required.
        </p>

        <a
        class="btn primary"
        href="/"
        >
        Back to Store
        </a>

        </div>

        </div>

        """,

        settings=get_settings()

    ), 403


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
  )
