import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import random # Needed for the discount wheel

# --- CONFIGURATION & UTILITIES ---

st.set_page_config(
    page_title="T-Shirt Inventory System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state defaults
st.session_state.setdefault('logged_in', False)
st.session_state.setdefault('username', None)
st.session_state.setdefault('role', None)

# New states for complex navigation and features
st.session_state.setdefault('current_view', 'catalog') # 'catalog', 'detail', 'profile'
st.session_state.setdefault('selected_product_id', None)
st.session_state.setdefault('checkout_stage', 'catalog') # 'catalog' or 'payment'
st.session_state.setdefault('checkout_substage', None) # 'payment_form' or 'delivered'

# Discount System States
st.session_state.setdefault('coupon_code', None)
st.session_state.setdefault('discount_rate', 0.0) # 0.0 to 1.0

# Optimization Counters for Cache Invalidation
# These counters force cached functions to re-run only when underlying data changes.
st.session_state.setdefault('product_version', 0)
st.session_state.setdefault('cart_version', 0)

@st.cache_resource
def get_db_connection():
    """
    Establishes and returns a single, cached connection to the SQLite database.
    
    IMPORTANT: check_same_thread=False is added to prevent Streamlit's threading 
    from causing SQLite ProgrammingErrors when accessing the connection across threads.
    """
    conn = sqlite3.connect('inventory.db', check_same_thread=False)
    # Use row_factory to access columns by name (optional but nice)
    conn.row_factory = sqlite3.Row 
    return conn

def hash_password(password):
    """Hashes the password for secure storage."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Initializes database tables and populates initial data."""
    conn = get_db_connection()
    c = conn.cursor()

    # Define all necessary tables
    c.executescript('''
        CREATE TABLE IF NOT EXISTS USERS (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS PRODUCTS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            size TEXT NOT NULL,
            image_url TEXT
        );
        CREATE TABLE IF NOT EXISTS CART (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES USERS(username),
            FOREIGN KEY(product_id) REFERENCES PRODUCTS(id),
            UNIQUE(user_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS ORDERS (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            total_amount REAL NOT NULL,
            tracking_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            shipping_address TEXT,
            FOREIGN KEY(user_id) REFERENCES USERS(username)
        );
    ''')
      # Add initial users
    try:
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('admin', hash_password('adminpass'), 'admin'))
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('customer1', hash_password('custpass'), 'customer'))
        conn.commit()
    except sqlite3.IntegrityError: pass # Users exist

    # Add initial products
    initial_products = [
        ("Classic Navy Tee", 24.99, "M", "https://placehold.co/150x150/1C3144/FFFFFF?text=Navy+Tee"),
        ("Summer V-Neck", 19.50, "S", "https://placehold.co/150x150/FFCC00/000000?text=Yellow+V-Neck"),
        ("Oversized Black Hoodie", 49.99, "L", "https://placehold.co/150x150/000000/FFFFFF?text=Black+Hoodie"),
        ("Striped Casual Shirt", 35.00, "XL", "https://placehold.co/150x150/93A3BC/FFFFFF?text=Striped+Shirt"),
    ]
    for name, price, size, url in initial_products:
        try:
            # Check if product exists before inserting
            c.execute("SELECT id FROM PRODUCTS WHERE name = ? AND size = ?", (name, size))
            if c.fetchone() is None:
                c.execute("INSERT INTO PRODUCTS (name, price, size, image_url) VALUES (?, ?, ?, ?)", (name, price, size, url))
                conn.commit()
        except sqlite3.IntegrityError: pass # Product exists

# --- AUTHENTICATION & SESSION ---

def authenticate(username, password):
    """Checks credentials and returns user role or None."""
    conn = get_db_connection()
    c = conn.cursor()
    hashed_password = hash_password(password)
    c.execute("SELECT role FROM USERS WHERE username = ? AND password = ?", (username, hashed_password))
    user = c.fetchone()
    return user[0] if user else None

def sign_up_user(username, password):
    """Adds a new customer user."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", (username, hash_password(password), 'customer'))
        conn.commit()
        return "Success"
    except sqlite3.IntegrityError:
        return "Username already exists. Please choose a different one."
    except Exception as e:
        return f"Database error: {e}"

def logout():
    """Logs out the user and resets all session states related to login/checkout/view."""
    st.session_state.logged_in = False
    st.session_state.username = st.session_state.role = None
    st.session_state.current_view = 'catalog'
    st.session_state.checkout_stage = 'catalog'
    st.session_state.checkout_substage = None
    st.session_state.coupon_code = None
    st.session_state.discount_rate = 0.0
    st.info("You have been logged out.")
    st.rerun()

def auth_forms():
    """Displays the login and sign up forms using tabs."""
    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    with tab_login:
        st.subheader("Existing User Login")
        with st.form("login_form", clear_on_submit=False): 
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                role = authenticate(username, password)
                if role:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = role
                    st.success(f"Welcome, {username}! Logged in as {role.capitalize()}.")
                    st.rerun()
                else: st.error("Invalid username or password.")
    
    with tab_signup:
        st.subheader("New Customer Sign Up")
        with st.form("signup_form", clear_on_submit=True):
            new_username = st.text_input("Choose Username")
            new_password = st.text_input("Choose Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            if st.form_submit_button("Create Account"):
                if new_password != confirm_password: st.error("Passwords do not match.")
                elif len(new_username) < 4 or len(new_password) < 6: st.error("Username must be at least 4 characters and password at least 6 characters.")
                else:
                    result = sign_up_user(new_username, new_password)
                    if result == "Success": st.success("Account created successfully! Please log in.")
                    else: st.error(result)

# --- ADMIN FEATURES (CRUD) ---

def admin_add_product():
    """Form to add a new product."""
    st.markdown("### 👕 Add New T-Shirt Product")
    with st.form("add_product_form"):
        name = st.text_input("Product Name")
        price = st.number_input("Price ($)", min_value=0.01, format="%.2f")
        size = st.selectbox("Size", ["XS", "S", "M", "L", "XL", "XXL"])
        image_url = st.text_input("Image URL (e.g., placeholder)")
        if st.form_submit_button("Add Product"):
            if not name or not image_url: st.error("Please fill in all fields.")
            else:
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO PRODUCTS VALUES (NULL, ?, ?, ?, ?)", (name, price, size, image_url))
                    conn.commit()
                    # CRITICAL: Increment product_version to bust the inventory cache
                    st.session_state.product_version += 1
                    st.success(f"Product '{name}' added successfully! (v{st.session_state.product_version})")
                except Exception as e: st.error(f"Error adding product: {e}")

@st.cache_data(show_spinner="Loading inventory...")
def admin_view_inventory(product_version):
    """Displays the current product inventory, cached."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)
    return df

def display_admin_inventory():
    """Wrapper function to display inventory using cached data."""
    st.markdown("### 📦 Current Inventory")
    # Inventory data is dependent on the product_version counter
    df = admin_view_inventory(st.session_state.product_version)
    
    if df.empty: st.info("The inventory is currently empty.")
    else: st.dataframe(df, column_config={"price": st.column_config.NumberColumn("Price ($)", format="$%.2f")}, hide_index=True)
    # --- CUSTOMER FEATURES ---

@st.cache_data(show_spinner="Loading cart...")
def get_user_cart(user_id, cart_version):
    """Retrieves the user's current cart items, cached by user_id and cart_version."""
    conn = get_db_connection()
    query = """
    SELECT T1.id AS cart_item_id, T2.id AS product_id, T2.name, T2.price, T1.quantity, T2.size, T2.image_url
    FROM CART AS T1 JOIN PRODUCTS AS T2 ON T1.product_id = T2.id
    WHERE T1.user_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    return df

def add_to_cart(product_id, quantity):
    pass
