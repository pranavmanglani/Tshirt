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

# --- DATABASE INITIALIZATION (WITH FULL ANALYTICS DATA) ---
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
        # Admin & Users
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", ('admin@shop.com', 'Admin User', hash_password('admin'), 'admin', 'https://placehold.co/100', '1990-01-01'))
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", ('customer1@email.com', 'Customer One', hash_password('customer1'), 'customer', 'https://placehold.co/100', '1995-05-15'))
        # Products
        c.execute("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('Vintage Coding Tee', 'Cotton t-shirt.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'))
        c.execute("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('Python Logo Hoodie', 'Warm hoodie.', 'Hoodie', 55.00, 25.00, 48, 'https://placehold.co/400x400/FFD700/000000?text=Python+Hoodie'))
        # Sample Defects for Charts
        c.execute("INSERT INTO DEFECTS (product_id, defect_date, quantity, reason) VALUES (1, '2023-10-01', 5, 'Printing Error')")
        c.execute("INSERT INTO DEFECTS (product_id, defect_date, quantity, reason) VALUES (2, '2023-10-02', 2, 'Stitching Issue')")

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

# --- ADMIN DASHBOARD TABS ---

def admin_analytics():
    st.subheader("📊 Sales & Financials")
    df = db.query_df("SELECT * FROM ORDERS")
    if df.empty:
        st.info("No sales data."); return
    c1, c2, c3 = st.columns(3)
    c1.metric("Revenue", f"${df['total_amount'].sum():.2f}")
    c2.metric("Profit", f"${df['total_profit'].sum():.2f}")
    c3.metric("Orders", len(df))
    df['date'] = pd.to_datetime(df['order_date']).dt.date
    st.line_chart(df.groupby('date').sum()[['total_amount', 'total_profit']])

def admin_defects():
    st.subheader("⚠️ Quality Control Analysis")
    df = db.query_df("SELECT D.*, P.name FROM DEFECTS D JOIN PRODUCTS P ON D.product_id = P.product_id")
    if not df.empty:
        st.bar_chart(df.groupby('reason')['quantity'].sum())
        st.dataframe(df)
    else: st.info("No defects recorded.")

def dashboard_page():
    st.title("🛡️ Admin Command Center")
    user = st.session_state['user_details']
    
    if user['role'] != 'admin':
        st.error("Access Denied"); return

    tabs = st.tabs(["Analytics", "Defects & QC", "Inventory Management"])
    with tabs[0]: admin_analytics()
    with tabs[1]: admin_defects()
    with tabs[2]:
        st.subheader("📦 Product Stock")
        st.dataframe(db.query_df("SELECT * FROM PRODUCTS"))

# --- STOREFRONT ---

def shop_page():
    st.title("The Shop")
    
    # --- NEW: Filter Option ---
    categories = ["All"] + [r['category'] for r in db.query("SELECT DISTINCT category FROM PRODUCTS")]
    selected_cat = st.selectbox("Filter by Category", categories)
    
    if selected_cat == "All":
        prods = db.query("SELECT * FROM PRODUCTS")
    else:
        prods = db.query("SELECT * FROM PRODUCTS WHERE category=?", (selected_cat,))

    cols = st.columns(3)
    for i, p in enumerate(prods):
        with cols[i % 3]:
            st.image(p['image_url'])
            st.subheader(p['name'])
            st.write(f"*{p['category']}*")
            if st.button(f"View details - ${p['price']}", key=p['product_id']):
                st.session_state['selected_product_id'] = p['product_id']
                st.session_state['page'] = 'product_detail'
                st.rerun()

def product_detail_page():
    pid = st.session_state.get('selected_product_id')
    res = db.query("SELECT * FROM PRODUCTS WHERE product_id=?", (pid,)) if pid else None
    if not res:
        st.error("Product not found"); st.session_state['page'] = 'shop'; return
    p = res[0]
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.image(p['image_url'], use_container_width=True)
    with col2:
        st.title(p['name'])
        st.write(f"**Category:** {p['category']}")
        st.write(p['description'])
        st.subheader(f"${p['price']}")
        
        # --- NEW: Product Details (Size & Qty) ---
        size = st.selectbox("Select Size", ["S", "M", "L", "XL", "XXL"])
        qty = st.number_input("Quantity", min_value=1, max_value=p['stock'], value=1)
        
        if st.button("Add to Cart"):
            st.session_state['cart'].append({
                'id': p['product_id'], 
                'name': p['name'], 
                'price': p['price'], 
                'size': size, 
                'qty': qty,
                'total': p['price'] * qty
            })
            st.success(f"Added {qty} {p['name']} to cart!")

def checkout_page():
    st.title("Checkout")
    if not st.session_state['cart']:
        st.warning("Empty cart"); return
    
    df_cart = pd.DataFrame(st.session_state['cart'])
    st.table(df_cart[['name', 'size', 'qty', 'price', 'total']])
    
    grand_total = df_cart['total'].sum()
    st.write(f"### Grand Total: ${grand_total:.2f}")

    if st.button("Place Order", type="primary"):
        st.balloons()
        st.session_state['cart'] = []
        st.success("Order Complete!")

# --- NEW: Sign Up Page ---
def signup_page():
    st.title("Create Account")
    with st.form("signup_form"):
        new_email = st.text_input("Email")
        new_user = st.text_input("Username")
        new_pw = st.text_input("Password", type="password")
        confirm_pw = st.text_input("Confirm Password", type="password")
        submit = st.form_submit_button("Sign Up")
        
        if submit:
            if new_pw != confirm_pw:
                st.error("Passwords do not match.")
            elif not new_email or not new_pw or not new_user:
                st.error("All fields are required.")
            else:
                existing = db.query("SELECT * FROM USERS WHERE email=?", (new_email,))
                if existing:
                    st.error("User already exists.")
                else:
                    db.query("INSERT INTO USERS (email, username, password_hash, role) VALUES (?, ?, ?, ?)", 
                             (new_email, new_user, hash_password(new_pw), 'customer'), commit=True)
                    st.success("Account created! Please log in.")
                    st.session_state['page'] = 'login'
                    st.rerun()
    if st.button("Back to Login"):
        st.session_state['page'] = 'login'
        st.rerun()

def login_page():
    st.title("Login")
    email = st.text_input("Email")
    pw = st.text_input("Password", type="password")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Login"):
            res = db.query("SELECT * FROM USERS WHERE email=?", (email,))
            if res and res[0]['password_hash'] == hash_password(pw):
                st.session_state.update({'logged_in': True, 'user_details': dict(res[0]), 'page': 'shop'})
                st.rerun()
            else: st.error("Wrong credentials")
    with col2:
        if st.button("Sign Up"):
            st.session_state['page'] = 'signup'
            st.rerun()

# --- ROUTING ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []})

if st.session_state['logged_in']:
    user = st.session_state['user_details']
    with st.sidebar:
        st.write(f"Logged in: {user['username']}")
        if st.button("Shop"): st.session_state['page'] = 'shop'; st.rerun()
        if st.button("Cart/Checkout"): st.session_state['page'] = 'checkout'; st.rerun()
        if user['role'] == 'admin':
            if st.button("🛡️ Admin Dashboard"): 
                st.session_state['page'] = 'dashboard'; st.rerun()
        if st.button("Logout"): st.session_state.clear(); st.rerun()

    page = st.session_state['page']
    if page == 'dashboard': dashboard_page()
    elif page == 'product_detail': product_detail_page()
    elif page == 'checkout': checkout_page()
    else: shop_page()
else:
    if st.session_state.get('page') == 'signup':
        signup_page()
    else:
        login_page()
