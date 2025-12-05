import streamlit as st
import sqlite3
import hashlib
import uuid
import datetime
import pandas as pd
from threading import Lock
import os
import time

# --- Constants and Configuration ---
DB_NAME = 'tshirt_shop.db'
PRODUCT_ID = 1  # Fixed ID for the single T-shirt product
MAX_RETRIES = 5
RETRY_DELAY_SEC = 1.0 # Increased delay for higher resilience

# --- Database Cleanup (Run before @st.cache_resource) ---
def clean_locked_db(db_path):
    """Attempts to remove a locked database file."""
    if os.path.exists(db_path):
        try:
            # Attempt a connection with a very short timeout (microsecond level)
            # If this fails, the file is likely locked by another process
            test_conn = sqlite3.connect(db_path, timeout=0.001)
            test_conn.close()
            return False # Not locked
        except sqlite3.OperationalError:
            # If a lock is detected, try to delete the file
            try:
                os.remove(db_path)
                st.toast("Locked database file successfully removed for fresh start.")
                return True
            except Exception as file_error:
                # If removal fails (e.g., file is actively open), just report the error
                st.warning(f"Database file '{db_path}' is locked and could not be removed: {file_error}")
                return False
        except Exception:
            return False

# Aggressively try to clean the file at startup before anything else runs
clean_locked_db(DB_NAME)

# --- Database Management Class (Maximum Resilience) ---
class DBManager:
    """
    Manages the SQLite connection and enforces thread safety using a Lock.
    Includes aggressive retry logic for startup and a 60-second connection timeout.
    """
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = Lock()
        self._conn = self._get_connection()
        self._initialize_db_with_retry() # Use the new retry method

    def _get_connection(self):
        """Creates or returns the connection, ensuring only one connection exists."""
        # CRITICAL FIX: Set connection timeout to 60 seconds (up from 30) 
        # to aggressively wait out any startup locks.
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row # Ensure we can access columns by name
        return conn

    def _initialize_db_with_retry(self):
        """
        Retries database initialization if an OperationalError occurs,
        specifically targeting the race condition during Streamlit startup.
        """
        for attempt in range(MAX_RETRIES):
            try:
                self._initialize_db()
                return # Success
            except sqlite3.OperationalError as e:
                if 'database is locked' in str(e) or 'timeout' in str(e):
                    if attempt < MAX_RETRIES - 1:
                        st.warning(f"Database locked during initialization. Retrying in {RETRY_DELAY_SEC}s... (Attempt {attempt + 1}/{MAX_RETRIES})")
                        time.sleep(RETRY_DELAY_SEC)
                    else:
                        st.error("CRITICAL: Failed to initialize database after multiple retries. The application cannot start.")
                        # This re-raises the error if all attempts fail
                        raise e
                else:
                    # Raise other OperationalErrors immediately
                    raise e
            except Exception as e:
                # Raise other exceptions immediately
                raise e

    def _initialize_db(self):
        """Creates tables and populates initial data idempotently."""
        conn = self._conn
        c = conn.cursor()
        
        # 1. Define all necessary tables using IF NOT EXISTS
        c.execute('''
            CREATE TABLE IF NOT EXISTS USERS (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                role TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS PRODUCTS (
                product_id INTEGER PRIMARY KEY,
                name TEXT,
                description TEXT,
                price REAL,
                stock INTEGER
            )
        ''')
        
        c.execute('''
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
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                product_id INTEGER,
                size TEXT,
                quantity INTEGER,
                unit_price REAL,
                FOREIGN KEY (order_id) REFERENCES ORDERS(order_id),
                FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
            )
        ''')
        conn.commit()

        # 2. Add initial users (Idempotent check)
        c.execute("SELECT COUNT(*) FROM USERS WHERE username = 'admin'")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('admin', hash_password('admin'), 'admin'))
            c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('customer1', hash_password('customer1'), 'customer'))
            conn.commit()

        # 3. Add initial product data (Idempotent check)
        # This is the line that keeps crashing, now protected by the aggressive retry/timeout mechanism.
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
                # pandas.read_sql_query uses the connection instance safely
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
    # If initialization fails even after retries, display a critical error
    st.error(f"Critical Error: Database initialization failed. Please try refreshing the app. Error Details: {e}")
    st.stop() # Stop the script execution

# --- Helper Functions Adapted to DBManager ---

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    try:
        users = db_manager.fetch_query("SELECT password_hash FROM USERS WHERE username = ?", (username,))
        if users:
            # users[0] is an sqlite3.Row object, access by name
            return users[0]['password_hash'] == hash_password(password)
        return False
    except Exception as e:
        # Suppress for cleaner UI, only log if needed
        # st.error(f"Error verifying user: {e}") 
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
    except Exception as e:
        st.error(f"Error adding user: {e}")
        return False

def get_product_details(product_id):
    try:
        products = db_manager.fetch_query("SELECT * FROM PRODUCTS WHERE product_id = ?", (product_id,))
        if products:
            row = products[0]
            # Accessing columns by name using the set row_factory
            return {'product_id': row['product_id'], 'name': row['name'], 'description': row['description'], 'price': row['price'], 'stock': row['stock']}
    except Exception as e:
        # Suppress for cleaner UI, only log if needed
        # st.error(f"Error accessing product details: {e}. Try refreshing.")
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
                # Stock check MUST use the correct column name 'stock'
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
         # Lock is handled by the DBManager, this usually means a timeout or IO issue
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
        # Fetch order history using the DBManager's thread-safe method
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
        
        # Load all orders for admin
        df_all_orders = db_manager.fetch_query_df("SELECT order_id, username, order_date, total_amount, status, full_name, address, city, zip_code FROM ORDERS")
        st.markdown("#### All Orders")
        st.dataframe(df_all_orders, hide_index=True, use_container_width=True)
        
        # Load products for admin
        df_products = db_manager.fetch_query_df("SELECT product_id, name, price, stock FROM PRODUCTS")
        st.markdown("#### Product Stock")
        st.dataframe(df_products, hide_index=True, use_container_width=True)

# --- Main App Logic ---

def main_app():
    """The main entry point for the Streamlit application."""
    
    # DB Manager is initialized and ready due to @st.cache_resource

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


# The execution point of the script
if __name__ == '__main__':
    # This try/except block wraps the main app run to handle high-level errors
    try:
        main_app()
    except Exception as e:
        # Generic catch-all for anything outside of the database logic
        st.error(f"An unexpected application error occurred. Please refresh the page. Error: {e}")
