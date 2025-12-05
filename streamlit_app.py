import streamlit as st
import sqlite3
import hashlib
import uuid
import datetime
import pandas as pd
import requests
import json
from io import BytesIO

# --- Constants and Configuration (unchanged) ---
# Assuming these are correct from your previous file
DB_NAME = 'tshirt_shop.db'
PRODUCT_ID = 1  # Fixed ID for the single T-shirt product

# --- Database Management (unchanged or previously fixed) ---

# This function might need to be moved to global scope or a different pattern
# if it's still causing the "database is locked" error, but for now,
# we'll assume the previous threading fixes were applied.
def get_db_connection():
    # Streamlit recommends using a memoized function for database connection
    # to handle retries and connection sharing across script reruns.
    # Note: If you still see 'database is locked', you may need to ensure
    # that init_db() is idempotent and not called multiple times concurrently.
    if 'db_conn' not in st.session_state:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        st.session_state['db_conn'] = conn
    return st.session_state['db_conn']

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT password_hash FROM USERS WHERE username = ?", (username,))
    result = c.fetchone()
    if result:
        return result[0] == hash_password(password)
    return False

def add_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", (username, hash_password(password), 'customer'))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_product_details(product_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM PRODUCTS WHERE product_id = ?", (product_id,))
    row = c.fetchone()
    if row:
        return {'product_id': row[0], 'name': row[1], 'description': row[2], 'price': row[3], 'stock': row[4]}
    return None

# Placeholder function for database initialization (keep it idempotent)
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Define all necessary tables
    c.executescript('''
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
    ''')
    conn.commit()

    # Add initial users
    try:
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('admin', hash_password('admin'), 'admin'))
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('customer1', hash_password('customer1'), 'customer'))
        conn.commit()
    except sqlite3.IntegrityError: pass

    # Add initial product data if not present
    product_data = get_product_details(PRODUCT_ID)
    if product_data is None:
        try:
            c.execute("INSERT INTO PRODUCTS VALUES (?, ?, ?, ?, ?)",
                      (PRODUCT_ID, 'Vintage Coding Tee', 'A comfortable cotton t-shirt for developers.', 25.00, 100))
            conn.commit()
        except sqlite3.IntegrityError: pass


def place_order(username, cart_items, total_amount, full_name, address, city, zip_code):
    conn = get_db_connection()
    c = conn.cursor()
    order_id = str(uuid.uuid4())
    order_date = datetime.datetime.now().isoformat()

    try:
        # Start transaction
        conn.execute('BEGIN TRANSACTION')

        # 1. Insert into ORDERS table
        c.execute("INSERT INTO ORDERS (order_id, username, order_date, total_amount, status) VALUES (?, ?, ?, ?, ?)",
                  (order_id, username, order_date, total_amount, 'Processing'))

        # 2. Insert into ORDER_ITEMS and update stock
        for item in cart_items:
            product = get_product_details(item['product_id'])
            if product and product['stock'] >= item['quantity']:
                # Insert item
                c.execute("INSERT INTO ORDER_ITEMS (order_id, product_id, size, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
                          (order_id, item['product_id'], item['size'], item['quantity'], item['price']))

                # Update stock
                new_stock = product['stock'] - item['quantity']
                c.execute("UPDATE PRODUCTS SET stock = ? WHERE product_id = ?", (new_stock, item['product_id']))
            else:
                conn.execute('ROLLBACK')
                return False, "Error: Insufficient stock for product ID {}".format(item['product_id'])

        # 3. Insert into a hypothetical SHIPPING_INFO table (optional, but good practice for checkout info)
        # We'll just store this info in a list for now, but a real app needs a dedicated table.

        conn.commit()
        return True, order_id

    except Exception as e:
        conn.execute('ROLLBACK')
        st.error(f"Database error during order placement: {e}")
        return False, f"Order failed due to an internal error. {e}"


# --- Streamlit Page Functions ---

def login_page():
    # ... (login page logic, assumed correct)
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
                    st.success("Account created! You can now log in.")
                else:
                    st.error("Username already exists.")

def product_page():
    # ... (product page logic, assumed correct)
    st.title("T-Shirt Store")

    product = get_product_details(PRODUCT_ID)
    if not product:
        st.error("Product not found.")
        return

    st.subheader(product['name'])
    st.write(product['description'])
    st.markdown(f"**Price:** ${product['price']:.2f}")
    st.markdown(f"**Stock:** {product['stock']} available")

    # Image placeholder
    st.image("https://placehold.co/400x400/36454F/FFFFFF?text=Awesome+Code+Tee", caption="Our Awesome T-Shirt Design", use_column_width=False)

    st.subheader("Select Options")
    
    # Initialize cart if it doesn't exist
    if 'cart' not in st.session_state:
        st.session_state['cart'] = []

    # Get the existing item in cart, if any, for pre-filling
    existing_item = next((item for item in st.session_state['cart'] if item['product_id'] == PRODUCT_ID), None)

    col_size, col_qty, col_add = st.columns([1, 1, 1])

    with col_size:
        size = st.selectbox("Size", ['S', 'M', 'L', 'XL'], index=1)
    
    with col_qty:
        # Use existing quantity or default to 1
        default_qty = existing_item['quantity'] if existing_item else 1
        quantity = st.number_input("Quantity", min_value=1, max_value=product['stock'], value=default_qty, step=1)
    
    with col_add:
        st.markdown("<br>", unsafe_allow_html=True) # Add vertical space
        if st.button("Add to Cart"):
            if quantity > 0 and quantity <= product['stock']:
                # Create the item dict
                new_item = {
                    'product_id': PRODUCT_ID,
                    'name': product['name'],
                    'size': size,
                    'quantity': quantity,
                    'price': product['price'],
                    'total': quantity * product['price']
                }

                # Update cart: remove old entry for this product and size, then add new one
                st.session_state['cart'] = [item for item in st.session_state['cart'] if not (item['product_id'] == PRODUCT_ID and item['size'] == size)]
                st.session_state['cart'].append(new_item)
                
                st.toast(f"{quantity}x {size} {product['name']} added to cart!")
            else:
                st.error("Invalid quantity.")

def checkout_page():
    st.title("Checkout")

    if 'cart' not in st.session_state or not st.session_state['cart']:
        st.warning("Your cart is empty. Please add items before checking out.")
        if st.button("Go to Shop"):
            st.session_state['page'] = 'shop'
            st.rerun()
        return

    st.subheader("Order Summary")
    cart_df = pd.DataFrame(st.session_state['cart'])
    cart_df['Unit Price'] = cart_df['price'].apply(lambda x: f"${x:.2f}")
    cart_df['Total Price'] = cart_df['total'].apply(lambda x: f"${x:.2f}")
    display_cols = ['name', 'size', 'quantity', 'Unit Price', 'Total Price']
    st.dataframe(cart_df[display_cols], hide_index=True, use_container_width=True)

    total_amount = cart_df['total'].sum()
    st.markdown(f"### Grand Total: **${total_amount:.2f}**")
    
    st.subheader("Shipping Information")

    # FIX: Use st.form and st.form_submit_button() here to submit the checkout details.
    # This addresses the 'Missing Submit Button' error.
    with st.form("checkout_form"):
        # Pre-fill name from session state if available
        # The .capitalize() should be safe if 'username' is in session_state,
        # but we'll use a try/except or default value for robustness.
        default_name = st.session_state.get('username', '').capitalize() or ""

        full_name = st.text_input("Full Name", value=default_name, required=True, key="checkout_full_name")
        address = st.text_area("Shipping Address", required=True, key="checkout_address")
        
        col_city, col_zip = st.columns(2)
        with col_city:
            city = st.text_input("City", required=True, key="checkout_city")
        with col_zip:
            zip_code = st.text_input("Zip Code", required=True, key="checkout_zip")
        
        # MANDATORY SUBMIT BUTTON FOR THE FORM
        submitted = st.form_submit_button("Complete Order")

        if submitted:
            # Check for required fields (Streamlit's required=True does client-side checks, but good to double-check)
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
                    # Clear the cart and navigate to the order confirmation page or shop
                    st.session_state['cart'] = []
                    st.balloons()
                    st.session_state['page'] = 'order_complete'
                    st.session_state['last_order_id'] = result
                    st.rerun()
                else:
                    st.error(f"Failed to place order: {result}")


def order_complete_page():
    st.title("Order Confirmed!")
    order_id = st.session_state.get('last_order_id', 'N/A')
    st.success(f"Thank you for your purchase, {st.session_state['username'].capitalize()}!")
    st.markdown(f"Your order ID is: **{order_id}**")
    st.info("You will receive a confirmation email shortly. You can track your order in the dashboard.")

    if st.button("Continue Shopping"):
        st.session_state['page'] = 'shop'
        st.rerun()

def dashboard_page():
    # ... (dashboard page logic, assumed correct)
    st.title("User Dashboard")
    st.subheader(f"Welcome, {st.session_state['username'].capitalize()}")

    conn = get_db_connection()
    df_orders = pd.read_sql_query(f"SELECT order_id, order_date, total_amount, status FROM ORDERS WHERE username = '{st.session_state['username']}' ORDER BY order_date DESC", conn)

    if df_orders.empty:
        st.info("You have no past orders.")
    else:
        st.subheader("Your Order History")
        st.dataframe(df_orders, hide_index=True, use_container_width=True)

    if st.session_state['username'] == 'admin':
        st.subheader("Admin Panel")
        df_all_orders = pd.read_sql_query("SELECT * FROM ORDERS", conn)
        df_products = pd.read_sql_query("SELECT * FROM PRODUCTS", conn)
        
        st.markdown("#### All Orders")
        st.dataframe(df_all_orders, hide_index=True, use_container_width=True)
        
        st.markdown("#### Product Stock")
        st.dataframe(df_products, hide_index=True, use_container_width=True)

# --- Main App Logic ---

def main_app():
    """The main entry point for the Streamlit application."""
    # Initialize DB (only run once per session using st.cache_resource)
    if 'db_initialized' not in st.session_state:
        init_db()
        st.session_state['db_initialized'] = True

    # Initialize session state variables
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['page'] = 'login' # Start at login page

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
    main_app()
