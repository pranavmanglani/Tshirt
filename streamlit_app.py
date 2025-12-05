import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import random
import time
import base64
import sys 
from datetime import date

# --- CONFIGURATION & UTILITIES ---

# Set page configuration at the very start
st.set_page_config(
    page_title="T-Shirt Inventory System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state defaults
st.session_state.setdefault('logged_in', False)
st.session_state.setdefault('username', None)
st.session_state.setdefault('role', None)

# States for complex navigation and features
st.session_state.setdefault('current_view', 'catalog') # 'catalog', 'detail', 'profile', 'admin_products', 'admin_inventory', 'admin_performance'
st.session_state.setdefault('selected_product_id', None)
st.session_state.setdefault('checkout_stage', 'catalog') 
st.session_state.setdefault('checkout_substage', None)
st.session_state.setdefault('coupon_code', None)
st.session_state.setdefault('discount_rate', 0.0) 

# Optimization Counters for Cache Invalidation
st.session_state.setdefault('product_version', 0)
st.session_state.setdefault('inventory_version', 0) 
st.session_state.setdefault('cart_version', 0)
st.session_state.setdefault('order_version', 0) 

def hash_password(password):
    """Hashes the password for secure storage."""
    return hashlib.sha256(password.encode()).hexdigest()

def image_to_base64(uploaded_file):
    """Converts uploaded file buffer to a Base64 string for database storage."""
    if uploaded_file is None:
        return None
    try:
        uploaded_file.seek(0) # Ensure we read from the start
        return base64.b64encode(uploaded_file.read()).decode('utf-8')
    except Exception:
        # Handle cases where the file might be large or corrupted
        return None

def b64_to_image_html(b64_string, width=150):
    """Generates HTML/Markdown to display a Base64 image."""
    if not b64_string:
        return f'<img src="https://placehold.co/{width}x{width}/93A3BC/FFFFFF?text=No+Image" width="{width}" style="border-radius: 8px; object-fit: cover; aspect-ratio: 1/1;">'
    return f'<img src="data:image/png;base64,{b64_string}" width="{width}" style="border-radius: 8px; object-fit: cover; aspect-ratio: 1/1;">'

# --- SAFE DATABASE INITIALIZATION (The Fix) ---
# NOTE: Renaming the DB file to force a clean start after previous corruption/locks.
DB_FILENAME = 'tshirt_shop.db' 

@st.cache_resource
def get_db_connection():
    """
    Establishes, caches, and initializes the SQLite database connection.
    This function runs only once across all sessions, solving the threading conflict.
    """
    try:
        # check_same_thread=False is crucial for Streamlit's multi-threaded environment.
        # timeout=10 is added for robust connection attempts.
        conn = sqlite3.connect(DB_FILENAME, check_same_thread=False, timeout=10) 
        conn.row_factory = sqlite3.Row 
        
        # Initialize schema and data
        _initialize_db_schema_and_data(conn)
        
        return conn
    except Exception as e:
        # Log and display fatal error if connection fails
        st.error(f"FATAL DB ERROR: Could not connect to or initialize database '{DB_FILENAME}'. Reason: {e}")
        # To prevent the application from continuing with a non-existent database object
        sys.exit(1) # Stop the script on fatal error

def _initialize_db_schema_and_data(conn):
    """Initializes schema and populates mock data if needed."""
    c = conn.cursor()
    
    # Execute DDL/Schema changes (IF NOT EXISTS makes it safe to call repeatedly)
    c.executescript('''
        CREATE TABLE IF NOT EXISTS USERS (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            profile_picture_b64 TEXT,
            birthday TEXT
        );
        CREATE TABLE IF NOT EXISTS PRODUCTS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            description TEXT,
            base_image_b64 TEXT
        );
        CREATE TABLE IF NOT EXISTS INVENTORY (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            size TEXT NOT NULL,
            quantity_in_stock INTEGER NOT NULL,
            manufacturing_cost REAL NOT NULL,
            selling_price REAL NOT NULL,
            FOREIGN KEY(product_id) REFERENCES PRODUCTS(id),
            UNIQUE(product_id, size)
        );
        CREATE TABLE IF NOT EXISTS CART (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            inventory_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES USERS(username),
            FOREIGN KEY(inventory_id) REFERENCES INVENTORY(id),
            UNIQUE(user_id, inventory_id)
        );
        CREATE TABLE IF NOT EXISTS ORDERS (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            total_amount REAL NOT NULL,
            tracking_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            shipping_address TEXT,
            discount_rate REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES USERS(username)
        );
        CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            inventory_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_selling_price REAL NOT NULL,
            unit_manufacturing_cost REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES ORDERS(order_id),
            FOREIGN KEY(inventory_id) REFERENCES INVENTORY(id)
        );
    ''')
    
    # --- SAFE INITIAL DATA INSERTION ---
    try:
        # Add initial users (using INSERT OR IGNORE)
        c.execute("INSERT OR IGNORE INTO USERS (username, password, role) VALUES (?, ?, ?)", ('admin', hash_password('adminpass'), 'admin'))
        c.execute("INSERT OR IGNORE INTO USERS (username, password, role) VALUES (?, ?, ?)", ('customer1', hash_password('custpass'), 'customer'))
        
        # Add initial products (using INSERT OR IGNORE)
        initial_products_data = [
            ("Classic Navy Tee", "T-Shirt", "A basic, comfortable navy tee, perfect for everyday wear.", None),
            ("Summer V-Neck", "T-Shirt", "Lightweight yellow V-neck, great for hot weather.", None),
            ("Code Debugger Hoodie", "Hoodie", "Warm hoodie for those late-night coding sessions.", None),
            ("Algorithm Logo Tee", "T-Shirt", "Abstract design based on a sorting algorithm.", None),
        ]
        for name, category, desc, b64_img in initial_products_data:
            c.execute("INSERT OR IGNORE INTO PRODUCTS (name, category, description, base_image_b64) VALUES (?, ?, ?, ?)", 
                      (name, category, desc, b64_img))
        
        conn.commit()
        
        # Now, add inventory items using the newly created product IDs
        product1 = c.execute("SELECT id FROM PRODUCTS WHERE name = 'Classic Navy Tee'").fetchone()
        product2 = c.execute("SELECT id FROM PRODUCTS WHERE name = 'Summer V-Neck'").fetchone()

        if product1 and product2:
            product1_id = product1['id']
            product2_id = product2['id']
            
            inventory1_data = [
                (product1_id, "S", 50, 100.00, 249.99), # product_id, size, stock, cost, price
                (product1_id, "M", 100, 100.00, 249.99),
                (product1_id, "L", 75, 105.00, 269.99),
            ]
            inventory2_data = [
                (product2_id, "S", 25, 90.00, 199.50),
                (product2_id, "M", 40, 95.00, 219.50),
            ]
            
            for pid, size, stock, cost, price in inventory1_data + inventory2_data:
                # Use INSERT OR IGNORE which is safer
                c.execute("""
                    INSERT OR IGNORE INTO INVENTORY (product_id, size, quantity_in_stock, manufacturing_cost, selling_price) 
                    VALUES (?, ?, ?, ?, ?)
                """, (pid, size, stock, cost, price))
            
            conn.commit()

    except sqlite3.IntegrityError: 
        # Data already exists, which is fine
        pass
    except Exception as e:
        # Catch any remaining errors and rollback
        st.warning(f"Error populating initial data (this might be fine if data already exists): {e}")
        conn.rollback()

# --- AUTHENTICATION & SESSION ---

def authenticate(username, password):
    """Checks credentials and returns user role or None."""
    conn = get_db_connection()
    c = conn.cursor()
    hashed_password = hash_password(password)
    c.execute("SELECT role FROM USERS WHERE username = ? AND password = ?", (username, hashed_password))
    user = c.fetchone()
    return user['role'] if user else None

def sign_up_user(username, password):
    """Adds a new customer user."""
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO USERS (username, password, role, profile_picture_b64, birthday) VALUES (?, ?, ?, NULL, NULL)", 
                  (username, hash_password(password), 'customer'))
        conn.commit()
        return "Success"
    except sqlite3.IntegrityError:
        return "Username already exists. Please choose a different one."
    except Exception as e:
        return f"Database error: {e}"

def logout():
    """Clears session state and logs out the user."""
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.current_view = 'catalog'
    st.session_state.checkout_stage = 'catalog'
    st.session_state.coupon_code = None
    st.session_state.discount_rate = 0.0
    st.cache_data.clear() # Clear all data caches
    st.rerun()

def auth_forms():
    """Handles login and signup forms."""
    if not st.session_state.logged_in:
        st.subheader("Login")
        with st.form("login_form"):
            login_username = st.text_input("Username (e.g., admin or customer1)")
            login_password = st.text_input("Password (e.g., adminpass or custpass)", type="password")
            if st.form_submit_button("Log In", use_container_width=True, type="primary"):
                role = authenticate(login_username, login_password)
                if role:
                    st.session_state.logged_in = True
                    st.session_state.username = login_username
                    st.session_state.role = role
                    st.session_state.current_view = 'catalog' # Reset view on login
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        
        st.markdown("---")
        st.subheader("Sign Up")
        with st.form("signup_form"):
            signup_username = st.text_input("New Username")
            signup_password = st.text_input("New Password", type="password")
            if st.form_submit_button("Create Customer Account", use_container_width=True):
                if len(signup_username) < 4 or len(signup_password) < 6:
                    st.warning("Username must be at least 4 characters and password 6 characters.")
                else:
                    result = sign_up_user(signup_username, signup_password)
                    if result == "Success":
                        st.success("Account created! You can now log in.")
                    else:
                        st.error(result)

# --- ADMIN FEATURES (CRUD & Performance) ---

@st.cache_data(show_spinner="Loading products...")
def admin_get_products(product_version):
    """Fetches product templates and inventory summary."""
    conn = get_db_connection()
    query = """
    SELECT 
        P.id, P.name, P.category, P.description, P.base_image_b64,
        COUNT(I.id) AS unique_sizes,
        IFNULL(SUM(I.quantity_in_stock), 0) AS total_stock,
        MIN(I.selling_price) AS min_price,
        MAX(I.selling_price) AS max_price
    FROM PRODUCTS AS P
    LEFT JOIN INVENTORY AS I ON P.id = I.product_id
    GROUP BY P.id
    ORDER BY P.id DESC
    """
    df = pd.read_sql_query(query, conn)
    return df

@st.cache_data(show_spinner="Loading inventory details...")
def admin_get_inventory_details(product_id, inventory_version):
    """Fetches detailed inventory for a single product template."""
    conn = get_db_connection()
    query = """
    SELECT id, size, quantity_in_stock, manufacturing_cost, selling_price
    FROM INVENTORY
    WHERE product_id = ?
    ORDER BY size
    """
    df = pd.read_sql_query(query, conn, params=(product_id,))
    return df

def admin_add_product_template():
    """Form to add a new top-level product template (name, description, image)."""
    st.markdown("### 👕 1. Add New Product Template (Name, Description, Image)")
    with st.form("add_product_template_form", clear_on_submit=True):
        name = st.text_input("Product Name", key="new_product_name")
        category = st.selectbox("Category", ["T-Shirt", "Shirt", "Hoodie", "Accessory", "Other"], key="new_product_category")
        description = st.text_area("Description", key="new_product_description")
        
        # FEATURE 1: Image Upload
        uploaded_file = st.file_uploader("Upload Product Image (PNG/JPG)", type=["png", "jpg", "jpeg"], key="new_product_image_uploader")
        
        if st.form_submit_button("Create Product Template", type="primary", use_container_width=True):
            if not name or not category or not description:
                st.error("Please fill in the Name, Category, and Description.")
            else:
                b64_image = image_to_base64(uploaded_file)
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO PRODUCTS (name, category, description, base_image_b64) VALUES (?, ?, ?, ?)", 
                                 (name, category, description, b64_image))
                    conn.commit()
                    st.session_state.product_version += 1
                    st.success(f"Product Template '{name}' created successfully! Now add inventory for sizes/costs.")
                    st.rerun() # Rerun to refresh the product list immediately
                except sqlite3.IntegrityError:
                    st.error(f"Product name '{name}' already exists.")
                except Exception as e: 
                    st.error(f"Error adding product: {e}")

def admin_add_inventory_item(product_id):
    """Form to add or update stock for a specific size/cost/price for a product template."""
    conn = get_db_connection()
    product_row = conn.execute("SELECT name FROM PRODUCTS WHERE id = ?", (product_id,)).fetchone()
    if not product_row: return
    product_name = product_row['name']
    
    st.markdown(f"### 📦 2. Manage Inventory for: {product_name}")
    
    current_inventory_df = admin_get_inventory_details(product_id, st.session_state.inventory_version)
    
    st.markdown("#### Existing Stock & Pricing")
    if current_inventory_df.empty:
        st.info("No sizes/stock added yet for this product.")
    else:
        # FEATURE 4: Displaying Inventory Details (including cost/price)
        st.dataframe(
            current_inventory_df, 
            column_config={
                "quantity_in_stock": "Stock",
                "manufacturing_cost": st.column_config.NumberColumn("Man. Cost (₹)", format="₹%.2f"),
                "selling_price": st.column_config.NumberColumn("Sell Price (₹)", format="₹%.2f"),
                "id": None,
            },
            hide_index=True,
            use_container_width=True
        )

    st.markdown("---")
    st.markdown("#### Add/Update Size Stock and Pricing")
    with st.form(f"add_inventory_form_{product_id}", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: 
            size = st.selectbox("Size", ["XS", "S", "M", "L", "XL", "XXL"], key=f"inv_size_{product_id}")
            # FEATURE 7: Manufacturing Cost
            cost = st.number_input("Manufacturing Cost (₹)", min_value=0.01, format="%.2f", key=f"inv_cost_{product_id}", value=150.00)
        
        with col2:
            # FEATURE 2: Bulk Quantity in Stock
            quantity = st.number_input("Bulk Quantity to Add/Set", min_value=1, value=10, step=1, key=f"inv_qty_{product_id}")
            # FEATURE 7: Selling Price (Customer Price)
            price = st.number_input("Selling Price (₹)", min_value=0.01, format="%.2f", key=f"inv_price_{product_id}", value=399.00)
        
        action = st.radio("Action for existing size", ["Set Stock to Quantity", "Add to Current Stock"], horizontal=True, index=0)

        if st.form_submit_button("Save Inventory Item", type="primary", use_container_width=True):
            if price <= cost:
                st.error("Selling Price must be higher than Manufacturing Cost to ensure profit margin.")
            else:
                try:
                    # Check if inventory item for this size already exists
                    existing_item = conn.execute("SELECT id, quantity_in_stock FROM INVENTORY WHERE product_id = ? AND size = ?", 
                                                (product_id, size)).fetchone()
                    
                    if existing_item:
                        inventory_id, current_stock = existing_item['id'], existing_item['quantity_in_stock']
                        
                        if action == "Add to Current Stock":
                            new_stock = current_stock + quantity
                        else: # "Set Stock to Quantity"
                            new_stock = quantity
                            
                        # Update existing item
                        conn.execute("UPDATE INVENTORY SET quantity_in_stock = ?, manufacturing_cost = ?, selling_price = ? WHERE id = ?",
                                    (new_stock, cost, price, inventory_id))
                        st.success(f"Updated {size} stock to {new_stock}. Price: ₹{price:.2f}, Cost: ₹{cost:.2f}")
                    else:
                        # Insert new item
                        conn.execute("INSERT INTO INVENTORY VALUES (NULL, ?, ?, ?, ?, ?)", 
                                    (product_id, size, quantity, cost, price))
                        st.success(f"Added new size {size} with {quantity} in stock. Price: ₹{price:.2f}, Cost: ₹{cost:.2f}")
                    
                    conn.commit()
                    st.session_state.inventory_version += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"Error managing inventory: {e}")

@st.cache_data(show_spinner="Loading performance data...")
def admin_get_performance_data(order_version):
    """Fetches all order and item data for performance calculations."""
    conn = get_db_connection()
    query = """
    SELECT 
        O.order_date,
        OI.quantity,
        OI.unit_selling_price,
        OI.unit_manufacturing_cost
    FROM ORDERS AS O
    JOIN ORDER_ITEMS AS OI ON O.order_id = OI.order_id
    """
    df = pd.read_sql_query(query, conn)
    return df

def admin_performance_tracking():
    """FEATURE 5 & 7: Displays sales, revenue, cost, and profit/loss over time."""
    st.title("📈 Performance Tracking Dashboard (Admin Only)")
    
    df = admin_get_performance_data(st.session_state.order_version)
    
    if df.empty:
        st.info("No sales data available yet to track performance.")
        return

    # --- Calculations ---
    df['date'] = pd.to_datetime(df['order_date']).dt.date
    df['Revenue'] = df['quantity'] * df['unit_selling_price']
    df['Cost'] = df['quantity'] * df['unit_manufacturing_cost']
    df['Profit'] = df['Revenue'] - df['Cost']

    total_revenue = df['Revenue'].sum()
    total_cost = df['Cost'].sum()
    total_profit = df['Profit'].sum()
    margin_pct = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

    st.subheader("Key Financial Metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Revenue", f"₹{total_revenue:,.2f}")
    col2.metric("Total Cost", f"₹{total_cost:,.2f}")
    col3.metric("Total Profit", f"₹{total_profit:,.2f}", delta=f"{margin_pct:.2f}% Margin")
    col4.metric("Total Items Sold", f"{df['quantity'].sum():,}")

    # --- Sales Over Time Graph (FEATURE 5) ---
    st.subheader("Sales and Profit Trend (by Date)")
    
    # Aggregate data by date
    sales_trend = df.groupby('date').agg(
        Total_Revenue=('Revenue', 'sum'),
        Total_Profit=('Profit', 'sum'),
    ).reset_index()

    sales_chart_data = sales_trend.set_index('date')[['Total_Revenue', 'Total_Profit']]
    st.line_chart(sales_chart_data)

# --- CUSTOMER FEATURES ---

@st.cache_data(show_spinner="Loading products...")
def get_customer_catalog(product_version):
    """Fetches combined product and inventory data for the customer catalog."""
    conn = get_db_connection()
    query = """
    SELECT 
        P.id AS product_id, P.name, P.category, P.description, P.base_image_b64,
        I.id AS inventory_id, I.size, I.quantity_in_stock, I.selling_price
    FROM PRODUCTS AS P
    JOIN INVENTORY AS I ON P.id = I.product_id
    WHERE I.quantity_in_stock > 0
    ORDER BY P.id DESC, I.selling_price ASC
    """
    df = pd.read_sql_query(query, conn)
    return df

@st.cache_data(show_spinner="Loading cart...")
def get_user_cart(user_id, cart_version):
    """Retrieves the user's current cart items."""
    conn = get_db_connection()
    query = """
    SELECT 
        C.id AS cart_item_id, C.quantity AS cart_quantity,
        I.id AS inventory_id, I.size, I.selling_price, 
        P.name, P.base_image_b64
    FROM CART AS C 
    JOIN INVENTORY AS I ON C.inventory_id = I.id
    JOIN PRODUCTS AS P ON I.product_id = P.id
    WHERE C.user_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    return df

def add_to_cart(inventory_id, quantity):
    """Adds or updates a product size/inventory item in the user's cart."""
    user_id = st.session_state.username
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if stock is sufficient
    stock_check = c.execute("SELECT quantity_in_stock FROM INVENTORY WHERE id = ?", (inventory_id,)).fetchone()
    if not stock_check:
        st.error("Invalid product selection.")
        return
        
    available_stock = stock_check['quantity_in_stock']

    try:
        c.execute("SELECT quantity FROM CART WHERE user_id = ? AND inventory_id = ?", (user_id, inventory_id))
        cart_item = c.fetchone()

        if cart_item:
            current_cart_qty = cart_item['quantity']
            new_quantity = current_cart_qty + quantity
            
            if new_quantity > available_stock:
                st.error(f"Cannot add {quantity} more items. Only {available_stock - current_cart_qty} available in stock.")
                return
                
            c.execute("UPDATE CART SET quantity = ? WHERE user_id = ? AND inventory_id = ?", (new_quantity, user_id, inventory_id))
            st.toast(f"Updated quantity to {new_quantity}!", icon="🛒")
        else:
            if quantity > available_stock:
                st.error(f"Cannot add {quantity}. Only {available_stock} available in stock.")
                return
                
            c.execute("INSERT INTO CART VALUES (NULL, ?, ?, ?)", (user_id, inventory_id, quantity))
            st.toast("Product added to cart!", icon="🛒")
            
        conn.commit()
        st.session_state.cart_version += 1
        
    except Exception as e:
        st.error(f"Could not add item: {e}")
    st.rerun() 

def remove_from_cart(cart_item_id):
    """Removes an item from the cart."""
    conn = get_db_connection()
    conn.execute("DELETE FROM CART WHERE id = ?", (cart_item_id,))
    conn.commit()
    st.session_state.cart_version += 1
    st.toast("Item removed from cart.", icon="🗑️")
    st.rerun()

def clear_user_cart(user_id):
    """Deletes all items from a user's cart."""
    conn = get_db_connection()
    conn.execute("DELETE FROM CART WHERE user_id = ?", (user_id,))
    conn.commit()
    st.session_state.cart_version += 1

def spin_the_wheel_logic():
    """FEATURE 13: Simulates a 'Spin the Wheel' discount."""
    options = [
        (0.0, "Better luck next time! You won 0% discount."),
        (0.0, "Better luck next time! You won 0% discount."),
        (0.05, "🎉 5% off!"),
        (0.10, "🎊 10% discount!"),
        (0.15, "✨ 15% discount!"),
        (0.20, "🥳 20% discount!")
    ]
    
    chosen_discount, message = random.choice(options)
    
    if chosen_discount > 0:
        coupon_code = f"SPIN{int(chosen_discount*100)}{random.randint(100, 999)}"
        st.session_state.coupon_code = coupon_code
        st.session_state.discount_rate = chosen_discount
        st.balloons()
        st.success(f"{message} Coupon: `{coupon_code}`")
    else:
        st.session_state.coupon_code = "NONE"
        st.session_state.discount_rate = 0.0
        st.warning(message)
    
    st.rerun()

def customer_checkout(cart_df):
    """Handles checkout, now deducting stock and saving detailed costs."""
    user_id = st.session_state.username
    if cart_df.empty:
        st.warning("Your cart is empty. Please add items to buy.")
        if st.button("Go to Catalog", type="secondary"):
            st.session_state.checkout_stage = 'catalog'
            st.session_state.current_view = 'catalog'
            st.rerun()
        return

    # --- STAGE 1: PAYMENT FORM ---
    if st.session_state.get('checkout_substage') != 'delivered':
        # Rename 'cart_quantity' to 'Quantity' for display
        cart_df['Quantity'] = cart_df['cart_quantity'] 
        cart_df['Subtotal'] = cart_df['selling_price'] * cart_df['Quantity']
        
        total_pre_discount = cart_df['Subtotal'].sum()
        
        st.subheader("1. Order Summary")
        
        # Display cart with a dedicated button handler for removing items
        st.dataframe(
            cart_df[['name', 'size', 'Quantity', 'selling_price', 'Subtotal', 'cart_item_id']],
            column_config={
                "selling_price": st.column_config.NumberColumn("Unit Price (₹)", format="₹%.2f"),
                "Subtotal": st.column_config.NumberColumn("Item Total (₹)", format="₹%.2f"),
                "cart_item_id": None, # Hide ID
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Manually create remove buttons outside the dataframe
        st.markdown("#### Manage Cart Items")
        for index, row in cart_df.iterrows():
            col_name, col_btn = st.columns([4, 1])
            with col_name:
                st.markdown(f"**{row['name']}** ({row['size']}) - Qty: {row['Quantity']}")
            with col_btn:
                # Use a specific key for each item's remove button
                if st.button("Remove", key=f"remove_item_{row['cart_item_id']}", use_container_width=True):
                    remove_from_cart(row['cart_item_id']) # Calls st.rerun() inside

        st.markdown("---")
        
        # --- Discount/Coupon Wheel (FEATURE 13) ---
        st.subheader("🎁 Spin to Win a Discount!")
        
        if st.session_state.coupon_code is None or st.session_state.coupon_code == "NONE":
            st.button("Spin the Discount Wheel", key="spin_wheel", type="secondary", 
                      on_click=spin_the_wheel_logic, help="Get a chance to win a discount on your order.")
        
        total = total_pre_discount
        if st.session_state.discount_rate > 0.0:
            discount_amount = total_pre_discount * st.session_state.discount_rate
            total_post_discount = total_pre_discount - discount_amount
            total = total_post_discount 
            
            st.markdown(f"**Coupon Applied:** `{st.session_state.coupon_code}` ({int(st.session_state.discount_rate * 100)}% off)")
            st.metric("Subtotal", f"₹{total_pre_discount:.2f}")
            st.metric("Discount Applied", f"- ₹{discount_amount:.2f}")
            st.metric("Final Payable", f"₹{total_post_discount:.2f}", delta=f"-{int(st.session_state.discount_rate * 100)}% Saving")
        else:
             st.metric("Total Payable", f"₹{total_pre_discount:.2f}")

        st.markdown("---")

        st.subheader("2. 💳 Fake Payment Gateway")
        with st.form("payment_form", clear_on_submit=False):
            st.warning("⚠️ This is a simulated payment gateway. Your data is not transmitted.")
            card_number = st.text_input("Card Number", value="4111 1111 1111 1111")
            address = st.text_area("Shipping Address", "123 Main St, Springfield, Anystate, 12345")
            
            if st.form_submit_button("Process Payment & Place Order", type="primary", use_container_width=True):
                # Simple validation
                if not address:
                    st.error("Please enter a shipping address.")
                else:
                    st.session_state.checkout_substage = 'delivered'
                    st.session_state.order_total = total # Store the final discounted total
                    st.session_state.shipping_address = address
                    st.rerun()

    # --- STAGE 2: DELIVERY SIMULATION & CONFIRMATION ---
    if st.session_state.get('checkout_substage') == 'delivered':
        
        tracking_id = f"DEL-{hashlib.sha256(user_id.encode()).hexdigest()[:6].upper()}-{pd.Timestamp.now().strftime('%d%H%M')}"
        conn = get_db_connection()
        c = conn.cursor()
        
        # Need to re-fetch the cart one last time just before transaction for guaranteed data integrity
        cart_df_for_order = get_user_cart(st.session_state.username, st.session_state.cart_version) 

        try:
            # 1. Create the Order
            # Use stored order_total and discount_rate from session state
            c.execute("INSERT INTO ORDERS VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                      (user_id, st.session_state.order_total, tracking_id, str(pd.Timestamp.now()), 
                       st.session_state.shipping_address, st.session_state.discount_rate))
            order_id = c.lastrowid
            
            # 2. Add Order Items, Update Stock, and Capture Costs
            for index, row in cart_df_for_order.iterrows():
                inventory_id = row['inventory_id']
                quantity = row['cart_quantity'] # Use cart_quantity
                
                # Fetch detailed cost info and current stock from inventory
                item_info = c.execute("SELECT manufacturing_cost, selling_price, quantity_in_stock FROM INVENTORY WHERE id = ?", (inventory_id,)).fetchone()
                
                if item_info and item_info['quantity_in_stock'] >= quantity:
                    man_cost, sell_price, current_stock = item_info['manufacturing_cost'], item_info['selling_price'], item_info['quantity_in_stock']
                    
                    # Insert into ORDER_ITEMS (Captures cost at time of sale for performance tracking)
                    c.execute("INSERT INTO ORDER_ITEMS VALUES (NULL, ?, ?, ?, ?, ?)", 
                              (order_id, inventory_id, quantity, sell_price, man_cost))
                    
                    # Update INVENTORY stock (Deduct quantity)
                    new_stock = current_stock - quantity
                    c.execute("UPDATE INVENTORY SET quantity_in_stock = ? WHERE id = ?", (new_stock, inventory_id))
                else:
                    # Transaction failed due to lack of stock
                    raise Exception(f"Stock check failed during final transaction for inventory item {inventory_id}. Transaction rolled back.")
                    
            clear_user_cart(user_id) # Clears cart
            conn.commit()
            
            # Reset states and increment version counters
            st.session_state.coupon_code = None
            st.session_state.discount_rate = 0.0
            st.session_state.order_version += 1 # Trigger performance cache refresh
            st.session_state.inventory_version += 1 # Trigger inventory views refresh

            st.balloons()
            st.success("🎉 Purchase Successful! Your order is placed.")
            st.markdown(f"**Order Total:** ₹{st.session_state.order_total:.2f}")
            st.markdown(f"**Tracking ID:** `{tracking_id}`")
            st.markdown(f"**Shipping to:** {st.session_state.shipping_address}")

            if st.button("Continue Shopping", type="primary"):
                st.session_state.checkout_stage = 'catalog'
                st.session_state.current_view = 'catalog'
                st.session_state.checkout_substage = None
                st.rerun()
                
        except Exception as e:
            st.error(f"Error processing order. Please try again. Details: {e}")
            conn.rollback()


def customer_browse_products():
    """Displays all products, allows search, and filtering."""
    st.markdown("### 🛍️ Browse Our T-Shirts")
    
    # --- Filter/Search Controls (FEATURE 6 & 14) ---
    col_s, col_c, col_sz = st.columns([3, 1, 1])
    
    with col_s: search_query = st.text_input("🔍 Search Products", placeholder="Search by name, description, or category...", key="product_search")
    
    products_df_all = get_customer_catalog(st.session_state.product_version)
    
    unique_categories = ["All Products"] + sorted(products_df_all['category'].unique().tolist())
    unique_sizes = ["All Sizes"] + sorted(products_df_all['size'].unique().tolist())
    
    with col_c: selected_category = st.selectbox("Filter by Type", unique_categories, key="filter_category")
    with col_sz: selected_size = st.selectbox("Filter by Size", unique_sizes, key="filter_size")

    # Apply filters
    filtered_df = products_df_all.copy()
    if selected_category != "All Products":
        filtered_df = filtered_df[filtered_df['category'] == selected_category]
    if selected_size != "All Sizes":
        filtered_df = filtered_df[filtered_df['size'] == selected_size]
    
    # Apply text search
    if search_query:
        query_lower = search_query.lower()
        filtered_df = filtered_df[filtered_df.apply(
            lambda row: query_lower in row['name'].lower() or 
                        query_lower in str(row['description']).lower() or
                        query_lower in row['category'].lower(), axis=1
        )]
    
    if filtered_df.empty: 
        st.warning(f"No products found matching your criteria.")
        return
        
    # Group by Product ID to display unique items
    product_groups = filtered_df.groupby('product_id').agg(
        name=('name', 'first'),
        category=('category', 'first'),
        description=('description', 'first'),
        base_image_b64=('base_image_b64', 'first'),
        min_price=('selling_price', 'min'),
    ).reset_index().sort_values(by='product_id', ascending=False)
        
    # Display Products
    num_products = len(product_groups)
    cols = st.columns(min(4, num_products) or 1) # Ensure at least 1 column for display

    for index, row in product_groups.iterrows():
        col_index = index % min(4, len(cols))
        col = cols[col_index]
        
        with col.container(border=True):
            # FEATURE 4: Display uploaded image
            col.markdown(b64_to_image_html(row['base_image_b64'], width=200), unsafe_allow_html=True)
            st.markdown(f"**{row['name']}**")
            st.markdown(f"*{row['category']}*")
            st.markdown(f"**Price from:** ₹{row['min_price']:.2f}")
            
            if col.button("View Details", key=f"view_detail_{row['product_id']}", use_container_width=True):
                st.session_state.selected_product_id = row['product_id']
                st.session_state.current_view = 'detail'
                st.rerun()

def product_detail_view():
    """Displays single product details, description, size chart, and allows size selection (FEATURE 8, 9, 10, 11)."""
    product_id = st.session_state.selected_product_id
    if not product_id:
        st.session_state.current_view = 'catalog'
        return

    conn = get_db_connection()
    c = conn.cursor()
    product_row = c.execute("SELECT * FROM PRODUCTS WHERE id = ?", (product_id,)).fetchone()
    
    if not product_row:
        st.error("Product not found.")
        st.session_state.current_view = 'catalog'
        return
        
    product = dict(product_row)
    
    # FEATURE 11: Back to catalog button on top left
    if st.button("⬅️ Back to Catalog", key="back_from_detail_top"):
        st.session_state.selected_product_id = None
        st.session_state.current_view = 'catalog'
        st.rerun()

    st.title(f"✨ {product['name']}")
    st.markdown(f"**Category:** *{product['category']}*")

    col_img, col_info = st.columns([1, 2])
    
    with col_img:
        # FEATURE 4: Display uploaded image
        st.markdown(b64_to_image_html(product['base_image_b64'], width=350), unsafe_allow_html=True)

    with col_info:
        # FEATURE 9: Seeing a description below
        st.subheader("Product Description")
        st.info(product['description'])

        # --- Size Selection and Add to Cart (FEATURE 8) ---
        st.subheader("Select Size & Quantity")
        
        inventory_df = admin_get_inventory_details(product_id, st.session_state.inventory_version)
        available_stock = inventory_df[inventory_df['quantity_in_stock'] > 0]
        
        if available_stock.empty:
            st.error("This product is currently out of stock.")
            return

        # Map inventory ID to a display string
        inventory_map = {}
        for _, row in available_stock.iterrows():
             # Only show price and stock for items that have stock
            if row['quantity_in_stock'] > 0:
                key = f"{row['size']} (₹{row['selling_price']:.2f}) - Stock: {row['quantity_in_stock']}"
                inventory_map[key] = row['id']
                
        size_options = list(inventory_map.keys())
        
        selected_option = st.selectbox("Select Size & Price", size_options, key="size_select")
        selected_inventory_id = inventory_map[selected_option]

        # Get max quantity for selected item
        selected_inventory_row = available_stock[available_stock['id'] == selected_inventory_id].iloc[0]
        max_qty = selected_inventory_row['quantity_in_stock']
        
        st.metric("Current Price", f"₹{selected_inventory_row['selling_price']:.2f}")

        quantity = st.number_input(f"Quantity (Max {max_qty})", min_value=1, max_value=max_qty, value=1, step=1, key="detail_qty")
        
        st.markdown("---")
        
        if st.button("Add to Cart", type="primary", key="add_to_cart_detail", use_container_width=True):
            add_to_cart(selected_inventory_id, quantity)
            # Rerun happens inside add_to_cart

    # FEATURE 10: Size Chart
    st.markdown("---")
    st.subheader("📏 Size Chart")
    size_chart_data = {
        'Size': ['XS', 'S', 'M', 'L', 'XL', 'XXL'],
        'Chest (in)': ['32-34', '36-38', '40-42', '44-46', '48-50', '52-54'],
        'Length (in)': ['24', '26', '28', '30', '32', '34']
    }
    st.dataframe(pd.DataFrame(size_chart_data), hide_index=True, use_container_width=True)


@st.cache_data(show_spinner="Loading user data...")
def get_user_data(user_id):
    """Fetches user profile data."""
    conn = get_db_connection()
    user_data = conn.execute("SELECT profile_picture_b64, birthday FROM USERS WHERE username = ?", (user_id,)).fetchone()
    return dict(user_data) if user_data else {}

def user_profile_view():
    """Displays user information, allows editing profile picture and birthday (FEATURE 12)."""
    user_id = st.session_state.username
    st.title(f"👤 User Profile: {user_id}")
    
    current_data = get_user_data(user_id)
    
    col_pic, col_info = st.columns([1, 2])
    
    with col_pic:
        st.subheader("Profile Picture")
        # Display current picture
        st.markdown(b64_to_image_html(current_data.get('profile_picture_b64'), width=180), unsafe_allow_html=True)
        
        # Upload new picture
        uploaded_file = st.file_uploader("Change Profile Image", type=["png", "jpg", "jpeg"], key="profile_image_uploader")

    with col_info:
        st.subheader("Account Details")
        st.markdown(f"**Username:** `{user_id}`")
        st.markdown(f"**Role:** `{st.session_state.role.capitalize()}`")
        
        # Birthday input
        st.markdown("---")
        st.subheader("Personal Information")
        
        # Handle date conversion for date_input default value
        default_bday = None
        if current_data.get('birthday'):
            try:
                # Convert SQL date string to Python date object
                default_bday = date.fromisoformat(current_data['birthday'])
            except (ValueError, TypeError):
                pass 
        
        new_birthday = st.date_input("Birthday", value=default_bday, key="profile_birthday", max_value=date.today())
        
        if st.button("Save Profile Updates", type="primary", use_container_width=True):
            conn = get_db_connection()
            
            # If a new file was uploaded, use its Base64. Otherwise, use the existing one.
            b64_image = image_to_base64(uploaded_file) if uploaded_file else current_data.get('profile_picture_b64')
            
            # Update user data (Birthday is stored as ISO format string)
            conn.execute("UPDATE USERS SET profile_picture_b64 = ?, birthday = ? WHERE username = ?",
                         (b64_image, str(new_birthday), user_id))
            conn.commit()
            st.success("Profile updated successfully!")
            st.cache_data.clear() # Clear user data cache to refresh view
            st.rerun()

    st.markdown("---")
    st.subheader("Your Order History")
    # Fetch and display order history
    orders_query = """
    SELECT 
        O.order_id, O.total_amount, O.order_date, O.tracking_id, O.discount_rate
    FROM ORDERS AS O
    WHERE O.user_id = ?
    ORDER BY O.order_date DESC
    """
    orders_df = pd.read_sql_query(orders_query, conn, params=(user_id,))
    
    if orders_df.empty:
        st.info("You have not placed any orders yet.")
    else:
        # Convert discount rate to percentage for display
        orders_df['discount_rate_pct'] = (orders_df['discount_rate'] * 100).astype(int)
        
        st.dataframe(
            orders_df.drop(columns=['discount_rate']),
            column_config={
                "order_id": "Order #",
                "total_amount": st.column_config.NumberColumn("Total Paid (₹)", format="₹%.2f"),
                "order_date": "Date",
                "tracking_id": "Tracking ID",
                "discount_rate_pct": st.column_config.NumberColumn("Discount", format="%d%%", help="Discount Applied"),
            },
            hide_index=True,
            use_container_width=True
        )

def customer_faq_enquiries():
    """Simple FAQ and simulated contact form (FEATURE 15)."""
    st.title("FAQ & Customer Service")
    st.markdown("""
        ### Frequently Asked Questions
        
        **Q: How long does shipping take?**
        A: Standard shipping takes 5-7 business days. You can track your order using the Tracking ID in your Order History under the User Profile.
        
        **Q: Can I return an item?**
        A: Yes, returns are accepted within 30 days of delivery. Please contact customer service below for a return authorization.
        
        **Q: How does the Spin the Wheel discount work?**
        A: The Spin the Wheel is a fun way to win an extra discount on your current checkout. You can spin once per order!
    """)
    st.markdown("---")
    st.subheader("Contact Us")
    with st.form("contact_form"):
        name = st.text_input("Your Name")
        email = st.text_input("Your Email")
        enquiry = st.text_area("Your Enquiry")
        if st.form_submit_button("Submit Enquiry", type="primary", use_container_width=True):
            if name and email and enquiry:
                # Placeholder for submission logic
                st.success(f"Thank you, {name}. Your enquiry has been submitted and we will respond to {email} shortly.")
            else:
                st.error("Please fill out all fields.")


# --- MAIN APP LAYOUT & NAVIGATION ---

def main_app():
    """The main entry point for the Streamlit application."""
    
    # Check for DB connection immediately, it handles initialization via cache
    db = get_db_connection()
    if db is None:
        # get_db_connection handles the error display, we just stop the script.
        return

    with st.sidebar:
        # Display T-Shirt icon prominently
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/T-shirt_blue_outline.svg/100px-T-shirt_blue_outline.svg.png")
        st.title("T-Shirt Shop")

        if st.session_state.logged_in:
            st.success(f"User: {st.session_state.username} ({st.session_state.role.capitalize()})")
            if st.button("Logout", key="logout_btn", use_container_width=True): logout()

            st.divider()

            if st.session_state.role == 'admin':
                st.subheader("Admin Menu")
                # Navigation for admin views
                if st.button("📦 Manage Products/Inventory", key="admin_products", use_container_width=True): st.session_state.current_view = 'admin_products'
                if st.button("📈 Performance Tracking", key="admin_performance", use_container_width=True): st.session_state.current_view = 'admin_performance'
            
            elif st.session_state.role == 'customer':
                st.subheader("Customer Menu")
                # Navigation for customer views
                if st.button("🏠 Catalog", key="catalog_link", use_container_width=True): 
                    st.session_state.current_view = 'catalog'
                    st.session_state.checkout_stage = 'catalog' # Reset checkout state
                if st.button("👤 User Profile / History", key="profile_btn", use_container_width=True): 
                    st.session_state.current_view = 'profile'
                    st.session_state.checkout_stage = 'catalog' # Reset checkout state

                st.divider()
                st.subheader("🛒 Your Cart")
                # Fetch cart and display summary
                cart_df = get_user_cart(st.session_state.username, st.session_state.cart_version)
                
                if cart_df.empty:
                    st.markdown("Your cart is empty.")
                else:
                    total = (cart_df['selling_price'] * cart_df['cart_quantity']).sum()
                    st.metric("Total Cart Value", f"₹{total:.2f}")

                    if st.button("Proceed to Checkout", key="buy_btn", type="primary", use_container_width=True):
                        st.session_state.checkout_stage = 'payment'
                        st.session_state.current_view = 'catalog' # Stay on catalog view but trigger checkout logic
                        st.session_state.checkout_substage = 'payment_form'
                        st.session_state.coupon_code = None
                        st.session_state.discount_rate = 0.0
                        st.rerun()
        else:
            auth_forms()

    # Main Content Area Routing
    if not st.session_state.logged_in:
        st.title("T-Shirt Inventory Portal")
        st.info("Please log in to proceed. Default users: `admin`/`adminpass`, `customer1`/`custpass`")

    elif st.session_state.role == 'admin':
        if st.session_state.current_view == 'admin_performance':
            admin_performance_tracking()
        else: # Default or 'admin_products'
            st.title("👨‍💻 Admin Dashboard")
            tab1, tab2 = st.tabs(["Add Product Template", "Manage Inventory/View Products"])
            with tab1: admin_add_product_template()
            with tab2: 
                products_df = admin_get_products(st.session_state.product_version)
                st.markdown("### Product Templates Overview")
                
                if products_df.empty:
                    st.info("No product templates exist. Use the 'Add Product Template' tab.")
                else:
                    # FEATURE 4: Display image in admin view
                    products_df['Image'] = products_df['base_image_b64'].apply(lambda x: b64_to_image_html(x, width=50))
                    
                    st.dataframe(
                        products_df[['Image', 'name', 'category', 'total_stock', 'min_price', 'max_price', 'id']],
                        column_config={
                            "Image": st.column_config.Column("Image", width="small", help="Product Image"),
                            "total_stock": "Total Stock",
                            "min_price": st.column_config.NumberColumn("Min Price (₹)", format="₹%.2f"),
                            "max_price": st.column_config.NumberColumn("Max Price (₹)", format="₹%.2f"),
                            "name": "Product Name",
                            "category": "Category",
                            "id": None, 
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # Selection for inventory management
                    if not products_df.empty:
                        product_selection_id = st.selectbox(
                            "Select Product Template to Manage Inventory (Sizes/Costs/Prices)", 
                            options=products_df['id'].tolist(),
                            format_func=lambda x: products_df[products_df['id'] == x]['name'].iloc[0]
                        )
                        admin_add_inventory_item(product_selection_id)
                    

    elif st.session_state.role == 'customer':
        view = st.session_state.get('current_view', 'catalog')
        checkout_stage = st.session_state.get('checkout_stage', 'catalog')

        # Checkout overrides all other views when triggered
        if checkout_stage == 'payment':
            st.title("Secure Checkout")
            # Must pass the current cart data
            cart_df_for_checkout = get_user_cart(st.session_state.username, st.session_state.cart_version)
            customer_checkout(cart_df_for_checkout)
        
        elif view == 'profile':
            user_profile_view()
            
        elif view == 'detail':
            product_detail_view()

        else: # Default: 'catalog' view
            tab1, tab2 = st.tabs(["T-Shirt Catalog", "FAQ / Enquiries"])
            with tab1: customer_browse_products()
            with tab2: customer_faq_enquiries()

if __name__ == '__main__':
    main_app()
