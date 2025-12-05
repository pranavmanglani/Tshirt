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
st.set_page_config(page_title="Code & Thread Shop", layout="centered", initial_sidebar_state="expanded")

# --- Constants and Configuration ---
DB_NAME = 'tshirt_shop.db'
PRODUCT_ID = 1  # Fixed ID for the single T-shirt product

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- Wholesale and Discount Helper ---

def calculate_item_total(base_price, quantity):
    """
    Applies bulk discount for the single product (Wholesale Feature).
    10% off for 10 or more items.
    """
    total = base_price * quantity
    bulk_discount = 0.0
    if quantity >= 10:
        # 10% wholesale discount
        discount_rate = 0.10
        bulk_discount = total * discount_rate
        total -= bulk_discount
    return round(total, 2), round(bulk_discount, 2)


# --- STANDALONE DATABASE INITIALIZATION FUNCTION ---
def initialize_database(target_db_path):
    """
    Creates the database file and initializes all schema tables and initial data, 
    including the new DISCOUNTS table.
    """
    conn = None
    try:
        if os.path.exists(target_db_path):
             return
             
        conn = sqlite3.connect(target_db_path, check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        with conn: 
            schema_script = f'''
                CREATE TABLE USERS (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT,
                    role TEXT
                );
                
                CREATE TABLE PRODUCTS (
                    product_id INTEGER PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    price REAL,
                    stock INTEGER
                );
                
                CREATE TABLE ORDERS (
                    order_id TEXT PRIMARY KEY,
                    username TEXT,
                    order_date TEXT,
                    total_amount REAL,
                    status TEXT,
                    full_name TEXT,
                    address TEXT,
                    city TEXT,
                    zip_code TEXT,
                    FOREIGN KEY (username) REFERENCES USERS(username)
                );

                CREATE TABLE ORDER_ITEMS (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    product_id INTEGER,
                    size TEXT,
                    quantity INTEGER,
                    unit_price REAL,
                    FOREIGN KEY (order_id) REFERENCES ORDERS(order_id),
                    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
                );
                
                -- New table for Discounts
                CREATE TABLE DISCOUNTS (
                    code TEXT PRIMARY KEY,
                    discount_type TEXT, -- 'percent' or 'fixed'
                    value REAL,
                    is_active INTEGER
                );
            '''
            c.executescript(schema_script)

            # Add initial users
            c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('admin', hash_password('admin'), 'admin'))
            c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('customer1', hash_password('customer1'), 'customer'))

            # Add initial product data (we keep the single product for simplicity as requested)
            c.execute("INSERT INTO PRODUCTS VALUES (?, ?, ?, ?, ?)",
                    (PRODUCT_ID, 'Vintage Coding Tee', 'A comfortable cotton t-shirt for developers.', 25.00, 100))
                    
            # Add initial discount codes
            c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('SAVE10', 'percent', 10.0, 1)) # 10% off
            c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('FIVER', 'fixed', 5.0, 1)) # $5 off
            c.execute("INSERT INTO DISCOUNTS VALUES (?, ?, ?, ?)", ('EXPIRED', 'percent', 20.0, 0)) # Inactive
            

    except Exception as e:
        if os.path.exists(target_db_path):
             os.remove(target_db_path)
        raise Exception(f"CRITICAL DB INIT ERROR: {e}")
    finally:
        if conn:
            conn.close()

# --- Database Management Class (Passive) ---
class DBManager:
    """
    Manages the SQLite connection. It performs NO initialization or setup.
    It relies entirely on the initialize_database function to run beforehand.
    """
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock() 
        self._conn = self._get_connection() 

    def _get_connection(self):
        """Creates the connection with a high timeout and WAL mode."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL") 
        conn.row_factory = sqlite3.Row 
        return conn

    # --- Data Access Methods (Using the connection) ---

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
@st.cache_resource
def get_db_manager():
    """
    Manages the initialization and returns the thread-safe DBManager instance.
    """
    if not os.path.exists(DB_NAME):
        time.sleep(1) 
        
        if os.path.exists(DB_NAME):
            pass
        else:
            try:
                initialize_database(DB_NAME)
            except Exception as e:
                st.error(f"FATAL: Database initialization failed after pause. Error: {e}")
                raise e

    try:
        return DBManager(DB_NAME)
    except Exception as e:
        st.error(f"Failed to connect to the finalized database. Error: {e}")
        st.stop()
        
# --- Global Access to DB Manager ---
try:
    db_manager = get_db_manager()
except Exception as e:
    st.error("CRITICAL: Application cannot start due to persistent database error. Please refresh and try again.")
    st.stop() 


# --- Helper Functions (using the new passive DBManager) ---

def verify_user(username, password):
    try:
        users = db_manager.fetch_query("SELECT password_hash FROM USERS WHERE username = ?", (username,))
        if users:
            return users[0]['password_hash'] == hash_password(password)
        return False
    except Exception:
        return False

def add_user(username, password):
    try:
        db_manager.execute_query("INSERT INTO USERS VALUES (?, ?, ?)", 
                                 (username, hash_password(password), 'customer'), 
                                 commit=True)
        return True
    except sqlite3.IntegrityError:
        return False 
    except sqlite3.OperationalError:
        st.warning("Database busy. Please try again.")
        return False
    except Exception:
        return False

def get_product_details(product_id):
    try:
        products = db_manager.fetch_query("SELECT * FROM PRODUCTS WHERE product_id = ?", (product_id,))
        if products:
            row = products[0]
            return {'product_id': row['product_id'], 'name': row['name'], 'description': row['description'], 'price': row['price'], 'stock': row['stock']}
    except Exception as e:
        print(f"Error fetching product details: {e}")
        return None
    return None

def get_discount(code):
    """Fetches active coupon details from the database."""
    try:
        results = db_manager.fetch_query("SELECT discount_type, value FROM DISCOUNTS WHERE code = ? AND is_active = 1", (code,))
        if results:
            return dict(results[0])
        return None
    except Exception:
        return None


def place_order(username, cart_items, final_amount, full_name, address, city, zip_code):
    order_id = str(uuid.uuid4())
    order_date = datetime.datetime.now().isoformat()

    try:
        with db_manager._lock:
            conn = db_manager._conn
            c = conn.cursor()
            
            with conn: 
                # Use final_amount calculated in checkout_page
                c.execute("INSERT INTO ORDERS (order_id, username, order_date, total_amount, status, full_name, address, city, zip_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (order_id, username, order_date, final_amount, 'Processing', full_name, address, city, zip_code))

                for item in cart_items:
                    c.execute("SELECT stock FROM PRODUCTS WHERE product_id = ?", (item['product_id'],))
                    product_stock = c.fetchone()
                    
                    if product_stock and product_stock[0] >= item['quantity']:
                        # unit_price here is the original product price for accounting
                        c.execute("INSERT INTO ORDER_ITEMS (order_id, product_id, size, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
                                (order_id, item['product_id'], item['size'], item['quantity'], item['price']))

                        new_stock = product_stock[0] - item['quantity']
                        c.execute("UPDATE PRODUCTS SET stock = ? WHERE product_id = ?", (new_stock, item['product_id']))
                    else:
                        raise Exception(f"Insufficient stock for product ID {item['product_id']}")

            return True, order_id

    except sqlite3.OperationalError:
         return False, "Database busy. Please try completing your order again."
    except Exception as e:
         if "Insufficient stock" in str(e):
             return False, f"Order failed: {str(e)}"
         st.error(f"Database error during order placement: {e}")
         return False, f"Order failed due to an internal error: {e}"

def add_product(name, description, price, stock):
    """Adds a new product to the database."""
    try:
        # Use an arbitrary ID for new products since the initial one is fixed (PRODUCT_ID=1)
        db_manager.execute_query("INSERT INTO PRODUCTS (name, description, price, stock) VALUES (?, ?, ?, ?)", 
                                 (name, description, price, stock), commit=True)
        return True
    except Exception as e:
        st.error(f"Error adding product: {e}")
        return False
        
def delete_product(product_id):
    """Deletes a product from the database."""
    try:
        db_manager.execute_query("DELETE FROM PRODUCTS WHERE product_id = ?", (product_id,), commit=True)
        return True
    except Exception as e:
        st.error(f"Error deleting product: {e}")
        return False

# --- Streamlit Page Functions ---

def login_page():
    st.subheader("Login / Sign Up")

    col1, col2 = st.columns(2)

    with col1:
        with st.form("login_form"):
            st.markdown("#### Login")
            login_username = st.text_input("Username", key="login_username_input")
            login_password = st.text_input("Password", type="password", key="login_password_input")
            login_submitted = st.form_submit_button("Login")

            if login_submitted:
                if verify_user(login_username, login_password):
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = login_username
                    st.success(f"Welcome back, {login_username}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
            st.markdown("---")
            st.caption("Admin: `admin` / `admin` | Customer: `customer1` / `customer1`")


    with col2:
        with st.form("signup_form"):
            st.markdown("#### Sign Up")
            signup_username = st.text_input("New Username", key="signup_username_input")
            signup_password = st.text_input("New Password", type="password", key="signup_password_input")
            signup_submitted = st.form_submit_button("Sign Up")

            if signup_submitted:
                if len(signup_username) < 3 or len(signup_password) < 5:
                    st.error("Username must be at least 3 characters and password at least 5.")
                elif add_user(signup_username, signup_password):
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = signup_username
                    st.success("Account created! You are now logged in.")
                    st.rerun()
                else:
                    st.error("Username already exists or database is busy.")

def product_page():
    st.title("T-Shirt Store")

    # Fetch all products now, not just one, to allow for future expansion
    df_products = db_manager.fetch_query_df("SELECT * FROM PRODUCTS")
    
    if df_products.empty:
        st.info("No products available in the shop right now.")
        return

    # For simplicity, we still focus on the single product ID 1 for detailed view and hardcoded image
    product = get_product_details(PRODUCT_ID)
    if not product:
        # Fallback if product ID 1 was somehow deleted, use the first available product
        first_product_row = df_products.iloc[0]
        product = first_product_row.to_dict()
        product['product_id'] = first_product_row['product_id']
        st.warning(f"Default product not found. Showing {product['name']}.")
        
    st.subheader(product['name'])
    st.write(product['description'])
    st.markdown(f"**Price:** ${product['price']:.2f}")
    st.markdown(f"**Stock:** {product['stock']} available")
    st.info("Wholesale pricing: 10% off when buying 10 or more items!")

    # Using the hardcoded image URL for the main featured product
    st.image("https://placehold.co/400x400/36454F/FFFFFF?text=Awesome+Code+Tee", caption=f"The {product['name']}", use_column_width=False)

    st.subheader("Select Options")
    
    if 'cart' not in st.session_state:
        st.session_state['cart'] = []

    col_size, col_qty, col_add = st.columns([1, 1, 1])

    with col_size:
        size = st.selectbox("Size", ['S', 'M', 'L', 'XL'], index=1, key="select_size")
    
    with col_qty:
        max_qty = product['stock'] 
        existing_item = next((item for item in st.session_state['cart'] if item['product_id'] == product['product_id'] and item['size'] == size), None)
        default_qty = existing_item['quantity'] if existing_item else 1
        
        if default_qty > max_qty:
            default_qty = max_qty
            
        quantity = st.number_input("Quantity", min_value=1, max_value=max_qty, value=default_qty, step=1, key="select_quantity")
    
    with col_add:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add to Cart"):
            # Use the product ID from the currently displayed product
            current_product_id = product['product_id']
            if quantity > 0 and quantity <= max_qty:
                
                new_total, bulk_discount = calculate_item_total(product['price'], quantity)

                new_item = {
                    'product_id': current_product_id,
                    'name': product['name'],
                    'size': size,
                    'quantity': quantity,
                    'price': product['price'], # Original unit price
                    'total': new_total, # Total after bulk discount
                    'bulk_discount': bulk_discount
                }

                cart_updated = False
                for i in range(len(st.session_state['cart'])):
                    item = st.session_state['cart'][i]
                    if item['product_id'] == current_product_id and item['size'] == size:
                        st.session_state['cart'][i].update(new_item) # Update existing item
                        cart_updated = True
                        break
                
                if not cart_updated:
                    st.session_state['cart'].append(new_item)

                st.toast(f"{quantity}x {size} {product['name']} added/updated in cart!")
            else:
                st.error("Invalid quantity or insufficient stock.")

def checkout_page():
    st.title("Checkout")

    if 'cart' not in st.session_state or not st.session_state['cart']:
        st.warning("Your cart is empty. Please add items before checking out.")
        if st.button("Go to Shop"):
            st.session_state['page'] = 'shop'
            st.rerun()
        return

    # --- Step 1: Order Summary and Shipping ---
    st.subheader("Order Summary")
        
    cart_df = pd.DataFrame(st.session_state['cart'])
    # Show bulk discount clearly
    cart_df['Unit Price'] = cart_df['price'].apply(lambda x: f"${x:.2f}")
    cart_df['Subtotal'] = (cart_df['price'] * cart_df['quantity']).apply(lambda x: f"${x:.2f}")
    cart_df['Bulk Discount'] = cart_df['bulk_discount'].apply(lambda x: f"- ${x:.2f}")
    cart_df['Final Total'] = cart_df['total'].apply(lambda x: f"${x:.2f}")
    
    display_cols = ['name', 'size', 'quantity', 'Unit Price', 'Bulk Discount', 'Final Total']
    st.dataframe(cart_df[display_cols], hide_index=True, use_container_width=True)

    subtotal_amount = cart_df['total'].sum()
    
    # Initialize discount states
    if 'coupon_code' not in st.session_state:
        st.session_state['coupon_code'] = ''
        st.session_state['coupon_discount'] = 0.0
        st.session_state['coupon_valid'] = False

    # --- Step 2: Discount Application ---
    st.subheader("Apply Coupon Code")
    col_code, col_apply = st.columns([2, 1])

    with col_code:
        coupon_input = st.text_input("Coupon Code", value=st.session_state['coupon_code'].upper(), max_chars=10, key="coupon_input")
    
    with col_apply:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Apply Discount"):
            st.session_state['coupon_code'] = coupon_input.upper()
            discount_data = get_discount(st.session_state['coupon_code'])
            
            if discount_data:
                if discount_data['discount_type'] == 'percent':
                    discount_value = subtotal_amount * (discount_data['value'] / 100)
                elif discount_data['discount_type'] == 'fixed':
                    discount_value = discount_data['value']
                
                st.session_state['coupon_discount'] = round(discount_value, 2)
                st.session_state['coupon_valid'] = True
                st.success(f"Coupon '{st.session_state['coupon_code']}' applied! Discount: -${st.session_state['coupon_discount']:.2f}")
                st.rerun()
            else:
                st.session_state['coupon_discount'] = 0.0
                st.session_state['coupon_valid'] = False
                st.error("Invalid or expired coupon code. Try 'SAVE10' or 'FIVER'.")
                st.rerun()
    
    final_payable = subtotal_amount - st.session_state['coupon_discount']
    
    st.markdown("---")
    st.metric("Total Before Coupon", f"${subtotal_amount:.2f}")
    if st.session_state['coupon_discount'] > 0:
        st.metric("Coupon Discount", f"- ${st.session_state['coupon_discount']:.2f}")
    st.markdown(f"## Final Payable: **${final_payable:.2f}**")
    
    st.subheader("Shipping Information")

    # Use session state to persist shipping info between reruns
    if 'shipping_info' not in st.session_state:
        st.session_state['shipping_info'] = {
            'full_name': st.session_state.get('username', '').capitalize() or "",
            'address': '',
            'city': '',
            'zip_code': ''
        }

    # Store inputs directly to session state on change
    full_name = st.text_input("Full Name", value=st.session_state['shipping_info']['full_name'], required=True, key="checkout_full_name")
    address = st.text_area("Shipping Address", value=st.session_state['shipping_info']['address'], required=True, key="checkout_address")
    
    col_city, col_zip = st.columns(2)
    with col_city:
        city = st.text_input("City", value=st.session_state['shipping_info']['city'], required=True, key="checkout_city")
    with col_zip:
        zip_code = st.text_input("Zip Code", value=st.session_state['shipping_info']['zip_code'], required=True, key="checkout_zip")
    
    st.session_state['shipping_info'].update({
        'full_name': full_name, 'address': address, 'city': city, 'zip_code': zip_code
    })

    # --- Step 3: Fake Payment Gateway ---
    st.subheader("Payment Details (Simulated Gateway)")
    
    if not all([full_name, address, city, zip_code]):
        st.warning("Please fill in shipping information to proceed to payment.")
        return

    with st.form("payment_form"):
        st.markdown("Enter fake payment details below.")
        card_number = st.text_input("Card Number", max_chars=16)
        col_exp, col_cvv = st.columns(2)
        with col_exp:
             expiration = st.text_input("Expiration Date (MM/YY)", max_chars=5)
        with col_cvv:
            cvv = st.text_input("CVV", type="password", max_chars=4)
        
        pay_button = st.form_submit_button(f"Pay ${final_payable:.2f} and Place Order", type="primary")

        if pay_button:
            if len(card_number) < 15 or len(expiration) != 5 or len(cvv) < 3:
                st.error("Please enter valid (fake) payment details to simulate a successful transaction.")
            else:
                success, result = place_order(
                    st.session_state['username'],
                    st.session_state['cart'],
                    final_payable, # Pass the final calculated amount
                    full_name,
                    address,
                    city,
                    zip_code
                )
                
                if success:
                    st.success(f"Payment successful! Order successfully placed! Your Order ID is: {result}")
                    st.session_state['cart'] = []
                    st.session_state['coupon_discount'] = 0.0
                    st.session_state['coupon_code'] = ''
                    st.balloons()
                    st.session_state['page'] = 'order_complete'
                    st.session_state['last_order_id'] = result
                    st.rerun()
                else:
                    st.error(f"Order failed: {result}")

def order_complete_page():
    st.title("Order Confirmed!")
    order_id = st.session_state.get('last_order_id', 'N/A')
    st.success(f"Thank you for your purchase, {st.session_state['username'].capitalize()}!")
    st.markdown(f"Your order ID is: **{order_id}**")
    st.info("You can track your order in the dashboard.")

    if st.button("Continue Shopping"):
        st.session_state['page'] = 'shop'
        st.rerun()

def admin_product_management():
    """Allows admin to add and delete products."""
    st.markdown("### 🛠️ Product Management")
    
    # --- Add Product Form ---
    with st.expander("➕ Add New Product", expanded=False):
        with st.form("add_product_form", clear_on_submit=True):
            st.subheader("Product Details")
            new_name = st.text_input("Product Name", max_chars=100)
            new_desc = st.text_area("Description")
            col_price, col_stock = st.columns(2)
            with col_price:
                new_price = st.number_input("Price ($)", min_value=0.01, format="%.2f")
            with col_stock:
                new_stock = st.number_input("Initial Stock", min_value=0, step=1)
                
            if st.form_submit_button("Add Product"):
                if new_name and new_desc and new_price > 0 and new_stock >= 0:
                    if add_product(new_name, new_desc, new_price, new_stock):
                        st.success(f"Product '{new_name}' added successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to add product.")
                else:
                    st.error("Please fill out all product details correctly.")

    # --- Delete Product Section ---
    st.markdown("---")
    st.markdown("##### Delete Existing Product")
    df_products = db_manager.fetch_query_df("SELECT product_id, name, price, stock FROM PRODUCTS")
    
    if not df_products.empty:
        # Create a dictionary for easy selection
        product_options = {f"{row['name']} (ID: {row['product_id']})": row['product_id'] for index, row in df_products.iterrows()}
        selected_product_name = st.selectbox("Select Product to Delete", list(product_options.keys()))
        
        if selected_product_name:
            product_to_delete_id = product_options[selected_product_name]
            
            if st.button(f"Delete '{selected_product_name}'", type="primary"):
                if delete_product(product_to_delete_id):
                    st.success(f"Product ID {product_to_delete_id} deleted.")
                    st.rerun()
                else:
                    st.error("Could not delete product.")
    
    st.markdown("---")
    st.markdown("##### Current Catalog")
    st.dataframe(df_products, hide_index=True, use_container_width=True)


def dashboard_page():
    st.title("User Dashboard")
    st.subheader(f"Welcome, {st.session_state['username'].capitalize()}")

    try:
        # Fetch orders for the current user
        df_orders = db_manager.fetch_query_df("SELECT order_id, order_date, total_amount, status FROM ORDERS WHERE username = ? ORDER BY order_date DESC", 
                                      params=(st.session_state['username'],))
    except Exception as e:
        st.error(f"Could not retrieve orders. Database error: {e}")
        st.info("Please try refreshing the page.")
        return

    if df_orders.empty:
        st.info("You have no past orders.")
    else:
        st.subheader("Your Order History")
        display_cols = ['order_id', 'order_date', 'total_amount', 'status']
        # Convert total_amount to currency format for better display
        df_display = df_orders.copy()
        df_display['total_amount'] = df_display['total_amount'].apply(lambda x: f"${x:.2f}")

        st.dataframe(df_display[display_cols], hide_index=True, use_container_width=True)

    if st.session_state['username'] == 'admin':
        st.subheader("Admin Panel")

        # Tab navigation for Admin features
        tab_analytics, tab_products = st.tabs(["📊 Sales & Inventory Analytics", "📦 Product Management"])
        
        with tab_products:
            admin_product_management()
        
        with tab_analytics:
            # Fetch all orders for admin
            df_all_orders = db_manager.fetch_query_df("SELECT order_id, username, order_date, total_amount, status, full_name FROM ORDERS ORDER BY order_date DESC")
            
            # --- Admin Charts Section ---
            st.markdown("### 📈 Sales Analytics & Charts")
            
            if not df_all_orders.empty:
                # Prepare data: Ensure order_date is a proper date type for charting
                df_all_orders['order_date'] = pd.to_datetime(df_all_orders['order_date']).dt.date
                
                # 1. Daily Sales Over Time (Line Chart)
                sales_daily = df_all_orders.groupby('order_date')['total_amount'].sum().reset_index()
                sales_daily.rename(columns={'total_amount': 'Daily Sales'}, inplace=True)
                
                st.markdown("#### Daily Sales Total Over Time")
                st.line_chart(sales_daily, x='order_date', y='Daily Sales')
                
                # 2. Order Status Distribution (Bar Chart - The 'VS' graph)
                status_counts = df_all_orders['status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                
                st.markdown("#### Order Status Breakdown")
                st.bar_chart(status_counts, x='Status', y='Count')
                
            else:
                st.info("No sales data available for charts.")
                
            st.markdown("#### Raw Data Tables")
            st.markdown("##### All Orders")
            st.dataframe(df_all_orders[['order_id', 'username', 'order_date', 'total_amount', 'status']], hide_index=True, use_container_width=True)
            
            # Fetch product stock for admin
            df_products = db_manager.fetch_query_df("SELECT product_id, name, price, stock FROM PRODUCTS")
            st.markdown("##### Current Stock Levels")
            st.dataframe(df_products, hide_index=True, use_container_width=True)

# --- Main App Logic ---

def main_app():
    """The main entry point for the Streamlit application."""

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['page'] = 'login' 

    if 'page' not in st.session_state:
        st.session_state['page'] = 'shop'

    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/T-shirt_Icon.svg/1024px-T-shirt_Icon.svg.png", width=100)
        st.title("Code & Thread")
        
        if st.session_state['logged_in']:
            st.markdown(f"**Logged in as:** `{st.session_state['username']}`")
            
            # Navigation links
            if st.button("🛒 Shop"):
                st.session_state['page'] = 'shop'
            if st.button("👤 Dashboard"):
                st.session_state['page'] = 'dashboard'
            if st.button("➡️ Checkout"):
                st.session_state['page'] = 'checkout'
            
            # Logout button
            if st.button("Logout", type="secondary"):
                st.session_state['logged_in'] = False
                st.session_state['username'] = None
                st.session_state['cart'] = []
                st.session_state['coupon_discount'] = 0.0 # Clear session state data
                st.session_state['coupon_code'] = ''
                st.session_state['page'] = 'login'
                st.rerun()

            # Display cart count
            cart_count = sum(item['quantity'] for item in st.session_state.get('cart', []))
            st.markdown(f"**Cart Items:** {cart_count}")
        else:
            if st.button("Login / Sign Up"):
                st.session_state['page'] = 'login'
            st.info("Please log in to shop.")

    # --- Page Routing ---
    if st.session_state['logged_in']:
        if st.session_state['page'] == 'shop':
            product_page()
        elif st.session_state['page'] == 'checkout':
            checkout_page()
        elif st.session_state['page'] == 'dashboard':
            dashboard_page()
        elif st.session_state['page'] == 'order_complete':
            order_complete_page()
        else:
            product_page()
    else:
        login_page()


if __name__ == '__main__':
    try:
        main_app()
    except Exception as e:
        st.error(f"An unexpected application error occurred. Please refresh the page. Error: {e}")
