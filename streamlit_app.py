import streamlit as st
import sqlite3
import hashlib
import uuid
import datetime
import pandas as pd
from threading import Lock
import os
import time

# Set page configuration for a better look
st.set_page_config(page_title="Code & Thread Shop - Premium", layout="wide", initial_sidebar_state="expanded")

# --- Constants and Configuration ---
DB_NAME = 'tshirt_shop_premium.db'

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- STANDALONE DATABASE INITIALIZATION FUNCTION ---
def initialize_database(target_db_path):
    """
    Creates the database file and initializes all schema tables and initial data,
    including sample sales data for analytics.
    """
    conn = None
    try:
        # If file exists, remove it to ensure clean sample data insertion
        if os.path.exists(target_db_path):
             os.remove(target_db_path)
             
        conn = sqlite3.connect(target_db_path, check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        with conn: 
            schema_script = f'''
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
                    discount_type TEXT, -- 'percent' or 'fixed'
                    value REAL,
                    is_active INTEGER
                );
            '''
            c.executescript(schema_script)

            # Add initial users (Admin uses 'admin@shop.com')
            c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", 
                      ('admin@shop.com', 'admin', hash_password('admin'), 'admin', 'https://placehold.co/100x100/1E88E5/FFFFFF?text=A', '1990-01-01'))
            c.execute("INSERT INTO USERS VALUES (?, ?, ?, ?, ?, ?)", 
                      ('customer1@email.com', 'customer1', hash_password('customer1'), 'customer', 'https://placehold.co/100x100/FBC02D/333333?text=C', '1995-05-15'))

            # Add initial products (Multiple products for filtering)
            products_data = [
                # ID 1: Vintage Coding Tee (Price: 25.00, Cost: 10.00, Profit: 15.00)
                ('Vintage Coding Tee', 'A comfortable cotton t-shirt for developers.', 'T-Shirt', 25.00, 10.00, 95, 'https://placehold.co/400x400/36454F/FFFFFF?text=Code+Tee'),
                # ID 2: Python Logo Hoodie (Price: 55.00, Cost: 25.00, Profit: 30.00)
                ('Python Logo Hoodie', 'Warm hoodie featuring the Python logo.', 'Hoodie', 55.00, 25.00, 48, 'https://placehold.co/400x400/FFD700/000000?text=Python+Hoodie'),
                # ID 3: JavaScript Mug (Price: 15.00, Cost: 5.00, Profit: 10.00)
                ('JavaScript Mug', 'A large coffee mug for late-night coding sessions.', 'Accessory', 15.00, 5.00, 198, 'https://placehold.co/400x400/76FF03/000000?text=JS+Mug'),
                # ID 4: SQL Query Cap (Price: 20.00, Cost: 7.50, Profit: 12.50)
                ('SQL Query Cap', 'A stylish baseball cap with a subtle SQL joke.', 'Cap', 20.00, 7.50, 75, 'https://placehold.co/400x400/E53935/FFFFFF?text=SQL+Cap'),
            ]
            c.executemany("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", products_data)
                    
            # Add initial discount codes
            c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('SAVE10', 'percent', 10.0, 1)) # 10% off
            c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('FIVER', 'fixed', 5.0, 1)) # $5 off
            
            # --- Sample Order Data for Analytics (Q1 2024) ---
            
            # Note: total_amount = total_cost + total_profit
            sample_orders = [
                # Order 1 (Jan 1, 2024): 1x Tee ($25.00)
                ('ORD-20240101-001', 'customer1@email.com', '2024-01-01T10:00:00', 25.00, 10.00, 15.00, 'Shipped', 'John Doe', '123 Main St', 'CityA', '10001'),
                # Order 2 (Jan 5, 2024): 1x Hoodie ($55.00)
                ('ORD-20240105-002', 'admin@shop.com', '2024-01-05T12:00:00', 55.00, 25.00, 30.00, 'Processing', 'Admin User', '456 Side Ave', 'CityB', '20002'),
                # Order 3 (Feb 15, 2024): 2x Mug ($30.00) - Total profit 20.00
                ('ORD-20240215-003', 'customer1@email.com', '2024-02-15T14:30:00', 30.00, 10.00, 20.00, 'Delivered', 'John Doe', '123 Main St', 'CityA', '10001'),
                # Order 4 (Mar 10, 2024): 1x Tee, 1x Hoodie ($25 + $55 = $80.00) - Profit: 15+30=45
                ('ORD-20240310-004', 'customer1@email.com', '2024-03-10T11:00:00', 80.00, 35.00, 45.00, 'Shipped', 'John Doe', '123 Main St', 'CityA', '10001'),
                # Order 5 (Mar 25, 2024): 1x Cap ($20.00) - Profit: 12.50
                ('ORD-20240325-005', 'customer1@email.com', '2024-03-25T15:00:00', 20.00, 7.50, 12.50, 'Processing', 'John Doe', '123 Main St', 'CityA', '10001'),
                # Order 6 (Feb 01, 2024): 1x Tee ($25.00)
                ('ORD-20240201-006', 'admin@shop.com', '2024-02-01T09:00:00', 25.00, 10.00, 15.00, 'Shipped', 'Admin User', '456 Side Ave', 'CityB', '20002'),
            ]
            c.executemany("INSERT INTO ORDERS VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sample_orders)

            sample_items = [
                # Items for ORD-20240101-001 (Product ID 1: Tee)
                ('ORD-20240101-001', 1, 'M', 1, 25.00, 10.00), 
                # Items for ORD-20240105-002 (Product ID 2: Hoodie)
                ('ORD-20240105-002', 2, 'L', 1, 55.00, 25.00), 
                # Items for ORD-20240215-003 (Product ID 3: Mug)
                ('ORD-20240215-003', 3, 'N/A', 2, 15.00, 5.00), 
                # Items for ORD-20240310-004 (Product ID 1: Tee)
                ('ORD-20240310-004', 1, 'S', 1, 25.00, 10.00),
                # Items for ORD-20240310-004 (Product ID 2: Hoodie)
                ('ORD-20240310-004', 2, 'XL', 1, 55.00, 25.00), 
                # Items for ORD-20240325-005 (Product ID 4: Cap)
                ('ORD-20240325-005', 4, 'N/A', 1, 20.00, 7.50),
                # Items for ORD-20240201-006 (Product ID 1: Tee)
                ('ORD-20240201-006', 1, 'L', 1, 25.00, 10.00),
            ]
            # Note: item_id is AUTOINCREMENT, so we only list 6 parameters here
            c.executemany("INSERT INTO ORDER_ITEMS (order_id, product_id, size, quantity, unit_price, unit_cost) VALUES (?, ?, ?, ?, ?, ?)", sample_items)
            

    except Exception as e:
        # Clean up failed file if it exists
        if os.path.exists(target_db_path):
             os.remove(target_db_path)
        raise Exception(f"CRITICAL DB INIT ERROR: {e}")
    finally:
        if conn:
            conn.close()

# --- Database Management Class (Passive) ---
class DBManager:
    """Manages the SQLite connection with thread safety."""
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock() 
        self._conn = self._get_connection() 

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL") 
        conn.row_factory = sqlite3.Row 
        return conn

    def execute_query(self, query, params=(), commit=False):
        """Executes a non-SELECT query with thread lock protection."""
        with self._lock:
            conn = self._conn
            c = conn.cursor()
            try:
                if commit:
                    with conn:
                        c.execute(query, params)
                else:
                    c.execute(query, params)
                return c
            except sqlite3.OperationalError as e:
                raise e
            except Exception as e:
                raise e

    def fetch_query(self, query, params=()):
        """Executes a SELECT query and fetches results with thread lock protection."""
        with self._lock:
            conn = self._conn
            c = conn.cursor()
            try:
                c.execute(query, params)
                return c.fetchall()
            except Exception as e:
                raise e

    def fetch_query_df(self, query, params=()):
        """Executes a SELECT query and fetches results as a Pandas DataFrame."""
        with self._lock:
            conn = self._conn
            try:
                df = pd.read_sql_query(query, conn, params=params)
                return df
            except Exception as e:
                raise e

# --- Global Database Manager Instance (Protected Cache) ---
# FIX: Removed the invalid 'suppress_st_warning=True' argument
@st.cache_resource
def get_db_manager():
    # FORCE DATABASE RECREATION to ensure sample data is always present
    if os.path.exists(DB_NAME):
        # Clear the cache before removing the file to prevent errors
        st.cache_resource.clear()
        os.remove(DB_NAME)
        time.sleep(0.5) 

    # Since the file is removed, we must re-initialize it below.
    try:
        initialize_database(DB_NAME)
    except Exception as e:
        st.error(f"FATAL: Database initialization failed. Error: {e}")
        raise e
        
    try:
        return DBManager(DB_NAME)
    except Exception as e:
        st.error(f"Failed to connect to the finalized database. Error: {e}")
        st.stop()
        
db_manager = get_db_manager()

# --- Helper Functions ---

def verify_user(email, password):
    try:
        users = db_manager.fetch_query("SELECT password_hash FROM USERS WHERE email = ?", (email,))
        if users:
            return users[0]['password_hash'] == hash_password(password)
        return False
    except Exception:
        return False

def get_user_details(email):
    try:
        users = db_manager.fetch_query("SELECT * FROM USERS WHERE email = ?", (email,))
        if users:
            return dict(users[0])
    except Exception:
        return None
    return None

def add_user(email, username, password, birthday, profile_pic_url):
    try:
        db_manager.execute_query("INSERT INTO USERS (email, username, password_hash, role, profile_pic_url, birthday) VALUES (?, ?, ?, ?, ?, ?)", 
                                 (email, username, hash_password(password), 'customer', profile_pic_url, birthday), 
                                 commit=True)
        return True
    except sqlite3.IntegrityError:
        return False 
    except Exception:
        return False
        
def update_user_profile(email, username, birthday, profile_pic_url):
    try:
        db_manager.execute_query("UPDATE USERS SET username = ?, birthday = ?, profile_pic_url = ? WHERE email = ?",
                                 (username, birthday, profile_pic_url, email), commit=True)
        # Update session state after successful update
        st.session_state['username'] = username
        st.session_state['user_details'] = get_user_details(email)
        return True
    except Exception as e:
        st.error(f"Error updating profile: {e}")
        return False


def get_product_details(product_id):
    try:
        products = db_manager.fetch_query("SELECT * FROM PRODUCTS WHERE product_id = ?", (product_id,))
        if products:
            return dict(products[0])
    except Exception as e:
        st.error(f"Error fetching product details: {e}")
        return None
    return None

def add_product(name, description, category, price, cost, stock, image_url):
    try:
        db_manager.execute_query("INSERT INTO PRODUCTS (name, description, category, price, cost, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                 (name, description, category, price, cost, stock, image_url), commit=True)
        return True
    except Exception as e:
        st.error(f"Error adding product: {e}")
        return False
        
def delete_product(product_id):
    try:
        db_manager.execute_query("DELETE FROM PRODUCTS WHERE product_id = ?", (product_id,), commit=True)
        return True
    except Exception as e:
        st.error(f"Error deleting product: {e}")
        return False

def calculate_item_total(base_price, quantity):
    """Applies bulk discount: 10% off for 10 or more items."""
    total = base_price * quantity
    bulk_discount = 0.0
    if quantity >= 10:
        discount_rate = 0.10
        bulk_discount = total * discount_rate
        total -= bulk_discount
    return round(total, 2), round(bulk_discount, 2)


def place_order(email, cart_items, final_amount, full_name, address, city, zip_code):
    order_id = str(uuid.uuid4())
    order_date = datetime.datetime.now().isoformat()
    
    total_cost = 0.0

    try:
        with db_manager._lock:
            conn = db_manager._conn
            c = conn.cursor()
            
            with conn: 
                order_item_details = []
                
                for item in cart_items:
                    c.execute("SELECT stock, cost FROM PRODUCTS WHERE product_id = ?", (item['product_id'],))
                    product_data = c.fetchone()
                    
                    if product_data:
                        current_stock = product_data['stock']
                        unit_cost = product_data['cost']
                        
                        if current_stock >= item['quantity']:
                            # Accumulate cost for the order
                            total_cost += unit_cost * item['quantity']
                            
                            # Prepare item for insertion
                            order_item_details.append((order_id, item['product_id'], item['size'], item['quantity'], item['price'], unit_cost))

                            # Update stock (perform updates after ensuring all items are valid)
                            new_stock = current_stock - item['quantity']
                            c.execute("UPDATE PRODUCTS SET stock = ? WHERE product_id = ?", (new_stock, item['product_id']))
                        else:
                            raise Exception(f"Insufficient stock for product ID {item['product_id']}")
                    else:
                        raise Exception(f"Product ID {item['product_id']} not found.")
                
                total_profit = final_amount - total_cost
                
                # Insert all order items
                c.executemany("INSERT INTO ORDER_ITEMS (order_id, product_id, size, quantity, unit_price, unit_cost) VALUES (?, ?, ?, ?, ?, ?)", order_item_details)

                # Insert order record
                c.execute("INSERT INTO ORDERS (order_id, email, order_date, total_amount, total_cost, total_profit, status, full_name, address, city, zip_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (order_id, email, order_date, final_amount, total_cost, total_profit, 'Processing', full_name, address, city, zip_code))

            return True, order_id

    except sqlite3.OperationalError:
         return False, "Database busy. Please try completing your order again."
    except Exception as e:
         return False, f"Order failed due to an error: {e}"

# --- Page Functions ---

def login_page():
    st.title("Welcome to Code & Thread Shop")
    st.subheader("Login / Sign Up")
    st.caption("Please use a valid email format for your username.")

    col1, col2 = st.columns(2)

    with col1:
        with st.form("login_form"):
            st.markdown("#### Login")
            login_email = st.text_input("Email", key="login_email_input")
            login_password = st.text_input("Password", type="password", key="login_password_input")
            login_submitted = st.form_submit_button("Login", type="primary")

            if login_submitted:
                if verify_user(login_email, login_password):
                    st.session_state['logged_in'] = True
                    st.session_state['email'] = login_email
                    user_details = get_user_details(login_email)
                    st.session_state['username'] = user_details['username']
                    st.session_state['user_details'] = user_details
                    st.success(f"Welcome back, {st.session_state['username']}!")
                    st.session_state['page'] = 'shop'
                    st.rerun()
                else:
                    st.error("Invalid email or password.")
            st.markdown("---")
            st.caption("Admin: `admin@shop.com` / `admin` | Customer: `customer1@email.com` / `customer1`")


    with col2:
        with st.form("signup_form"):
            st.markdown("#### Sign Up")
            signup_email = st.text_input("Your Email", key="signup_email_input", help="Used for login.")
            signup_username = st.text_input("Your Name/Nickname", key="signup_username_input")
            signup_password = st.text_input("New Password", type="password", key="signup_password_input")
            signup_birthday = st.date_input("Birthday (Optional)", datetime.date(2000, 1, 1), key="signup_birthday")
            signup_pic = st.text_input("Profile Picture URL (Optional)", key="signup_pic", placeholder="e.g., https://example.com/pic.jpg")
            
            signup_submitted = st.form_submit_button("Create Account", type="secondary")

            if signup_submitted:
                if not signup_email or "@" not in signup_email:
                    st.error("Please enter a valid email address.")
                elif len(signup_password) < 5:
                    st.error("Password must be at least 5 characters.")
                elif add_user(signup_email, signup_username, signup_password, signup_birthday.isoformat(), signup_pic):
                    st.session_state['logged_in'] = True
                    st.session_state['email'] = signup_email
                    st.session_state['username'] = signup_username
                    st.session_state['user_details'] = get_user_details(signup_email)
                    st.success("Account created! You are now logged in.")
                    st.session_state['page'] = 'shop'
                    st.rerun()
                else:
                    st.error("Email already exists or database error.")

def shop_page():
    st.title("The Shop")
    st.subheader("Browse Our Catalog")
    
    if 'cart' not in st.session_state:
        st.session_state['cart'] = []
    
    # 1. Fetch all products
    df_products = db_manager.fetch_query_df("SELECT * FROM PRODUCTS WHERE stock > 0")
    
    if df_products.empty:
        st.info("No products currently in stock.")
        return

    # 2. Filters and Search
    col_search, col_category, col_size = st.columns([3, 2, 1])

    with col_search:
        search_term = st.text_input("🔍 Search Products", placeholder="e.g., Tee, Hoodie, Python", key="search_bar")
    
    with col_category:
        categories = ['All'] + df_products['category'].unique().tolist()
        selected_category = st.selectbox("Filter by Category", categories, key="category_filter")

    with col_size:
        sizes = ['All', 'S', 'M', 'L', 'XL']
        selected_size = st.selectbox("Filter by Size", sizes, key="size_filter")
        # NOTE: Size filter is purely a label for the user since product table doesn't track stock per size.

    # Apply filters
    filtered_df = df_products.copy()
    
    if selected_category != 'All':
        filtered_df = filtered_df[filtered_df['category'] == selected_category]
        
    if search_term:
        filtered_df = filtered_df[
            filtered_df['name'].str.contains(search_term, case=False) |
            filtered_df['description'].str.contains(search_term, case=False)
        ]

    # 3. Display Products (Grid Layout)
    st.markdown("---")
    
    cols = st.columns(4) 
    
    for index, row in filtered_df.iterrows():
        product_id = row['product_id']
        col_index = index % 4
        
        with cols[col_index]:
            card_html = f"""
            <style>
                .product-card {{
                    background-color: #f0f2f6;
                    border-radius: 12px;
                    padding: 15px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    margin-bottom: 20px;
                    text-align: center;
                    cursor: pointer;
                    transition: all 0.2s ease-in-out;
                }}
                .product-card:hover {{
                    box-shadow: 0 8px 12px rgba(0, 0, 0, 0.2);
                    transform: translateY(-5px);
                }}
                .card-title {{
                    font-weight: 700;
                    font-size: 1.2rem;
                    color: #1E88E5;
                    margin-top: 5px;
                    margin-bottom: 5px;
                }}
                .card-price {{
                    font-size: 1.1rem;
                    font-weight: bold;
                    color: #E53935;
                }}
                .card-stock {{
                    font-size: 0.85rem;
                    color: #616161;
                }}
            </style>
            <div class="product-card">
                <img src="{row['image_url']}" style="width: 100%; height: auto; border-radius: 8px;">
                <p class="card-title">{row['name']}</p>
                <p class="card-price">${row['price']:.2f}</p>
                <p class="card-stock">Stock: {row['stock']}</p>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
            
            # Use a button to handle navigation to the detail page
            if st.button("View Details", key=f"view_btn_{product_id}"):
                st.session_state['page'] = 'product_detail'
                st.session_state['selected_product_id'] = product_id
                st.rerun()

def product_detail_page():
    product_id = st.session_state.get('selected_product_id')
    if not product_id:
        st.warning("No product selected. Returning to shop.")
        st.session_state['page'] = 'shop'
        st.rerun()
        return

    product = get_product_details(product_id)
    if not product:
        st.error("Product details could not be loaded.")
        st.session_state['page'] = 'shop'
        st.rerun()
        return
        
    st.title(product['name'])
    
    # 1. Back to Catalog
    if st.button("⬅️ Back to Shop", key="back_to_shop_detail_btn"):
        st.session_state['page'] = 'shop'
        st.rerun()
    
    st.markdown("---")

    col_img, col_info = st.columns([1, 2])
    
    with col_img:
        st.image(product['image_url'], caption=product['name'], use_column_width='always')
    
    with col_info:
        st.markdown(f"## ${product['price']:.2f}")
        st.subheader("Description")
        st.write(product['description'])
        st.markdown(f"**Category:** {product['category']}")
        st.markdown(f"**Stock:** {product['stock']} available")
        st.info("Wholesale pricing: 10% off when buying 10 or more items!")
        
        st.markdown("---")
        
        # 2. Size Chart Modal
        with st.expander("📏 View Size Chart"):
            st.markdown("""
            | Size | Chest (in) | Length (in) |
            | :--- | :---: | :---: |
            | **S** | 34 - 36 | 27 |
            | **M** | 38 - 40 | 28 |
            | **L** | 42 - 44 | 29 |
            | **XL** | 46 - 48 | 30 |
            """)
            st.caption("Measurements are approximate and for standard fit.")
            
        st.markdown("---")

        # 3. Add to Cart Logic
        if product['category'] in ['T-Shirt', 'Hoodie']:
            size_options = ['S', 'M', 'L', 'XL']
            selected_size = st.selectbox("Select Size", size_options, key="detail_size")
        else:
            size_options = ['N/A']
            selected_size = 'N/A'

        max_qty = product['stock']
        if max_qty == 0:
            st.error("This item is currently out of stock.")
            return

        quantity = st.number_input("Quantity", min_value=1, max_value=max_qty, value=1, step=1, key="detail_quantity")
        
        if st.button("➕ Add to Cart", type="primary"):
            new_total, bulk_discount = calculate_item_total(product['price'], quantity)

            new_item = {
                'product_id': product['product_id'],
                'name': product['name'],
                'size': selected_size,
                'quantity': quantity,
                'price': product['price'], 
                'cost': product['cost'],
                'total': new_total, 
                'bulk_discount': bulk_discount
            }

            cart_updated = False
            for i in range(len(st.session_state['cart'])):
                item = st.session_state['cart'][i]
                if item['product_id'] == product['product_id'] and item['size'] == selected_size:
                    st.session_state['cart'][i].update(new_item)
                    cart_updated = True
                    break
            
            if not cart_updated:
                st.session_state['cart'].append(new_item)

            st.toast(f"{quantity}x {selected_size} {product['name']} added/updated in cart!")
            st.session_state['page'] = 'checkout' # Navigate directly to checkout after adding
            st.rerun()


def checkout_page():
    st.title("Checkout")

    if 'cart' not in st.session_state or not st.session_state['cart']:
        st.warning("Your cart is empty.")
        if st.button("Go to Shop"):
            st.session_state['page'] = 'shop'
            st.rerun()
        return

    # --- Step 1: Order Summary and Shipping ---
    st.subheader("Order Summary")
        
    cart_df = pd.DataFrame(st.session_state['cart'])
    cart_df['Unit Price'] = cart_df['price'].apply(lambda x: f"${x:.2f}")
    cart_df['Bulk Discount'] = cart_df['bulk_discount'].apply(lambda x: f"- ${x:.2f}")
    cart_df['Final Total'] = cart_df['total'].apply(lambda x: f"${x:.2f}")
    
    display_cols = ['name', 'size', 'quantity', 'Unit Price', 'Bulk Discount', 'Final Total']
    st.dataframe(cart_df[display_cols], hide_index=True, use_container_width=True)

    subtotal_amount = cart_df['total'].sum()
    
    if 'coupon_discount' not in st.session_state:
        st.session_state['coupon_discount'] = 0.0

    # --- Step 2: Discount Application (Simulated Spin the Wheel) ---
    st.subheader("Discount Vouchers")
    
    # Simple animation/simulation for "Spin the Wheel"
    with st.expander("🎰 Try Your Luck: Reveal Discount"):
        st.markdown(
            """
            <div style="text-align: center; padding: 20px; border: 2px solid #FFC107; border-radius: 10px; background-color: #FFFDE7;">
                <p style="font-size: 1.2rem; font-weight: bold;">[Simulated] Click below to reveal a random discount!</p>
                <button 
                    onclick="this.innerText='Spinning...';" 
                    style="background-color: #FFC107; color: black; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; transition: all 0.3s;"
                >
                    SPIN THE WHEEL
                </button>
            </div>
            """, unsafe_allow_html=True)
        
        # Real logic is just a coupon input
        coupon_input = st.text_input("Apply Coupon Code", max_chars=10, key="coupon_input_checkout")
        
        if st.button("Apply Discount Code"):
            code = coupon_input.upper()
            discount_data = db_manager.fetch_query("SELECT discount_type, value FROM DISCOUNTS WHERE code = ? AND is_active = 1", (code,))
            
            if discount_data:
                discount = dict(discount_data[0])
                if discount['discount_type'] == 'percent':
                    discount_value = subtotal_amount * (discount['value'] / 100)
                elif discount['discount_type'] == 'fixed':
                    discount_value = discount['value']
                
                st.session_state['coupon_discount'] = round(discount_value, 2)
                st.success(f"Coupon '{code}' applied! Discount: -${st.session_state['coupon_discount']:.2f}")
                st.rerun()
            else:
                st.session_state['coupon_discount'] = 0.0
                st.error("Invalid or expired coupon code. Try 'SAVE10' (10% off) or 'FIVER' ($5 off).")
                st.rerun()
    
    final_payable = subtotal_amount - st.session_state['coupon_discount']
    
    st.markdown("---")
    st.metric("Subtotal", f"${subtotal_amount:.2f}")
    if st.session_state['coupon_discount'] > 0:
        st.metric("Coupon Discount", f"- ${st.session_state['coupon_discount']:.2f}")
    st.markdown(f"## Final Payable: **${final_payable:.2f}**")
    
    st.subheader("Shipping Information")

    user_email = st.session_state['email']
    user_details = st.session_state['user_details']

    # Initialize shipping info
    if 'shipping_info' not in st.session_state:
        st.session_state['shipping_info'] = {
            'full_name': user_details.get('username', '').capitalize() or user_email,
            'address': '', 'city': '', 'zip_code': ''
        }

    # Shipping Form
    with st.form("shipping_payment_form"):
        full_name = st.text_input("Full Name", value=st.session_state['shipping_info']['full_name'], required=True)
        address = st.text_area("Shipping Address", value=st.session_state['shipping_info']['address'], required=True)
        
        col_city, col_zip = st.columns(2)
        with col_city:
            city = st.text_input("City", value=st.session_state['shipping_info']['city'], required=True)
        with col_zip:
            zip_code = st.text_input("Zip Code", value=st.session_state['shipping_info']['zip_code'], required=True)
        
        st.session_state['shipping_info'].update({
            'full_name': full_name, 'address': address, 'city': city, 'zip_code': zip_code
        })

        st.markdown("#### Payment Details (Simulated)")
        card_number = st.text_input("Card Number", max_chars=16, placeholder="16-digit number")
        col_exp, col_cvv = st.columns(2)
        with col_exp:
             expiration = st.text_input("Expiration Date (MM/YY)", max_chars=5)
        with col_cvv:
            cvv = st.text_input("CVV", type="password", max_chars=4)
        
        pay_button = st.form_submit_button(f"💳 Pay ${final_payable:.2f} and Place Order", type="primary")

        if pay_button:
            if not all([full_name, address, city, zip_code]):
                st.error("Please fill in shipping information.")
            elif len(card_number) < 15 or len(expiration) != 5 or len(cvv) < 3:
                st.error("Please enter valid (fake) payment details to simulate a successful transaction.")
            else:
                success, result = place_order(
                    user_email,
                    st.session_state['cart'],
                    final_payable,
                    full_name, address, city, zip_code
                )
                
                if success:
                    st.success(f"Payment successful! Order successfully placed! Order ID: {result}")
                    st.session_state['cart'] = []
                    st.session_state['coupon_discount'] = 0.0
                    st.balloons()
                    st.session_state['page'] = 'order_complete'
                    st.session_state['last_order_id'] = result
                    st.rerun()
                else:
                    st.error(f"Order failed: {result}")


def admin_product_management():
    """Allows admin to add and delete products."""
    st.markdown("### 🛠️ Product Management")
    
    # --- Add Product Form ---
    with st.expander("➕ Add New Product", expanded=False):
        with st.form("add_product_form", clear_on_submit=True):
            st.subheader("Product Details")
            new_name = st.text_input("Product Name", max_chars=100)
            new_desc = st.text_area("Description")
            
            categories = ['T-Shirt', 'Hoodie', 'Accessory', 'Cap', 'Other']
            new_category = st.selectbox("Category", categories)
            
            new_image_url = st.text_input("Image URL (Simulated Upload)", placeholder="e.g., https://placehold.co/400x400/?text=New+Product")

            col_price, col_cost, col_stock = st.columns(3)
            with col_price:
                new_price = st.number_input("Selling Price ($)", min_value=0.01, format="%.2f")
            with col_cost:
                new_cost = st.number_input("Manufacture Cost ($)", min_value=0.01, format="%.2f")
            with col_stock:
                # User request: Keeping bulk quantity in stock
                new_stock = st.number_input("Initial Stock (Bulk Quantity)", min_value=0, step=1)
                
            if st.form_submit_button("Add Product", type="primary"):
                if new_name and new_desc and new_price > 0 and new_cost > 0 and new_stock >= 0 and new_image_url:
                    if add_product(new_name, new_desc, new_category, new_price, new_cost, new_stock, new_image_url):
                        st.success(f"Product '{new_name}' added successfully! Note: Image is stored as URL, not a file.")
                        # Form clears automatically due to clear_on_submit=True (User request #3)
                        st.rerun()
                    else:
                        st.error("Failed to add product.")
                else:
                    st.error("Please fill out all product details correctly.")

    # --- Current Catalog & Delete Section ---
    st.markdown("---")
    st.markdown("##### Current Catalog")
    
    df_products = db_manager.fetch_query_df("SELECT product_id, image_url, name, category, price, cost, stock FROM PRODUCTS")
    
    if not df_products.empty:
        # Prepare DataFrame for better display (showing image instead of link - User request #4)
        df_display = df_products.copy()
        
        # Function to display image instead of URL
        def format_image(url):
             return f'<img src="{url}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 4px;"/>'
             
        df_display['Image'] = df_display['image_url'].apply(format_image)
        df_display.rename(columns={'product_id': 'ID', 'name': 'Name', 'category': 'Category', 'price': 'Price', 'cost': 'Cost', 'stock': 'Stock'}, inplace=True)
        
        st.markdown(df_display[['Image', 'ID', 'Name', 'Category', 'Price', 'Cost', 'Stock']].to_html(escape=False, index=False), unsafe_allow_html=True)

        # Delete Product Selection
        st.markdown("##### Delete Existing Product")
        product_options = {f"{row['Name']} (ID: {row['ID']})": row['ID'] for index, row in df_display.iterrows()}
        
        # Check if there are any products to select
        if product_options:
            selected_product_name = st.selectbox("Select Product to Delete", list(product_options.keys()))
            
            if selected_product_name:
                product_to_delete_id = product_options[selected_product_name]
                
                if st.button(f"Delete '{selected_product_name}'", type="secondary"):
                    if delete_product(product_to_delete_id):
                        st.success(f"Product ID {product_to_delete_id} deleted.")
                        st.rerun()
                    else:
                        st.error("Could not delete product.")
        else:
            st.info("No products available to delete.")

def admin_analytics():
    """Calculates and displays profit/loss/revenue and sales graphs."""
    st.markdown("### 📊 Sales & Financial Performance Tracking (Admin Only)")

    # Fetch all orders and items for comprehensive analysis
    df_orders = db_manager.fetch_query_df("SELECT * FROM ORDERS")
    
    if df_orders.empty:
        st.info("No orders placed yet. Financial metrics not available.")
        return

    # --- KPI Cards ---
    total_revenue = df_orders['total_amount'].sum()
    total_cost = df_orders['total_cost'].sum()
    total_profit = df_orders['total_profit'].sum()
    
    st.markdown("#### Key Performance Indicators")
    col_rev, col_cogs, col_profit = st.columns(3)
    
    with col_rev:
        st.metric("Total Revenue (Sales)", f"${total_revenue:,.2f}", delta_color="normal")
    with col_cogs:
        st.metric("Total COGS (Cost)", f"${total_cost:,.2f}", delta_color="inverse")
    with col_profit:
        # Delta shows profit margin percentage
        margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0
        st.metric("Total Profit", f"${total_profit:,.2f}", f"{margin:,.1f}% Margin")

    # --- Sales and Profit Graph ---
    df_orders['order_date_dt'] = pd.to_datetime(df_orders['order_date']).dt.date
    
    # Aggregate daily data
    sales_daily = df_orders.groupby('order_date_dt').agg(
        {'total_amount': 'sum', 'total_profit': 'sum'}
    ).reset_index()
    sales_daily.rename(columns={'total_amount': 'Daily Revenue', 'total_profit': 'Daily Profit', 'order_date_dt': 'Date'}, inplace=True)

    st.markdown("#### Revenue vs. Profit Over Time")
    st.line_chart(sales_daily, x='Date', y=['Daily Revenue', 'Daily Profit'])
    
    # --- Product Sales Breakdown ---
    # Fetch all order items and join with products
    query = """
    SELECT 
        OI.quantity, 
        P.name 
    FROM ORDER_ITEMS OI
    JOIN PRODUCTS P ON OI.product_id = P.product_id
    """
    df_items = db_manager.fetch_query_df(query)
    
    if not df_items.empty:
        st.markdown("#### Product Quantity Breakdown")
        product_sales_qty = df_items.groupby('name')['quantity'].sum().reset_index()
        product_sales_qty.rename(columns={'name': 'Product Name', 'quantity': 'Total Quantity Sold'}, inplace=True)
        
        # Use a bar chart to visualize product quantity sold
        st.bar_chart(product_sales_qty, x='Product Name', y='Total Quantity Sold')


    # --- Order Status Breakdown ---
    st.markdown("#### Order Status Breakdown")
    status_counts = df_orders['status'].value_counts().reset_index()
    status_counts.columns = ['Status', 'Count']
    st.bar_chart(status_counts, x='Status', y='Count')
    
    st.markdown("---")
    st.markdown("##### Raw Order Data")
    st.dataframe(df_orders[['order_id', 'order_date_dt', 'email', 'total_amount', 'total_cost', 'total_profit', 'status']], hide_index=True, use_container_width=True)


def user_profile_management():
    st.markdown("### 👤 Profile Settings")

    user_email = st.session_state['email']
    current_details = st.session_state['user_details']
    
    col_pic, col_info = st.columns([1, 2])
    
    with col_pic:
        st.image(current_details['profile_pic_url'] or "https://placehold.co/100x100/CCCCCC/333333?text=User", width=150)
        st.caption(f"Logged in as: `{user_email}`")
    
    with col_info:
        with st.form("update_profile_form"):
            new_username = st.text_input("Name/Nickname", value=current_details['username'])
            
            # Format birthday from DB (ISO string) to date object for widget
            db_birthday_str = current_details['birthday']
            if db_birthday_str and db_birthday_str != '2000-01-01': # Check for existing or non-default value
                 db_birthday = datetime.date.fromisoformat(db_birthday_str)
            else:
                 # Default if null or initial value
                 db_birthday = datetime.date(2000, 1, 1)

            new_birthday = st.date_input("Birthday", value=db_birthday)
            
            new_pic_url = st.text_input("Profile Picture URL", value=current_details['profile_pic_url'] or "", placeholder="e.g., https://example.com/pic.jpg")
            
            if st.form_submit_button("Update Profile", type="primary"):
                if update_user_profile(user_email, new_username, new_birthday.isoformat(), new_pic_url):
                    st.success("Profile updated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to update profile.")
            

def dashboard_page():
    st.title("User Dashboard")
    st.subheader(f"Welcome, {st.session_state['username'].capitalize()}")
    
    user_details = st.session_state['user_details']

    # Tab navigation for Dashboard features
    tabs = ["📦 Order History", "👤 Profile", "⚙️ Admin Panel"] if user_details['role'] == 'admin' else ["📦 Order History", "👤 Profile"]
    selected_tab = st.tabs(tabs)
    
    if user_details['role'] == 'admin':
        tab_history, tab_profile, tab_admin = selected_tab
    else:
        tab_history, tab_profile = selected_tab
    
    # --- Order History Tab ---
    with tab_history:
        st.markdown("### Your Order History")
        try:
            df_orders = db_manager.fetch_query_df(
                "SELECT order_id, order_date, total_amount, status FROM ORDERS WHERE email = ? ORDER BY order_date DESC", 
                params=(st.session_state['email'],)
            )
        except Exception as e:
            st.error(f"Could not retrieve orders. Database error: {e}")
            df_orders = pd.DataFrame() # Ensure df_orders is defined

        if df_orders.empty:
            st.info("You have no past orders.")
        else:
            df_display = df_orders.copy()
            df_display['total_amount'] = df_display['total_amount'].apply(lambda x: f"${x:.2f}")
            df_display.rename(columns={'order_id': 'Order ID', 'order_date': 'Date', 'total_amount': 'Total', 'status': 'Status'}, inplace=True)
            
            st.dataframe(df_display, hide_index=True, use_container_width=True)

    # --- Profile Tab ---
    with tab_profile:
        user_profile_management()

    # --- Admin Panel Tab (Visible only to admin) ---
    if user_details['role'] == 'admin':
        with tab_admin:
            st.markdown("## Global Admin Control")
            admin_tabs = st.tabs(["📊 Analytics", "📦 Inventory & Pricing"])
            with admin_tabs[0]:
                admin_analytics()
            with admin_tabs[1]:
                admin_product_management()

def order_complete_page():
    st.title("Order Confirmed!")
    order_id = st.session_state.get('last_order_id', 'N/A')
    st.success(f"Thank you for your purchase, {st.session_state['username'].capitalize()}")
    st.markdown(f"Your order ID is: **{order_id}**")
    st.info("You can track your order in the dashboard.")

    if st.button("Continue Shopping"):
        st.session_state['page'] = 'shop'
        st.rerun()

# --- Main App Logic ---

def main_app():
    """The main entry point for the Streamlit application."""

    # Initialize state variables
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['page'] = 'login' 
        st.session_state['cart'] = []
        st.session_state['coupon_discount'] = 0.0

    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/T-shirt_Icon.svg/1024px-T-shirt_Icon.svg.png", width=100)
        st.title("Code & Thread")
        
        if st.session_state['logged_in']:
            st.markdown(f"**Hi, {st.session_state['username']}**")
            
            # Navigation links
            if st.button("🛒 Shop"):
                st.session_state['page'] = 'shop'
            if st.button("👤 Dashboard"):
                st.session_state['page'] = 'dashboard'
            
            # Cart Status always visible
            st.markdown("---")
            cart_count = sum(item['quantity'] for item in st.session_state.get('cart', []))
            cart_total = sum(item['total'] for item in st.session_state.get('cart', []))
            
            st.markdown(f"**Cart Items:** {cart_count}")
            st.markdown(f"**Cart Total:** ${cart_total:.2f}")

            if cart_count > 0 and st.button("➡️ Checkout", type="primary"):
                 st.session_state['page'] = 'checkout'
                 st.rerun()
            
            # Logout button
            if st.button("Logout", type="secondary"):
                st.session_state.clear()
                st.session_state['logged_in'] = False
                st.session_state['page'] = 'login'
                st.rerun()

        else:
            if st.button("Login / Sign Up"):
                st.session_state['page'] = 'login'
            st.info("Please log in to shop.")

    # --- Page Routing ---
    if st.session_state['logged_in']:
        page = st.session_state['page']
        
        if page == 'shop':
            shop_page()
        elif page == 'product_detail':
            product_detail_page()
        elif page == 'checkout':
            checkout_page()
        elif page == 'dashboard':
            dashboard_page()
        elif page == 'order_complete':
            order_complete_page()
        else:
            shop_page()
    else:
        login_page()


if __name__ == '__main__':
    try:
        main_app()
    except Exception as e:
        st.error(f"An unexpected application error occurred. Please refresh the page. Error: {e}")
