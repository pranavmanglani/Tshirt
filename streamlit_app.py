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

# --- Constants and Configuration ---
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
        schema_script = '''
            CREATE TABLE USERS (email TEXT PRIMARY KEY, username TEXT, password_hash TEXT, role TEXT, profile_pic_url TEXT, birthday TEXT);
            CREATE TABLE PRODUCTS (product_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, category TEXT, price REAL, cost REAL, stock INTEGER, image_url TEXT);
            CREATE TABLE ORDERS (order_id TEXT PRIMARY KEY, email TEXT, order_date TEXT, total_amount REAL, total_cost REAL, total_profit REAL, status TEXT, full_name TEXT, address TEXT, city TEXT, zip_code TEXT, FOREIGN KEY (email) REFERENCES USERS(email));
            CREATE TABLE ORDER_ITEMS (item_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, product_id INTEGER, size TEXT, quantity INTEGER, unit_price REAL, unit_cost REAL, FOREIGN KEY (order_id) REFERENCES ORDERS(order_id), FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id));
            CREATE TABLE DISCOUNTS (code TEXT PRIMARY KEY, discount_type TEXT, value REAL, is_active INTEGER);
            CREATE TABLE DEFECTS (defect_id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, defect_date TEXT, quantity INTEGER, reason TEXT, FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id));
        '''
        c.executescript(schema_script)

        # Initial Data
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", ('admin@shop.com', 'admin', hash_password('admin'), 'admin', 'https://placehold.co/100x100/1E88E5/FFFFFF?text=A', '1990-01-01'))
        
        products_data = [
            ('Vintage Coding Tee', 'Cotton t-shirt for devs.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'),
            ('Python Logo Hoodie', 'Warm hoodie.', 'Hoodie', 55.00, 25.00, 48, 'https://placehold.co/400x400/FFD700/000000?text=Python+Hoodie')
        ]
        c.executemany("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", products_data)
        c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('SAVE10', 'percent', 10.0, 1))

class DBManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        self._conn.row_factory = sqlite3.Row

    def query(self, query, params=(), commit=False):
        with self._lock:
            c = self._conn.cursor()
            res = c.execute(query, params)
            if commit: self._conn.commit()
            return res.fetchall()

    def query_df(self, query, params=()):
        with self._lock:
            return pd.read_sql_query(query, self._conn, params=params)

@st.cache_resource
def get_db():
    if not os.path.exists(DB_NAME): initialize_database(DB_NAME)
    return DBManager(DB_NAME)

db = get_db()

# --- ORIGINAL ADMIN PAGES ---

def admin_analytics():
    st.header("📊 Sales & Financial Performance")
    df_orders = db.query_df("SELECT * FROM ORDERS")
    if df_orders.empty:
        st.info("No orders yet."); return

    # KPI Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Revenue", f"${df_orders['total_amount'].sum():,.2f}")
    c2.metric("Total Profit", f"${df_orders['total_profit'].sum():,.2f}")
    c3.metric("Order Count", len(df_orders))

    # Line Chart: Revenue Over Time
    df_orders['date'] = pd.to_datetime(df_orders['order_date']).dt.date
    daily = df_orders.groupby('date').sum()[['total_amount', 'total_profit']]
    st.line_chart(daily)

def admin_defects():
    st.header("⚠️ Quality Control")
    df_defects = db.query_df("SELECT D.*, P.name FROM DEFECTS D JOIN PRODUCTS P ON D.product_id = P.product_id")
    if not df_defects.empty:
        st.bar_chart(df_defects, x="reason", y="quantity")
        st.dataframe(df_defects)
    else:
        st.info("No defect data found.")

def dashboard_page():
    st.title("🛡️ Admin Command Center")
    tabs = st.tabs(["Analytics", "Defects & QC", "Product Management"])
    with tabs[0]: admin_analytics()
    with tabs[1]: admin_defects()
    with tabs[2]: st.write("Product management functions would be here.")

# --- SHOP PAGES ---

def shop_page():
    st.title("The Shop")
    df = db.query_df("SELECT * FROM PRODUCTS WHERE stock > 0")
    cols = st.columns(3)
    for i, row in df.iterrows():
        with cols[i % 3]:
            st.image(row['image_url'])
            st.subheader(row['name'])
            if st.button(f"View Details ${row['price']}", key=row['product_id']):
                st.session_state['selected_product_id'] = row['product_id']
                st.session_state['page'] = 'product_detail'
                st.rerun()

def product_detail_page():
    pid = st.session_state.get('selected_product_id')
    res = db.query("SELECT * FROM PRODUCTS WHERE product_id=?", (pid,)) if pid else None
    if not res:
        st.error("Product Not Found"); st.session_state['page'] = 'shop'; return
    
    p = res[0]
    st.title(p['name'])
    st.image(p['image_url'], width=300)
    if st.button("Add to Cart"):
        st.session_state['cart'].append({'id': p['product_id'], 'name': p['name'], 'price': p['price'], 'total': p['price']})
        st.toast("Added!")
        st.session_state['page'] = 'checkout'
        st.rerun()

def checkout_page():
    st.title("Checkout")
    if not st.session_state['cart']:
        st.warning("Empty cart"); 
        if st.button("Back"): st.session_state['page'] = 'shop'; st.rerun()
        return
    
    st.table(st.session_state['cart'])
    if st.button("Complete Purchase"):
        st.success("Order Placed Successfully!")
        st.session_state['cart'] = []
        time.sleep(1)
        st.session_state['page'] = 'shop'
        st.rerun()

def login_page():
    st.title("Login")
    with st.form("l"):
        email = st.text_input("Email")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = db.query("SELECT * FROM USERS WHERE email=?", (email,))
            if res and res[0]['password_hash'] == hash_password(pw):
                st.session_state.update({'logged_in': True, 'user': dict(res[0]), 'page': 'shop'})
                st.rerun()
            else: st.error("Invalid")

# --- MAIN LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []})

if st.session_state['logged_in']:
    u = st.session_state['user']
    with st.sidebar:
        st.write(f"User: {u['username']} ({u['role']})")
        if st.button("Shop"): st.session_state['page'] = 'shop'; st.rerun()
        if st.button("Checkout"): st.session_state['page'] = 'checkout'; st.rerun()
        if u['role'] == 'admin' and st.button("🛡️ Admin Dashboard"):
            st.session_state['page'] = 'dashboard'; st.rerun()
        if st.button("Logout"): st.session_state.clear(); st.rerun()

    p = st.session_state['page']
    if p == 'dashboard': dashboard_page()
    elif p == 'product_detail': product_detail_page()
    elif p == 'checkout': checkout_page()
    else: shop_page()
else:
    login_page()
