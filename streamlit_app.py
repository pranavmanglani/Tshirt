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
st.set_page_config(page_title="Code & Thread Shop - Premium", layout="wide", initial_sidebar_state="expanded") [cite: 1]

# --- Constants and Configuration ---
DB_NAME = 'tshirt_shop_premium.db' [cite: 1]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest() [cite: 1]

# --- DATABASE INITIALIZATION ---
def initialize_database(target_db_path):
    """Creates the database and initializes schema and sample data."""
    conn = None
    try:
        if os.path.exists(target_db_path):
             os.remove(target_db_path) [cite: 2]
             
        conn = sqlite3.connect(target_db_path, check_same_thread=False, timeout=60) [cite: 2]
        conn.row_factory = sqlite3.Row [cite: 2]
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
                CREATE TABLE DEFECTS (
                    defect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER,
                    defect_date TEXT,
                    quantity INTEGER,
                    reason TEXT,
                    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
                );
            ''' [cite: 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
            c.executescript(schema_script) [cite: 17]

            # Initial Data
            c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", 
                      ('admin@shop.com', 'admin', hash_password('admin'), 'admin', 'https://placehold.co/100x100/1E88E5/FFFFFF?text=A', '1990-01-01')) [cite: 17]
            
            products_data = [
                ('Vintage Coding Tee', 'A comfortable cotton t-shirt for developers.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'),
                ('Python Logo Hoodie', 'Warm hoodie featuring the Python logo.', 'Hoodie', 55.00, 25.00, 48, 'https://placehold.co/400x400/FFD700/000000?text=Python+Hoodie'),
                ('JavaScript Mug', 'A large coffee mug for late-night coding sessions.', 'Accessory', 15.00, 5.00, 198, 'https://placehold.co/400x400/76FF03/000000?text=JS+Mug')
            ] [cite: 19, 20]
            c.executemany("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", products_data) [cite: 21]
            
            c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('SAVE10', 'percent', 10.0, 1)) [cite: 21]

    except Exception as e:
        if os.path.exists(target_db_path):
             os.remove(target_db_path) [cite: 34]
        raise Exception(f"CRITICAL DB INIT ERROR: {e}")
    finally:
        if conn:
            conn.close() [cite: 34]

# --- Database Management Class ---
class DBManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock() [cite: 34]
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60) [cite: 35]
        self._conn.row_factory = sqlite3.Row [cite: 35]

    def execute_query(self, query, params=(), commit=False):
        with self._lock:
            c = self._conn.cursor() [cite: 36]
            c.execute(query, params) [cite: 37]
            if commit: self._conn.commit()
            return c

    def fetch_query(self, query, params=()):
        with self._lock:
            c = self._conn.cursor() [cite: 38]
            c.execute(query, params) [cite: 39]
            return c.fetchall() [cite: 39]

    def fetch_query_df(self, query, params=()):
        with self._lock:
            return pd.read_sql_query(query, self._conn, params=params) [cite: 40]

@st.cache_resource
def get_db_manager():
    if not os.path.exists(DB_NAME):
        initialize_database(DB_NAME) [cite: 42]
    return DBManager(DB_NAME) [cite: 42]

db_manager = get_db_manager() [cite: 42]

# --- Logic and Helpers ---
def get_product_details(product_id):
    products = db_manager.fetch_query("SELECT * FROM PRODUCTS WHERE product_id = ?", (product_id,)) [cite: 48]
    return dict(products[0]) if products else None [cite: 48]

def place_order(email, cart_items, final_amount, full_name, address, city, zip_code):
    order_id = str(uuid.uuid4()) [cite: 51]
    order_date = datetime.datetime.now().isoformat() [cite: 51]
    total_cost = sum(item['cost'] * item['quantity'] for item in cart_items)
    total_profit = final_amount - total_cost

    try:
        db_manager.execute_query("INSERT INTO ORDERS (order_id, email, order_date, total_amount, total_cost, total_profit, status, full_name, address, city, zip_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, email, order_date, final_amount, total_cost, total_profit, 'Processing', full_name, address, city, zip_code), commit=True) [cite: 61]
        
        for item in cart_items:
            db_manager.execute_query("INSERT INTO ORDER_ITEMS (order_id, product_id, size, quantity, unit_price, unit_cost) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, item['product_id'], item['size'], item['quantity'], item['price'], item['cost']), commit=True) [cite: 60]
            db_manager.execute_query("UPDATE PRODUCTS SET stock = stock - ? WHERE product_id = ?", (item['quantity'], item['product_id']), commit=True) [cite: 58]
        return True, order_id
    except Exception as e:
        return False, str(e)

# --- Pages ---
def login_page():
    st.title("Code & Thread Shop - Login") [cite: 62]
    with st.form("login"):
        email = st.text_input("Email") [cite: 63]
        pw = st.text_input("Password", type="password") [cite: 63]
        if st.form_submit_button("Login"):
            res = db_manager.fetch_query("SELECT * FROM USERS WHERE email = ?", (email,)) [cite: 43]
            if res and res[0]['password_hash'] == hash_password(pw):
                st.session_state.update({'logged_in': True, 'email': email, 'username': res[0]['username'], 'user_details': dict(res[0]), 'page': 'shop'}) [cite: 64, 65]
                st.rerun()
            else: st.error("Invalid credentials") [cite: 65]

def shop_page():
    st.title("Shop Catalog") [cite: 72]
    products = db_manager.fetch_query_df("SELECT * FROM PRODUCTS WHERE stock > 0") [cite: 72]
    cols = st.columns(3)
    for i, row in products.iterrows():
        with cols[i % 3]:
            st.image(row['image_url']) [cite: 84]
            st.write(f"**{row['name']}**") [cite: 84]
            if st.button(f"View ${row['price']}", key=row['product_id']):
                st.session_state['selected_product_id'] = row['product_id'] [cite: 85]
                st.session_state['page'] = 'product_detail' [cite: 85]
                st.rerun()

def product_detail_page():
    pid = st.session_state.get('selected_product_id')
    product = get_product_details(pid) if pid else None [cite: 86]
    
    if not product:
        st.error("Product not found") [cite: 86]
        if st.button("Back"): st.session_state['page'] = 'shop'; st.rerun()
        return

    st.title(product['name']) [cite: 87]
    st.image(product['image_url'], width=300) [cite: 87]
    qty = st.number_input("Quantity", 1, product['stock'], 1) [cite: 93]
    
    if st.button("Add to Cart"):
        item = {'product_id': product['product_id'], 'name': product['name'], 'quantity': qty, 'price': product['price'], 'cost': product['cost'], 'total': qty * product['price'], 'size': 'M'} [cite: 95]
        st.session_state['cart'].append(item) [cite: 97]
        st.toast("Added!") [cite: 97]

def checkout_page():
    st.title("Checkout") [cite: 98]
    if not st.session_state['cart']: 
        st.warning("Empty cart"); return [cite: 98]
    
    st.table(st.session_state['cart']) [cite: 99]
    total = sum(i['total'] for i in st.session_state['cart'])
    
    if st.button(f"Pay ${total:.2f}"):
        success, msg = place_order(st.session_state['email'], st.session_state['cart'], total, "User", "123 St", "City", "12345") [cite: 114]
        if success:
            st.session_state['cart'] = [] [cite: 116]
            st.success("Order Placed!") [cite: 116]
            st.balloons() [cite: 116]

# --- Main App ---
def main():
    if 'logged_in' not in st.session_state:
        st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []}) [cite: 151, 152]

    if st.session_state['logged_in']:
        with st.sidebar:
            if st.button("Shop"): st.session_state['page'] = 'shop'; st.rerun() [cite: 153]
            if st.button("Checkout"): st.session_state['page'] = 'checkout'; st.rerun() [cite: 155]
            if st.button("Logout"): st.session_state.clear(); st.rerun() [cite: 156]

        pg = st.session_state['page']
        if pg == 'shop': shop_page()
        elif pg == 'product_detail': product_detail_page()
        elif pg == 'checkout': checkout_page()
    else:
        login_page()

if __name__ == "__main__":
    main()
