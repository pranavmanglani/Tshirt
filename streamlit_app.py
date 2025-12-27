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

# --- STANDALONE DATABASE INITIALIZATION FUNCTION ---
def initialize_database(target_db_path):
    """Creates the database and initializes schema and sample data."""
    conn = None
    try:
        if os.path.exists(target_db_path):
             os.remove(target_db_path)
             
        conn = sqlite3.connect(target_db_path, check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        with conn: 
            schema_script = '''
                CREATE TABLE USERS (
                    email TEXT PRIMARY KEY,
                    username TEXT,
                    password_hash TEXT,
                    role TEXT,
                    profile_pic_url TEXT,
                    birthday TEXT
                );
                CREATE TABLE PRODUCTS (
                    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    description TEXT,
                    category TEXT,
                    price REAL,
                    cost REAL,
                    stock INTEGER,
                    image_url TEXT
                );
                CREATE TABLE ORDERS (
                    order_id TEXT PRIMARY KEY,
                    email TEXT,
                    order_date TEXT,
                    total_amount REAL,
                    total_cost REAL,
                    total_profit REAL,
                    status TEXT,
                    full_name TEXT,
                    address TEXT,
                    city TEXT,
                    zip_code TEXT,
                    FOREIGN KEY (email) REFERENCES USERS(email)
                );
                CREATE TABLE ORDER_ITEMS (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    product_id INTEGER,
                    size TEXT,
                    quantity INTEGER,
                    unit_price REAL,
                    unit_cost REAL,
                    FOREIGN KEY (order_id) REFERENCES ORDERS(order_id),
                    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
                );
                CREATE TABLE DISCOUNTS (
                    code TEXT PRIMARY KEY,
                    discount_type TEXT,
                    value REAL,
                    is_active INTEGER
                );
            '''
            c.executescript(schema_script)
            c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", 
                      ('admin@shop.com', 'admin', hash_password('admin'), 'admin', 'https://placehold.co/100x100/1E88E5/FFFFFF?text=A', '1990-01-01'))
            products_data = [
                ('Vintage Coding Tee', 'Cotton t-shirt.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'),
                ('Python Logo Hoodie', 'Warm hoodie.', 'Hoodie', 55.00, 25.00, 48, 'https://placehold.co/400x400/FFD700/000000?text=Python+Hoodie')
            ]
            c.executemany("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", products_data)
    except Exception as e:
        if os.path.exists(target_db_path):
             os.remove(target_db_path)
        raise e
    finally:
        if conn:
            conn.close()

# --- Database Management Class ---
class DBManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        self._conn.row_factory = sqlite3.Row

    def execute_query(self, query, params=(), commit=False):
        with self._lock:
            c = self._conn.cursor()
            c.execute(query, params)
            if commit: self._conn.commit()
            return c

    def fetch_query(self, query, params=()):
        with self._lock:
            c = self._conn.cursor()
            c.execute(query, params)
            return c.fetchall()

    def fetch_query_df(self, query, params=()):
        with self._lock:
            return pd.read_sql_query(query, self._conn, params=params)

@st.cache_resource
def get_db_manager():
    if not os.path.exists(DB_NAME):
        initialize_database(DB_NAME)
    return DBManager(DB_NAME)

db_manager = get_db_manager()

# --- Helpers ---
def get_product_details(product_id):
    products = db_manager.fetch_query("SELECT * FROM PRODUCTS WHERE product_id = ?", (product_id,))
    return dict(products[0]) if products else None

def place_order(email, cart_items, amount, name, addr, city, zip_code):
    order_id = str(uuid.uuid4())
    date = datetime.datetime.now().isoformat()
    try:
        db_manager.execute_query("INSERT INTO ORDERS VALUES (?, ?, ?, ?, 0, 0, 'Processing', ?, ?, ?, ?)", 
                                (order_id, email, date, amount, name, addr, city, zip_code), commit=True)
        return True, order_id
    except Exception as e:
        return False, str(e)

# --- Pages ---
def login_page():
    st.title("Login")
    with st.form("login"):
        email = st.text_input("Email")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = db_manager.fetch_query("SELECT * FROM USERS WHERE email = ?", (email,))
            if res and res[0]['password_hash'] == hash_password(pw):
                st.session_state.update({'logged_in': True, 'email': email, 'username': res[0]['username'], 'page': 'shop'})
                st.rerun()
            else: st.error("Failed")

def shop_page():
    st.title("Shop")
    products = db_manager.fetch_query_df("SELECT * FROM PRODUCTS")
    cols = st.columns(3)
    for i, row in products.iterrows():
        with cols[i % 3]:
            st.image(row['image_url'])
            if st.button(f"View {row['name']}", key=row['product_id']):
                st.session_state['selected_product_id'] = row['product_id']
                st.session_state['page'] = 'product_detail'
                st.rerun()

def product_detail_page():
    # FIXED: Check if selected_product_id exists before querying [cite: 305, 306]
    pid = st.session_state.get('selected_product_id')
    product = get_product_details(pid) if pid else None
    
    if not product:
        st.warning("Product not found.")
        if st.button("Back"): st.session_state['page'] = 'shop'; st.rerun()
        return

    st.title(product['name'])
    st.image(product['image_url'], width=300)
    if st.button("Add to Cart"):
        st.session_state['cart'].append({'product_id': product['product_id'], 'name': product['name'], 'total': product['price'], 'size': 'M'})
        st.session_state['page'] = 'checkout'
        st.rerun()

def checkout_page():
    st.title("Checkout")
    # FIXED: Clean syntax for empty cart check [cite: 318]
    if not st.session_state.get('cart'):
        st.warning("Your cart is empty.")
        if st.button("Back to Shop"):
            st.session_state['page'] = 'shop'
            st.rerun()
        return

    st.table(st.session_state['cart'])
    if st.button("Pay Now"):
        st.success("Success!")
        st.session_state['cart'] = []

def main():
    if 'logged_in' not in st.session_state:
        st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []})

    if st.session_state['logged_in']:
        pg = st.session_state.get('page', 'shop')
        if pg == 'shop': shop_page()
        elif pg == 'product_detail': product_detail_page()
        elif pg == 'checkout': checkout_page()
    else:
        login_page()

if __name__ == "__main__":
    main()
