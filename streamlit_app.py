import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import random

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

# States for complex navigation and features
st.session_state.setdefault('current_view', 'catalog') # 'catalog', 'detail', 'profile'
st.session_state.setdefault('selected_product_id', None)
st.session_state.setdefault('checkout_stage', 'catalog') # 'catalog' or 'payment'
st.session_state.setdefault('checkout_substage', None) # 'payment_form' or 'delivered'
st.session_state.setdefault('coupon_code', None)
st.session_state.setdefault('discount_rate', 0.0) # 0.0 to 1.0

# Optimization Counters for Cache Invalidation
st.session_state.setdefault('product_version', 0)
st.session_state.setdefault('cart_version', 0)

@st.cache_resource
def get_db_connection():
    """
    Establishes and returns a single, cached connection to the SQLite database.
    
    CRITICAL FIX: check_same_thread=False prevents Streamlit's threading from 
    causing SQLite ProgrammingErrors.
    """
    conn = sqlite3.connect('inventory.db', check_same_thread=False)
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
    except sqlite3.IntegrityError: pass

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
        except sqlite3.IntegrityError: pass

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
    """Logs out the user and resets all session states."""
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
    query = f"""
    SELECT T1.id AS cart_item_id, T2.id AS product_id, T2.name, T2.price, T1.quantity, T2.size, T2.image_url
    FROM CART AS T1 JOIN PRODUCTS AS T2 ON T1.product_id = T2.id
    WHERE T1.user_id = '{user_id}'
    """
    df = pd.read_sql_query(query, conn)
    return df

def add_to_cart(product_id, quantity):
    """Adds or updates a product in the user's cart."""
    user_id = st.session_state.username
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Check if the exact product ID is already in the cart
        c.execute("SELECT quantity FROM CART WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        cart_item = c.fetchone()

        if cart_item:
            new_quantity = cart_item[0] + quantity
            c.execute("UPDATE CART SET quantity = ? WHERE user_id = ? AND product_id = ?", (new_quantity, user_id, product_id))
            st.toast(f"Updated quantity to {new_quantity}!", icon="🛒")
        else:
            c.execute("INSERT INTO CART VALUES (NULL, ?, ?, ?)", (user_id, product_id, quantity))
            st.toast("Product added to cart!", icon="🛒")
        conn.commit()
        
        # CRITICAL: Increment cart_version to bust the cart cache
        st.session_state.cart_version += 1
        
    except Exception as e:
        st.error(f"Could not add item: {e}")
    st.rerun() # Rerunning is necessary for instant UI update

def remove_from_cart(cart_item_id):
    """Removes a single item entry from the cart based on its ID."""
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM CART WHERE id = ?", (cart_item_id,))
        conn.commit()
        # CRITICAL: Increment cart_version to bust the cart cache
        st.session_state.cart_version += 1
        st.toast("Item removed from cart!", icon="❌")
    except Exception as e:
        st.error(f"Error removing item: {e}")
    st.rerun()

def clear_user_cart(user_id):
    """Removes all items from the user's cart."""
    conn = get_db_connection()
    conn.execute("DELETE FROM CART WHERE user_id = ?", (user_id,))
    conn.commit()
    # CRITICAL: Increment cart_version to bust the cart cache
    st.session_state.cart_version += 1

def spin_the_wheel_logic():
    """Simulates a discount wheel spin and updates session state."""
    discounts = {
        "NO-LUCK": 0.0,
        "SAVE5": 0.05,
        "SAVE10": 0.10,
        "SAVE20": 0.20,
    }
    
    # Define weight distribution for outcomes (e.g., 50% for 0%)
    outcomes = random.choices(
        list(discounts.keys()), 
        weights=[50, 30, 15, 5], 
        k=1
    )[0]
    
    st.session_state.coupon_code = outcomes
    st.session_state.discount_rate = discounts[outcomes]
    
    if st.session_state.discount_rate > 0:
        st.success(f"🎉 Winner! You won a {int(st.session_state.discount_rate * 100)}% discount with code **{outcomes}**!")
    else:
        st.info("Spin again next time! No extra discount this round.")
    
    # Rerun to refresh the checkout summary with the new discount
    st.session_state.checkout_substage = 'payment_form'
    st.rerun()

def customer_checkout(cart_df):
    """Handles the multi-stage fake payment and delivery process with discount logic."""
    user_id = st.session_state.username
    if cart_df.empty:
        st.error("Your cart is empty. Please add items to buy.")
        st.session_state.checkout_stage = 'catalog'
        st.session_state.current_view = 'catalog'
        return

    # --- STAGE 1: PAYMENT FORM ---
    if st.session_state.get('checkout_substage') != 'delivered':
        total_pre_discount = (cart_df['price'] * cart_df['quantity']).sum()
        total = total_pre_discount # Default total

        st.subheader("1. Order Summary")
        
        # Display cart with remove buttons
        st.dataframe(
            cart_df[['name', 'size', 'quantity', 'price']],
            column_config={"price": st.column_config.NumberColumn("Price ($)", format="$%.2f")},
            hide_index=True
        )
        
        # Display individual remove buttons below the table
        cols_remove = st.columns(3)
        # Ensure we don't access columns beyond the index size
        num_items = len(cart_df)
        for index, row in cart_df.iterrows():
            col_index = index % 3
            if col_index < 3: # Safety check
                cols_remove[col_index].button(
                    f"Remove 1x {row['name']} ({row['size']})", 
                    key=f"remove_{row['cart_item_id']}", 
                    on_click=remove_from_cart, 
                    args=(row['cart_item_id'],)
                )

        st.markdown("---")
         # --- Discount/Coupon Wheel ---
        st.subheader("🎁 Spin to Win a Discount!")
        
        if st.session_state.coupon_code is None:
            st.button("Spin the Discount Wheel", key="spin_wheel", type="secondary", 
                      on_click=spin_the_wheel_logic, help="Get a chance to win a discount on your order.")
        
        # Apply Discount Logic
        if st.session_state.discount_rate > 0:
            discount_amount = total_pre_discount * st.session_state.discount_rate
            total_post_discount = total_pre_discount - discount_amount
            total = total_post_discount # Use the discounted total
            
            st.markdown(f"**Coupon Applied:** `{st.session_state.coupon_code}` ({int(st.session_state.discount_rate * 100)}% off)")
            st.metric("Discount Applied", f"- ${discount_amount:.2f}")
            st.metric("Final Payable", f"${total_post_discount:.2f}", delta=f"-{int(st.session_state.discount_rate * 100)}%")
        else:
             st.metric("Total Payable", f"${total_pre_discount:.2f}")

        st.markdown("---")

        st.subheader("2. 💳 Fake Payment Gateway")
        with st.form("payment_form", clear_on_submit=False):
            st.warning("⚠️ This is a simulated payment gateway.")
            card_number = st.text_input("Card Number", value="4111 1111 1111 1111")
            col1, col2 = st.columns(2)
            with col1: expiry = st.text_input("Expiry Date (MM/YY)", value="12/26")
            with col2: cvv = st.text_input("CVV", type="password", value="123")
            address = st.text_area("Shipping Address", "123 Main St, Springfield, Anystate, 12345")
            
            if st.form_submit_button("Process Payment & Place Order", type="primary"):
                # Simple validation
                if len(card_number.replace(' ', '')) != 16 or len(cvv) != 3 or not address or not expiry:
                    st.error("Please enter valid fake payment details.")
                else:
                    st.session_state.checkout_substage = 'delivered'
                    st.session_state.order_total = total # Save the final total
                    st.session_state.shipping_address = address
                    st.rerun()

    # --- STAGE 2: DELIVERY SIMULATION & CONFIRMATION ---
    if st.session_state.get('checkout_substage') == 'delivered':
        
        # Generate a unique tracking ID
        tracking_id = f"DEL-{hashlib.sha256(user_id.encode()).hexdigest()[:6].upper()}-{pd.Timestamp.now().strftime('%d%H%M')}"
        
        conn = get_db_connection()
        try:
            # Save the final order details
            conn.execute("INSERT INTO ORDERS VALUES (NULL, ?, ?, ?, ?, ?)",
                      (user_id, st.session_state.order_total, tracking_id, str(pd.Timestamp.now()), st.session_state.shipping_address))
            conn.commit()
            
            clear_user_cart(user_id) # Clears cart and increments cart_version
            
            # Reset discount states after successful order
            st.session_state.coupon_code = None
            st.session_state.discount_rate = 0.0

            st.balloons()
            st.success("🎉 Purchase Successful! Your order is placed.")

            st.markdown("---")
            st.subheader("3. 🚚 Fake Delivery Confirmation")
            st.info("Your order is now **Processing**.")
            
            st.markdown(f"**Tracking ID:** `{tracking_id}`")
            st.markdown(f"**Shipping Address:** {st.session_state.shipping_address}")
            estimated_delivery = pd.Timestamp.now() + pd.Timedelta(days=7)
            st.markdown(f"**Estimated Delivery:** **{estimated_delivery.strftime('%A, %B %d, %Y')}**")
            
            if st.button("Back to Shopping", type="secondary"):
                st.session_state.checkout_stage = 'catalog'
                st.session_state.current_view = 'catalog'
                st.session_state.checkout_substage = None
                st.rerun()
                
        except Exception as e:
            st.error(f"Error saving order: {e}")

@st.cache_data(show_spinner="Loading products...")
def get_all_products(product_version):
    """Fetches all product data from the database, cached."""
    conn = get_db_connection()
    products_df = pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)
    return products_df
    
def customer_browse_products():
    """Displays all products, allows search, and links to detail view."""
    st.markdown("### 🛍️ Browse Our T-Shirts")
    
    # --- Search Bar ---
    search_query = st.text_input("🔍 Search Products", placeholder="Search by name, size, or description...", key="product_search")

    # Use cached data
    products_df = get_all_products(st.session_state.product_version)

    if products_df.empty: 
        st.info("No products available.")
        return
        
    # Apply filter based on search query
    if search_query:
        query_lower = search_query.lower()
        products_df = products_df[products_df.apply(
            lambda row: query_lower in row['name'].lower() or 
                        query_lower in row['size'].lower(), axis=1
        )]
    
    if products_df.empty and search_query:
        st.warning(f"No products found matching '{search_query}'.")
        return
        
    # Display Products
    # Use max 3 columns, or fewer if there are fewer products
    num_products = len(products_df)
    cols = st.columns(min(3, num_products)) 

    if num_products == 0: return

    for index, row in products_df.iterrows():
        # Cycle through columns: 0, 1, 2, 0, 1, 2...
        col_index = index % min(3, len(cols))
        col = cols[col_index]
        
        with col.container(border=True):
            st.image(row['image_url'], caption=row['name'], width=150)
            st.markdown(f"**{row['name']}**")
            st.markdown(f"**Price:** \${row['price']:.2f} | **Size:** {row['size']}")
            
            # Button to navigate to Product Detail View
            if col.button("View Details", key=f"view_detail_{row['id']}"):
                st.session_state.selected_product_id = row['id']
                st.session_state.current_view = 'detail'
                st.rerun()

def product_detail_view():
    """Displays single product details and allows adding to cart."""
    product_id = st.session_state.selected_product_id
    if not product_id:
        st.error("No product selected.")
        st.session_state.current_view = 'catalog'
        return

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM PRODUCTS WHERE id = ?", (product_id,))
    product_row = c.fetchone()
    
    if not product_row:
        st.error("Product not found.")
        st.session_state.current_view = 'catalog'
        return
        
    product = dict(product_row)

    st.title(f"✨ {product['name']} Details")

    col_img, col_info = st.columns([1, 2])
    
    with col_img:
        st.image(product['image_url'], caption=product['name'], use_column_width=True)

    with col_info:
        st.metric("Price", f"${product['price']:.2f}")
        st.markdown(f"**Description:** High-quality T-shirt made from organic cotton.")
        
        # Allow selection of quantity
        quantity = st.number_input("Quantity", min_value=1, value=1, step=1, key="detail_qty")
        
        st.markdown("---")
        
        if st.button(f"Add {quantity}x to Cart", type="primary", key="add_to_cart_detail"):
            add_to_cart(product['id'], quantity)
            st.session_state.selected_product_id = None # Clear selection
            st.session_state.current_view = 'catalog' # Go back to catalog
            # add_to_cart already calls rerun
        
        if st.button("Back to Catalog", key="back_from_detail"):
            st.session_state.selected_product_id = None
            st.session_state.current_view = 'catalog'
            st.rerun()


@st.cache_data(show_spinner="Loading order history...")
def get_order_history(user_id):
    """Fetches user order history, cached by user_id."""
    conn = get_db_connection()
    order_history_df = pd.read_sql_query(
        "SELECT order_id, total_amount, tracking_id, order_date FROM ORDERS WHERE user_id = ? ORDER BY order_date DESC", 
        conn, 
        params=(user_id,)
    )
    return order_history_df

def user_profile_view():
    """Displays user information and order history."""
    user_id = st.session_state.username
    st.title(f"👤 User Profile: {user_id}")
    
    st.subheader("Account Details")
    st.markdown(f"**Username:** `{user_id}`")
    st.markdown(f"**Role:** `{st.session_state.role.capitalize()}`")

    st.subheader("Your Order History")
    # Optimization: Use cached order history
    order_history_df = get_order_history(user_id)

    if order_history_df.empty:
        st.info("You have no past orders yet.")
    else:
        st.dataframe(
            order_history_df,
            column_config={
                "order_id": "Order ID",
                "total_amount": st.column_config.NumberColumn("Total Paid ($)", format="$%.2f"),
                "tracking_id": "Tracking ID",
                "order_date": "Date Placed",
            },
            hide_index=True
        )

def customer_faq_enquiries():
    """Section for FAQs and enquiries."""
    st.markdown("### ❓ Customer Enquiries & FAQ")
    st.markdown("""
        **Q: How long does shipping take?**
        A: Standard shipping takes 5-7 business days.
        **Q: What is your return policy?**
        A: We accept returns within 30 days of purchase.
        """)
    st.subheader("Contact Us")
    st.info("Email support@tshirts.com for enquiries.")
# --- MAIN APP LAYOUT ---

def main_app():
    """The main entry point for the Streamlit application."""
    init_db()

    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/T-shirt_blue_outline.svg/100px-T-shirt_blue_outline.svg.png")
        st.title("T-Shirt Shop")

        if st.session_state.logged_in:
            st.success(f"User: {st.session_state.username} ({st.session_state.role.capitalize()})")
            if st.button("Logout", key="logout_btn"): logout()

            if st.session_state.role == 'customer':
                st.divider()
                
                # Navigation links
                if st.button("🏠 Catalog", key="catalog_link"):
                    st.session_state.current_view = 'catalog'
                    st.session_state.checkout_stage = 'catalog'
                    st.rerun()

                if st.button("👤 User Profile", key="profile_btn"):
                    st.session_state.current_view = 'profile'
                    st.session_state.checkout_stage = 'catalog'
                    st.rerun()

                st.divider()
                st.subheader("🛒 Your Cart")
                # Optimization: Pass user_id and cart_version to get cached data
                cart_df = get_user_cart(st.session_state.username, st.session_state.cart_version)
                
                if cart_df.empty:
                    st.markdown("Your cart is empty.")
                else:
                    total = (cart_df['price'] * cart_df['quantity']).sum()
                    st.markdown(f"Items: **{cart_df['quantity'].sum()}**")
                    st.metric("Total", f"${total:.2f}")

                    if st.button("Proceed to Checkout", key="buy_btn", type="primary"):
                        st.session_state.checkout_stage = 'payment'
                        st.session_state.current_view = 'catalog' # Keep view context clean
                        st.session_state.checkout_substage = 'payment_form'
                        st.session_state.coupon_code = None # Reset coupon on starting checkout
                        st.session_state.discount_rate = 0.0 # Reset discount
                        st.rerun()
        else:
            auth_forms()
            st.markdown("---")
            st.caption("Admin: `admin` / `adminpass`")
            st.caption("Customer: `customer1` / `custpass`")


    # Main Content Area
    if not st.session_state.logged_in:
        st.title("T-Shirt Inventory Portal")
        st.info("Please log in to proceed.")

    elif st.session_state.role == 'admin':
        st.title("👨‍💻 Admin Dashboard")
        tab1, tab2 = st.tabs(["Add Product", "View Inventory"])
        with tab1: admin_add_product()
        # Optimization: Call wrapper function for cached display
        with tab2: display_admin_inventory()

    elif st.session_state.role == 'customer':
        view = st.session_state.get('current_view', 'catalog')
        checkout_stage = st.session_state.get('checkout_stage', 'catalog')

        # Checkout overrides all other views
        if checkout_stage == 'payment':
            st.title("Secure Checkout")
            # Optimization: Pass the immediately retrieved cart to avoid a duplicate fetch inside checkout
            cart_df_for_checkout = get_user_cart(st.session_state.username, st.session_state.cart_version)
            customer_checkout(cart_df_for_checkout)
        
        # Other views (Catalog/Detail/Profile)
        elif view == 'profile':
            user_profile_view()
            
        elif view == 'detail':
            product_detail_view()

        else: # Default: 'catalog' view
            st.title("Welcome to the Customer Shop")
            tab1, tab2 = st.tabs(["T-Shirt Catalog", "FAQ / Enquiries"])
            with tab1: customer_browse_products()
            with tab2: customer_faq_enquiries()

if __name__ == '__main__':
    main_app()
