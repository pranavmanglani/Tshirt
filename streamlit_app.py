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
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", ('admin@shop.com', 'admin', hash_password('admin'), 'admin', 'https://placehold.co/100x100/1E88E5/FFFFFF?text=A', '1990-01-01'))
        c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", ('customer1@email.com', 'customer1', hash_password('customer1'), 'customer', 'https://placehold.co/100x100/FBC02D/333333?text=C', '1995-05-15'))
        products_data = [
            ('Vintage Coding Tee', 'Cotton t-shirt.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'),
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
    if not os.path.exists(DB_NAME): initialize_database(DB_NAME)
    return DBManager(DB_NAME)

db_manager = get_db_manager()

# --- ADMIN FUNCTIONS (RESTORED) ---

def admin_analytics():
    st.markdown("### 📊 Sales & Financial Performance")
    df_orders = db_manager.fetch_query_df("SELECT * FROM ORDERS")
    if df_orders.empty:
        st.info("No orders placed yet."); return
    total_revenue = df_orders['total_amount'].sum()
    total_profit = df_orders['total_profit'].sum()
    col1, col2 = st.columns(2)
    col1.metric("Total Revenue", f"${total_revenue:,.2f}")
    col2.metric("Total Profit", f"${total_profit:,.2f}")
    df_orders['date'] = pd.to_datetime(df_orders['order_date']).dt.date
    st.line_chart(df_orders.groupby('date').sum()[['total_amount', 'total_profit']])

def admin_defects_analysis():
    st.markdown("### ⚠️ Quality Control & Defect Analysis")
    df_defects = db_manager.fetch_query_df("SELECT D.*, P.name FROM DEFECTS D JOIN PRODUCTS P ON D.product_id = P.product_id")
    if df_defects.empty:
        st.info("No defects recorded."); return
    st.bar_chart(df_defects.groupby('reason')['quantity'].sum())
    st.dataframe(df_defects)

def admin_product_management():
    st.markdown("### 📦 Inventory & Pricing")
    df_products = db_manager.fetch_query_df("SELECT * FROM PRODUCTS")
    st.dataframe(df_products)

# --- USER INTERFACE ---

def dashboard_page():
    st.title("User Dashboard")
    user_details = st.session_state['user_details']
    tabs_labels = ["📦 Order History", "👤 Profile"]
    if user_details['role'] == 'admin':
        tabs_labels.append("⚙️ Admin Panel")
    
    tabs = st.tabs(tabs_labels)
    with tabs[0]: st.write("Order history logic here.")
    with tabs[1]: st.write("Profile settings logic here.")
    if user_details['role'] == 'admin':
        with tabs[2]:
            admin_tabs = st.tabs(["📊 Sales Analytics", "⚠️ Defects Analysis", "📦 Inventory & Pricing"])
            with admin_tabs[0]: admin_analytics()
            with admin_tabs[1]: admin_defects_analysis()
            with admin_tabs[2]: admin_product_management()

def shop_page():
    st.title("The Shop")
    df = db_manager.fetch_query_df("SELECT * FROM PRODUCTS WHERE stock > 0")
    cols = st.columns(4)
    for i, row in df.iterrows():
        with cols[i % 4]:
            st.image(row['image_url'])
            st.write(f"**{row['name']}**")
            if st.button("View Details", key=f"btn_{row['product_id']}"):
                st.session_state['selected_product_id'] = row['product_id']
                st.session_state['page'] = 'product_detail'
                st.rerun()

def product_detail_page():
    pid = st.session_state.get('selected_product_id')
    res = db_manager.fetch_query("SELECT * FROM PRODUCTS WHERE product_id = ?", (pid,)) if pid else None
    if not res:
        st.session_state['page'] = 'shop'; st.rerun()
    p = dict(res[0])
    st.title(p['name'])
    st.image(p['image_url'], width=300)
    if st.button("➕ Add to Cart"):
        st.session_state['cart'].append({'product_id': p['product_id'], 'name': p['name'], 'price': p['price'], 'total': p['price'], 'quantity': 1, 'size': 'M'})
        st.session_state['page'] = 'checkout'
        st.rerun()

def checkout_page():
    st.title("Checkout")
    if not st.session_state.get('cart'):
        st.warning("Empty cart"); return
    st.table(st.session_state['cart'])
    if st.button("Pay Now"):
        st.success("Success!"); st.session_state['cart'] = []; st.rerun()

def login_page():
    st.title("Login")
    email = st.text_input("Email")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        res = db_manager.fetch_query("SELECT * FROM USERS WHERE email = ?", (email,))
        if res and res[0]['password_hash'] == hash_password(pw):
            st.session_state.update({'logged_in': True, 'email': email, 'username': res[0]['username'], 'user_details': dict(res[0]), 'page': 'shop'})
            st.rerun()
        else: st.error("Invalid credentials")

def main():
    if 'logged_in' not in st.session_state:
        st.session_state.update({'logged_in': False, 'page': 'login', 'cart': []})
    
    if st.session_state['logged_in']:
        with st.sidebar:
            if st.button("🛒 Shop"): st.session_state['page'] = 'shop'; st.rerun()
            if st.button("👤 Dashboard"): st.session_state['page'] = 'dashboard'; st.rerun()
            if st.button("Logout"): st.session_state.clear(); st.rerun()
        
        pg = st.session_state.get('page', 'shop')
        if pg == 'shop': shop_page()
        elif pg == 'product_detail': product_detail_page()
        elif pg == 'checkout': checkout_page()
        elif pg == 'dashboard': dashboard_page()
    else:
        login_page()

if __name__ == '__main__':
    main()
