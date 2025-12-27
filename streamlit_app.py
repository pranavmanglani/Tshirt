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
    
    conn = sqlite3.connect(target_db_path, check_same_thread=False)
    c = conn.cursor()
    
    with conn:
        c.executescript('''
            CREATE TABLE USERS (email TEXT PRIMARY KEY, username TEXT, password_hash TEXT, role TEXT);
            CREATE TABLE PRODUCTS (product_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, price REAL, cost REAL, stock INTEGER, image_url TEXT);
            CREATE TABLE ORDERS (order_id TEXT PRIMARY KEY, email TEXT, total_amount REAL, total_profit REAL, order_date TEXT);
            CREATE TABLE DEFECTS (defect_id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, quantity INTEGER, reason TEXT, defect_date TEXT);
        ''')
        
        # Add Admin and Products
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?)", ('admin@shop.com', 'Admin User', hash_password('admin'), 'admin'))
        c.execute("INSERT INTO PRODUCTS (name, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?)", 
                  ('Vintage Coding Tee', 'T-Shirt', 25.0, 10.0, 50, 'https://placehold.co/400x400?text=Code+Tee'))
        
        # Sample Defect Data for Dashboard
        c.execute("INSERT INTO DEFECTS (product_id, quantity, reason, defect_date) VALUES (1, 2, 'Printing Error', '2023-10-01')")

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

@st.cache_resource
def get_db():
    if not os.path.exists(DB_NAME): initialize_database(DB_NAME)
    return DBManager(DB_NAME)

db = get_db()

# --- PAGES ---

def dashboard_page():
    st.title("🛡️ Admin Dashboard")
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    orders = db.query("SELECT * FROM ORDERS")
    total_rev = sum(o['total_amount'] for o in orders)
    total_profit = sum(o['total_profit'] for o in orders)
    
    col1.metric("Total Revenue", f"${total_rev:.2f}")
    col2.metric("Total Profit", f"${total_profit:.2f}")
    col3.metric("Total Orders", len(orders))
    
    st.divider()
    
    # Inventory & Defects
    st.subheader("Inventory & Defect Analysis")
    defects_df = pd.read_sql_query("SELECT * FROM DEFECTS", db._conn)
    if not defects_df.empty:
        st.bar_chart(defects_df, x="reason", y="quantity")
    else:
        st.info("No defect data reported yet.")

def shop_page():
    st.title("🛒 Hardware & Threads Shop")
    prods = db.query("SELECT * FROM PRODUCTS")
    cols = st.columns(3)
    for i, p in enumerate(prods):
        with cols[i % 3]:
            st.image(p['image_url'])
            st.subheader(p['name'])
            st.write(f"Price: ${p['price']}")
            if st.button(f"View Details", key=p['product_id']):
                st.session_state['selected_product_id'] = p['product_id']
                st.session_state['page'] = 'product_detail'
                st.rerun()

def product_detail_page():
    pid = st.session_state.get('selected_product_id')
    p = db.query("SELECT * FROM PRODUCTS WHERE product_id=?", (pid,))
    if not p:
        st.error("Select a product first!"); return
    p = p[0]
    st.title(p['name'])
    if st.button("Add to Cart"):
        st.session_state['cart'].append({'id': p['product_id'], 'name': p['name'], 'price': p['price'], 'cost': p['cost']})
        st.success("Added!")

def login_page():
    st.title("🔐 Login")
    email = st.text_input("Email")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        user = db.query("SELECT * FROM USERS WHERE email=?", (email,))
        if user and user[0]['password_hash'] == hash_password(pw):
            st.session_state.update({'logged_in': True, 'user': dict(user[0]), 'page': 'shop'})
            st.rerun()
        else: st.error("Wrong credentials")

# --- MAIN ---
if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []})

if st.session_state['logged_in']:
    user = st.session_state['user']
    with st.sidebar:
        st.write(f"Welcome, **{user['username']}**")
        if st.button("Store"): st.session_state['page'] = 'shop'; st.rerun()
        
        # THE ADMIN BUTTON
        if user['role'] == 'admin':
            if st.button("🛡️ Admin Dashboard"): 
                st.session_state['page'] = 'dashboard'
                st.rerun()
                
        if st.button("Logout"): 
            st.session_state.clear()
            st.rerun()

    page = st.session_state['page']
    if page == 'dashboard': dashboard_page()
    elif page == 'product_detail': product_detail_page()
    else: shop_page()
else:
    login_page()
