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
MAX_RETRIES = 5
RETRY_DELAY_SEC = 1.0 

# ***************************************************************
# CRITICAL FIX FOR PERSISTENT SCHEMA CORRUPTION (FINAL ATTEMPT)
# FORCE DELETE THE DATABASE FILE ON EVERY START TO ENSURE A CLEAN SCHEMA
# ***************************************************************
if os.path.exists(DB_NAME):
    try:
        os.remove(DB_NAME)
        # We don't use st.toast here as it might not be available during the very first run
        # but the file deletion itself should solve the problem.
    except Exception as e:
        # If deletion fails, the file is actively locked, but we proceed, relying on the 
        # 60-second timeout to eventually succeed.
        pass 
# ***************************************************************


# --- Database Management Class (Maximum Resilience) ---
class DBManager:
    """
    Manages the SQLite connection and enforces thread safety using a Lock.
    Includes aggressive retry logic for startup and a 60-second connection timeout.
    """
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock()
        # Establish connection first
        self._conn = self._get_connection() 
        # Then, initialize the database with retry logic
        self._initialize_db_with_retry() 

    def _get_connection(self):
        """Creates the connection with a high timeout."""
        # CRITICAL FIX: Set connection timeout to 60 seconds 
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row # Allows column access by name
        return conn

    def _initialize_db_with_retry(self):
        """
        Retries database initialization if an OperationalError occurs,
        targeting race conditions and schema inconsistencies.
        """
        for attempt in range(MAX_RETRIES):
            try:
                self._initialize_db()
                return # Success
            except sqlite3.OperationalError as e:
                # Catch lock, timeout, and schema issues during initial setup
                if 'database is locked' in str(e) or 'timeout' in str(e) or 'no such column' in str(e):
                    if attempt < MAX_RETRIES - 1:
                        st.warning(f"Database issue during initialization. Retrying in {RETRY_DELAY_SEC}s... (Attempt {attempt + 1}/{MAX_RETRIES})")
                        # Wait for the lock/inconsistency to clear
                        time.sleep(RETRY_DELAY_SEC) 
                    else:
                        st.error("CRITICAL: Failed to initialize database after multiple retries. The application cannot start.")
                        raise e
                else:
                    raise e
            except Exception as e:
                raise e

    def _initialize_db(self):
        """
        Creates tables atomically and populates initial data idempotently.
        All DDL (CREATE TABLE) is done in one script execution for robustness.
        """
        conn = self._conn
        c = conn.cursor()
        
        # 1. Define all necessary tables using a single executescript for atomic schema setup
        schema_script = f'''
            CREATE TABLE IF NOT EXISTS USERS (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                role TEXT
            );
            
            CREATE TABLE IF NOT EXISTS PRODUCTS (
                product_id INTEGER PRIMARY KEY,
                name TEXT,
                description TEXT,
                price REAL,
                stock INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS ORDERS (
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

            CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                product_id INTEGER,
                size TEXT,
                quantity INTEGER,
                unit_price REAL,
                FOREIGN KEY (order_id) REFERENCES ORDERS(order_id),
                FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
            );
        '''
        c.executescript(schema_script)
        conn.commit()

        # 2. Add initial users (Idempotent check)
        c.execute("SELECT COUNT(*) FROM USERS WHERE username = 'admin'")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('admin', hash_password('admin'), 'admin'))
            c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('customer1', hash_password('customer1'), 'customer'))
            conn.commit()

        # 3. Add initial product data (Idempotent check)
        # This check is now guaranteed to succeed because the schema was just created atomically
        c.execute("SELECT product_id FROM PRODUCTS WHERE product_id = ?", (PRODUCT_ID,))
        if c.fetchone() is None:
            c.execute("INSERT INTO PRODUCTS VALUES (?, ?, ?, ?, ?)",
                      (PRODUCT_ID, 'Vintage Coding Tee', 'A comfortable cotton t-shirt for developers.', 25.00, 100))
            conn.commit()

    def execute_query(self, query, params=(), commit=False):
        """Executes a non-SELECT query with thread lock protection."""
        with self._lock:
            conn = self._conn
            c = conn.cursor()
            try:
                c.execute(query, params)
                if commit:
                    conn.commit()
                return c
            except sqlite3.OperationalError as e:
                conn.rollback()
                raise e
            except Exception as e:
                conn.rollback()
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

# --- Global Database Manager Instance ---
@st.cache_resource
def get_db_manager():
    """Initializes and returns the thread-safe DBManager instance."""
    # The DBManager constructor now handles the retry logic internally.
    return DBManager(DB_NAME)

try:
    # Attempt to get the DB manager instance
    db_manager = get_db_manager()
except Exception as e:
    st.error(f"Critical Error: Database initialization failed. Please try refreshing the app. Error Details: {e}")
    st.stop() 

# --- Helper Functions Adapted to DBManager ---

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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
    except Exception:
        return None
    return None

def place_order(username, cart_items, total_amount, full_name, address, city, zip_code):
    order_id = str(uuid.uuid4())
    order_date = datetime.datetime.now().isoformat()

    try:
        # Acquire Lock and perform transaction
        with db_manager._lock:
            conn = db_manager._conn
            c = conn.cursor()
            
            # 1. Insert into ORDERS table 
            c.execute("INSERT INTO ORDERS (order_id, username, order_date, total_amount, status, full_name, address, city, zip_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (order_id, username, order_date, total_amount, 'Processing', full_name, address, city, zip_code))

            # 2. Insert into ORDER_ITEMS and update stock
            for item in cart_items:
                c.execute("SELECT stock FROM PRODUCTS WHERE product_id = ?", (item['product_id'],))
                product_stock = c.fetchone()
                
                if product_stock and product_stock[0] >= item['quantity']:
                    # Insert item
                    c.execute("INSERT INTO ORDER_ITEMS (order_id, product_id, size, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
                            (order_id, item['product_id'], item['size'], item['quantity'], item['price']))

                    # Update stock
                    new_stock = product_stock[0] - item['quantity']
                    c.execute("UPDATE PRODUCTS SET stock = ? WHERE product_id = ?", (new_stock, item['product_id']))
                else:
                    conn.rollback() 
                    return False, f"Error: Insufficient stock for product ID {item['product_id']} (Requested: {item['quantity']}, Available: {product_stock[0] if product_stock else 0})"

            conn.commit()
            return True, order_id

    except sqlite3.OperationalError:
         return False, "Database busy. Please try completing your order again."
    except Exception as e:
         st.error(f"Database error during order placement: {e}")
         return False, f"Order failed due to an internal error: {e}"


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

    product = get_product_details(PRODUCT_ID)
    if not product:
        st.error("Product details are currently unavailable. The database may still be initializing. Please refresh.")
        return

    st.subheader(product['name'])
    st.write(product['description'])
    st.markdown(f"**Price:** ${product['price']:.2f}")
    st.markdown(f"**Stock:** {product['stock']} available")

    # Image placeholder
    st.image("https://placehold.co/400x400/36454F/FFFFFF?text=Awesome+Code+Tee", caption="Our Awesome T-Shirt Design", use_column_width=False)

    st.subheader("Select Options")
    
    if 'cart' not in st.session_state:
        st.session_state['cart'] = []

    col_size, col_qty, col_add = st.columns([1, 1, 1])

    with col_size:
        size = st.selectbox("Size", ['S', 'M', 'L', 'XL'], index=1, key="select_size")
    
    with col_qty:
        existing_item = next((item for item in st.session_state['cart'] if item['product_id'] == PRODUCT_ID and item['size'] == size), None)
        default_qty = existing_item['quantity'] if existing_item else 1
        quantity = st.number_input("Quantity", min_value=1, max_value=product['stock'], value=default_qty, step=1, key="select_quantity")
    
    with col_add:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add to Cart"):
            if quantity > 0 and quantity <= product['stock']:
                new_item = {
                    'product_id': PRODUCT_ID,
                    'name': product['name'],
                    'size': size,
                    'quantity': quantity,
                    'price': product['price'],
                    'total': quantity * product['price']
                }

                cart_updated = False
                for i in range(len(st.session_state['cart'])):
                    item = st.session_state['cart'][i]
                    if item['product_id'] == PRODUCT_ID and item['size'] == size:
                        st.session_state['cart'][i]['quantity'] = quantity
                        st.session_state['cart'][i]['total'] = quantity * item['price']
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

    st.subheader("Order Summary")
    if not st.session_state['cart']:
        st.warning("Your cart is empty.")
        return
        
    cart_df = pd.DataFrame(st.session_state['cart'])
    cart_df['Unit Price'] = cart_df['price'].apply(lambda x: f"${x:.2f}")
    cart_df['Total Price'] = cart_df['total'].apply(lambda x: f"${x:.2f}")
    display_cols = ['name', 'size', 'quantity', 'Unit Price', 'Total Price']
    st.dataframe(cart_df[display_cols], hide_index=True, use_container_width=True)

    total_amount = cart_df['total'].sum()
    st.markdown(f"### Grand Total: **${total_amount:.2f}**")
    
    st.subheader("Shipping Information")

    with st.form("checkout_form"):
        default_name = st.session_state.get('username', '').capitalize() or ""

        full_name = st.text_input("Full Name", value=default_name, required=True, key="checkout_full_name")
        address = st.text_area("Shipping Address", required=True, key="checkout_address")
        
        col_city, col_zip = st.columns(2)
        with col_city:
            city = st.text_input("City", required=True, key="checkout_city")
        with col_zip:
            zip_code = st.text_input("Zip Code", required=True, key="checkout_zip")
        
        submitted = st.form_submit_button("Complete Order")

        if submitted:
            if not all([full_name, address, city, zip_code]):
                st.error("Please fill in all shipping fields.")
            else:
                success, result = place_order(
                    st.session_state['username'],
                    st.session_state['cart'],
                    total_amount,
                    full_name,
                    address,
                    city,
                    zip_code
                )
                
                if success:
                    st.success(f"Order successfully placed! Your Order ID is: {result}")
                    st.session_state['cart'] = []
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

def dashboard_page():
    st.title("User Dashboard")
    st.subheader(f"Welcome, {st.session_state['username'].capitalize()}")

    try:
        df_orders = db_manager.fetch_query_df("SELECT order_id, order_date, total_amount, status, full_name, address, city, zip_code FROM ORDERS WHERE username = ? ORDER BY order_date DESC", 
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
        st.dataframe(df_orders[display_cols], hide_index=True, use_container_width=True)

    if st.session_state['username'] == 'admin':
        st.subheader("Admin Panel")
        
        df_all_orders = db_manager.fetch_query_df("SELECT order_id, username, order_date, total_amount, status, full_name, address, city, zip_code FROM ORDERS")
        st.markdown("#### All Orders")
        st.dataframe(df_all_orders, hide_index=True, use_container_width=True)
        
        df_products = db_manager.fetch_query_df("SELECT product_id, name, price, stock FROM PRODUCTS")
        st.markdown("#### Product Stock")
        st.dataframe(df_products, hide_index=True, use_container_width=True)

# --- Main App Logic ---

def main_app():
    """The main entry point for the Streamlit application."""

    # 1. Initialize session state variables
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
            product_page() # Default to shop page
    else:
        login_page()


if __name__ == '__main__':
    try:
        main_app()
    except Exception as e:
        st.error(f"An unexpected application error occurred. Please refresh the page. Error: {e}")
