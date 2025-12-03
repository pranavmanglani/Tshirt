import streamlit as st
import sqlite3
import pandas as pd
import hashlib

# --- CONFIGURATION & UTILITIES ---

st.set_page_config(page_title="Minimal T-Shirt Shop", layout="wide")
st.session_state.setdefault('logged_in', False)
st.session_state.setdefault('username', None)
st.session_state.setdefault('role', None)
st.session_state.setdefault('cart_version', 0)
st.session_state.setdefault('product_version', 0) # For cache control

@st.cache_resource
def get_db_connection():
    """Initializes and caches SQLite connection."""
    conn = sqlite3.connect('inventory.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row 
    return conn

def hash_password(password):
    """Hashes the password."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Initializes database tables and default data."""
    conn = get_db_connection()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS USERS (username TEXT PRIMARY KEY, password TEXT NOT NULL, role TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS PRODUCTS (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL, size TEXT NOT NULL, image_url TEXT);
        CREATE TABLE IF NOT EXISTS CART (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, UNIQUE(user_id, product_id));
        CREATE TABLE IF NOT EXISTS ORDERS (order_id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, total_amount REAL NOT NULL, tracking_id TEXT NOT NULL, order_date TEXT NOT NULL);
    ''')

    try:
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('admin', hash_password('adminpass'), 'admin'))
        c.execute("INSERT INTO USERS VALUES (?, ?, ?)", ('customer1', hash_password('custpass'), 'customer'))
        conn.commit()
    except sqlite3.IntegrityError: pass # Users exist

    initial_products = [
        ("Classic Navy Tee", 24.99, "M", "https://placehold.co/150x150/1C3144/FFFFFF?text=Navy"),
        ("Summer V-Neck", 19.50, "S", "https://placehold.co/150x150/FFCC00/000000?text=Yellow"),
        ("Oversized Black Hoodie", 49.99, "L", "https://placehold.co/150x150/000000/FFFFFF?text=Hoodie"),
    ]
    for name, price, size, url in initial_products:
        try:
            c.execute("SELECT id FROM PRODUCTS WHERE name = ? AND size = ?", (name, size))
            if c.fetchone() is None:
                c.execute("INSERT INTO PRODUCTS VALUES (NULL, ?, ?, ?, ?)", (name, price, size, url))
                conn.commit()
        except sqlite3.IntegrityError: pass
# --- AUTHENTICATION ---

def authenticate(username, password):
    """Checks credentials and returns user role or None."""
    conn = get_db_connection()
    c = conn.cursor()
    hashed_password = hash_password(password)
    c.execute("SELECT role FROM USERS WHERE username = ? AND password = ?", (username, hashed_password))
    user = c.fetchone()
    return user[0] if user else None

def logout():
    """Logs out the user."""
    st.session_state.logged_in = False
    st.session_state.username = st.session_state.role = None
    st.session_state.cart_version = 0
    st.info("You have been logged out.")
    st.rerun()

def auth_form():
    """Displays the login form."""
    st.subheader("Login")
    with st.form("login_form", clear_on_submit=False): 
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            role = authenticate(username, password)
            if role:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = role
                st.success(f"Welcome, {username}!")
                st.rerun()
            else: st.error("Invalid username or password.")
            
# --- CART & PRODUCT FUNCTIONS ---

@st.cache_data
def get_all_products(product_version):
    """Fetches all product data."""
    conn = get_db_connection()
    return pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)

@st.cache_data
def get_user_cart(user_id, cart_version):
    """Retrieves the user's current cart items."""
    conn = get_db_connection()
    query = f"""
    SELECT T1.id AS cart_item_id, T2.id AS product_id, T2.name, T2.price, T1.quantity
    FROM CART AS T1 JOIN PRODUCTS AS T2 ON T1.product_id = T2.id
    WHERE T1.user_id = '{user_id}'
    """
    return pd.read_sql_query(query, conn)

def add_to_cart(product_id, quantity=1):
    """Adds a product to the cart."""
    user_id = st.session_state.username
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO CART VALUES (NULL, ?, ?, ?)", (user_id, product_id, quantity))
        conn.commit()
        st.session_state.cart_version += 1
        st.toast("Product added to cart!", icon="🛒")
    except sqlite3.IntegrityError:
        # If product exists, just update quantity (simplified version)
        c.execute("UPDATE CART SET quantity = quantity + ? WHERE user_id = ? AND product_id = ?", (quantity, user_id, product_id))
        conn.commit()
        st.session_state.cart_version += 1
        st.toast("Cart quantity updated!", icon="➕")
    st.rerun()

def remove_from_cart(cart_item_id):
    """Removes a single item entry from the cart."""
    conn = get_db_connection()
    conn.execute("DELETE FROM CART WHERE id = ?", (cart_item_id,))
    conn.commit()
    st.session_state.cart_version += 1
    st.toast("Item removed.", icon="❌")
    st.rerun()

def clear_user_cart(user_id):
    """Removes all items from the user's cart."""
    conn = get_db_connection()
    conn.execute("DELETE FROM CART WHERE user_id = ?", (user_id,))
    conn.commit()
    st.session_state.cart_version += 1

def finalize_order(user_id, total):
    """Simulates order placement and clears cart."""
    conn = get_db_connection()
    tracking_id = f"ORD-{hashlib.sha256(user_id.encode()).hexdigest()[:6].upper()}"
    try:
        conn.execute("INSERT INTO ORDERS VALUES (NULL, ?, ?, ?, ?)",
                      (user_id, total, tracking_id, str(pd.Timestamp.now())))
        conn.commit()
        clear_user_cart(user_id)
        st.balloons()
        st.success(f"🎉 Order placed successfully! Tracking ID: {tracking_id}")
    except Exception as e:
        st.error(f"Error saving order: {e}")

# --- DISPLAY FUNCTIONS ---

def customer_browse_products():
    """Displays products in a simple grid."""
    st.markdown("### 🛍️ Product Catalog")
    products_df = get_all_products(st.session_state.product_version)
    cols = st.columns(3)
    
    for index, row in products_df.iterrows():
        col_index = index % 3
        with cols[col_index].container(border=True):
            st.image(row['image_url'], caption=row['name'], width=100)
            st.markdown(f"**{row['name']}** - \${row['price']:.2f}")
            st.button(f"Add to Cart", key=f"add_{row['id']}", on_click=add_to_cart, args=(row['id'],))

def customer_checkout(cart_df):
    """Simplified checkout view."""
    user_id = st.session_state.username
    st.subheader("Checkout")

    if cart_df.empty:
        st.error("Your cart is empty. Please add items to buy.")
        return

    total = (cart_df['price'] * cart_df['quantity']).sum()

    st.dataframe(
        cart_df[['name', 'quantity', 'price']],
        column_config={"price": st.column_config.NumberColumn("Price ($)", format="$%.2f")},
        hide_index=True
    )
    st.metric("Total Payable", f"${total:.2f}")

    if st.button("Place Order Now (Simulated Payment)", type="primary"):
        finalize_order(user_id, total)


# --- MAIN APP LAYOUT ---

def main_app():
    """The main entry point."""
    init_db()

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("T-Shirt Shop")

        if st.session_state.logged_in:
            st.success(f"Logged in as: {st.session_state.username}")
            if st.button("Logout", key="logout_btn"): logout()

            if st.session_state.role == 'customer':
                st.divider()
                st.subheader("🛒 Cart Status")
                cart_df = get_user_cart(st.session_state.username, st.session_state.cart_version)
                total = (cart_df['price'] * cart_df['quantity']).sum()
                st.markdown(f"Items: **{cart_df['quantity'].sum()}**")
                st.metric("Total", f"${total:.2f}")
                
                # Show checkout button only if cart is not empty
                if not cart_df.empty and st.button("Go to Checkout", key="go_to_checkout"):
                    st.session_state.current_view = 'checkout'
                    st.rerun()
                elif st.session_state.get('current_view') == 'checkout' and st.button("Back to Catalog"):
                    st.session_state.current_view = 'catalog'
                    st.rerun()

        else:
            auth_form()
            st.markdown("---")
            st.caption("Admin: `admin` / `adminpass`")
            st.caption("Customer: `customer1` / `custpass`")

    # --- MAIN CONTENT ---
    if not st.session_state.logged_in:
        st.info("Please log in to browse the shop.")
    
    elif st.session_state.role == 'admin':
        st.title("👨‍💻 Admin View")
        st.markdown("### 📦 Current Inventory")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT id, name, price, size FROM PRODUCTS", conn)
        st.dataframe(df, hide_index=True)

    elif st.session_state.role == 'customer':
        view = st.session_state.get('current_view', 'catalog')
        cart_df = get_user_cart(st.session_state.username, st.session_state.cart_version)

        if view == 'checkout':
            customer_checkout(cart_df)
        else:
            customer_browse_products()

if __name__ == '__main__':
    main_app()
