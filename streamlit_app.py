import streamlit as st
import sqlite3
import hashlib
import uuid
import datetime
import pandas as pd
from threading import Lock
import os
import time

# Set page configuration
st.set_page_config(page_title="Code & Thread Shop - Premium", layout="wide", initial_sidebar_state="expanded")

DB_NAME = 'tshirt_shop_premium.db'

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- DATABASE INITIALIZATION ---
def initialize_database(target_db_path):
    if os.path.exists(target_db_path):
        os.remove(target_db_path)
    conn = sqlite3.connect(target_db_path, check_same_thread=False, timeout=60)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    with conn: 
        c.executescript('''
            CREATE TABLE USERS (email TEXT PRIMARY KEY, username TEXT, password_hash TEXT, role TEXT, profile_pic_url TEXT, birthday TEXT);
            CREATE TABLE PRODUCTS (product_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, category TEXT, price REAL, cost REAL, stock INTEGER, image_url TEXT);
            CREATE TABLE ORDERS (order_id TEXT PRIMARY KEY, email TEXT, order_date TEXT, total_amount REAL, total_cost REAL, total_profit REAL, status TEXT, full_name TEXT, address TEXT, city TEXT, zip_code TEXT);
            CREATE TABLE ORDER_ITEMS (item_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, product_id INTEGER, size TEXT, quantity INTEGER, unit_price REAL, unit_cost REAL);
            CREATE TABLE DISCOUNTS (code TEXT PRIMARY KEY, discount_type TEXT, value REAL, is_active INTEGER);
            CREATE TABLE DEFECTS (defect_id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, defect_date TEXT, quantity INTEGER, reason TEXT);
        ''')
        # Seed Data
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", ('admin@shop.com', 'Admin User', hash_password('admin'), 'admin', 'https://placehold.co/100', '1990-01-01'))
        c.execute("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('Vintage Coding Tee', 'Cotton t-shirt.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'))
        c.execute("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('Python Logo Hoodie', 'Warm hoodie.', 'Hoodie', 55.00, 25.00, 48, 'https://placehold.co/400x400/FFD700/000000?text=Python+Hoodie'))
        c.execute("INSERT INTO DEFECTS (product_id, defect_date, quantity, reason) VALUES (1, '2023-10-01', 5, 'Printing Error')")

class DBManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def query(self, q, p=(), commit=False):
        with self._lock:
            c = self._conn.cursor()
            res = c.execute(q, p)
            if commit: self._conn.commit()
            return res.fetchall()

    def query_df(self, q, p=()):
        with self._lock: return pd.read_sql_query(q, self._conn, params=p)

@st.cache_resource
def get_db():
    if not os.path.exists(DB_NAME): initialize_database(DB_NAME)
    return DBManager(DB_NAME)

db = get_db()

# --- ADMIN FUNCTIONS ---
def admin_analytics():
    st.subheader("📊 Sales Analytics")
    df = db.query_df("SELECT * FROM ORDERS")
    if df.empty:
        st.info("No sales recorded."); return
    c1, c2 = st.columns(2)
    c1.metric("Revenue", f"${df['total_amount'].sum():.2f}")
    c2.metric("Profit", f"${df['total_profit'].sum():.2f}")
    df['date'] = pd.to_datetime(df['order_date']).dt.date
    st.line_chart(df.groupby('date').sum()[['total_amount', 'total_profit']])

def admin_defects():
    st.subheader("⚠️ Quality Control")
    df = db.query_df("SELECT D.*, P.name FROM DEFECTS D JOIN PRODUCTS P ON D.product_id = P.product_id")
    if not df.empty:
        st.bar_chart(df.groupby('reason')['quantity'].sum())
        st.dataframe(df)

def dashboard_page():
    st.title("🛡️ Admin Panel")
    user = st.session_state['user_details']
    if user['role'] != 'admin':
        st.error("Unauthorized"); return
    t1, t2, t3 = st.tabs(["Analytics", "Defects", "Inventory"])
    with t1: admin_analytics()
    with t2: admin_defects()
    with t3: st.dataframe(db.query_df("SELECT * FROM PRODUCTS"))

# --- STOREFRONT ---
def shop_page():
    st.title("The Shop")
    # --- Category Filter ---
    categories = ["All"] + [r['category'] for r in db.query("SELECT DISTINCT category FROM PRODUCTS")]
    selected_cat = st.selectbox("Filter Products", categories)
    
    q = "SELECT * FROM PRODUCTS" if selected_cat == "All" else "SELECT * FROM PRODUCTS WHERE category=?"
    p = () if selected_cat == "All" else (selected_cat,)
    prods = db.query(q, p)

    cols = st.columns(3)
    for i, p in enumerate(prods):
        with cols[i % 3]:
            st.image(p['image_url'])
            st.subheader(p['name'])
            if st.button(f"View - ${p['price']}", key=p['product_id']):
                st.session_state['selected_product_id'] = p['product_id']
                st.session_state['page'] = 'product_detail'
                st.rerun()

def product_detail_page():
    pid = st.session_state.get('selected_product_id')
    res = db.query("SELECT * FROM PRODUCTS WHERE product_id=?", (pid,)) if pid else None
    if not res: st.session_state['page'] = 'shop'; st.rerun()
    p = res[0]
    
    col1, col2 = st.columns(2)
    with col1: st.image(p['image_url'])
    with col2:
        st.title(p['name'])
        st.write(p['description'])
        # --- Size & Qty ---
        sz = st.selectbox("Size", ["S", "M", "L", "XL"])
        qt = st.number_input("Quantity", 1, p['stock'], 1)
        if st.button("Add to Cart"):
            st.session_state['cart'].append({'name': p['name'], 'price': p['price'], 'size': sz, 'qty': qt, 'total': p['price']*qt})
            st.success("Added!")

def checkout_page():
    st.title("Your Cart")
    if not st.session_state['cart']: st.warning("Cart is empty"); return
    df = pd.DataFrame(st.session_state['cart'])
    st.table(df)
    if st.button("Place Order"):
        st.balloons(); st.session_state['cart'] = []; st.success("Done!"); time.sleep(1); st.session_state['page'] = 'shop'; st.rerun()

# --- SIGN UP & LOGIN ---
def signup_page():
    st.title("📝 Create Account")
    with st.form("signup"):
        email = st.text_input("Email")
        user = st.text_input("Username")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Register"):
            if not email or not pw: st.error("Fields required")
            else:
                db.query("INSERT INTO USERS (email, username, password_hash, role) VALUES (?, ?, ?, ?)", (email, user, hash_password(pw), 'customer'), commit=True)
                st.success("Account created! Log in now."); st.session_state['page'] = 'login'; st.rerun()
    if st.button("Back to Login"): st.session_state['page'] = 'login'; st.rerun()

def login_page():
    st.title("🔐 Login")
    email = st.text_input("Email")
    pw = st.text_input("Password", type="password")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("Login"):
            res = db.query("SELECT * FROM USERS WHERE email=?", (email,))
            if res and res[0]['password_hash'] == hash_password(pw):
                st.session_state.update({'logged_in': True, 'user_details': dict(res[0]), 'page': 'shop'})
                st.rerun()
            else: st.error("Failed")
    with c2:
        if st.button("New User? Create Account"):
            st.session_state['page'] = 'signup'; st.rerun()

# --- APP START ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []})

if st.session_state['logged_in']:
    u = st.session_state['user_details']
    with st.sidebar:
        st.write(f"User: {u['username']}")
        if st.button("Shop"): st.session_state['page'] = 'shop'; st.rerun()
        if st.button("Cart"): st.session_state['page'] = 'checkout'; st.rerun()
        if u['role'] == 'admin' and st.button("🛡️ Admin Dashboard"): st.session_state['page'] = 'dashboard'; st.rerun()
        if st.button("Logout"): st.session_state.clear(); st.rerun()

    p = st.session_state['page']
    if p == 'dashboard': dashboard_page()
    elif p == 'product_detail': product_detail_page()
    elif p == 'checkout': checkout_page()
    else: shop_page()
else:
    if st.session_state.get('page') == 'signup': signup_page()
    else: login_page()
