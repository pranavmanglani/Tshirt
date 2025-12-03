#Optima source code corps.
import streamlit as st
import sqlite3
import pandas as pd
import hashlib

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
st.session_state.setdefault('checkout_stage', 'catalog') # 'catalog' or 'payment'
st.session_state.setdefault('checkout_substage', None) # 'payment_form' or 'delivered'

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    return sqlite3.connect('inventory.db')

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
            c.execute("INSERT INTO PRODUCTS (name, price, size, image_url) VALUES (?, ?, ?, ?)", (name, price, size, url))
            conn.commit()
        except sqlite3.IntegrityError: pass # Product exists

    conn.close()

# --- AUTHENTICATION & SESSION ---

def authenticate(username, password):
    """Checks credentials and returns user role or None."""
    conn = get_db_connection()
    c = conn.cursor()
    hashed_password = hash_password(password)
    c.execute("SELECT role FROM USERS WHERE username = ? AND password = ?", (username, hashed_password))
    user = c.fetchone()
    conn.close()
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
    finally:
        conn.close()

def logout():
    """Logs out the user and resets all session states related to login/checkout."""
    st.session_state.logged_in = False
    st.session_state.username = st.session_state.role = st.session_state.checkout_stage = st.session_state.checkout_substage = None
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
                    st.success(f"Product '{name}' added successfully!")
                except Exception as e: st.error(f"Error adding product: {e}")
                finally: conn.close()

def admin_view_inventory():
    """Displays the current product inventory."""
    st.markdown("### 📦 Current Inventory")
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)
    conn.close()
    
    if df.empty: st.info("The inventory is currently empty.")
    else: st.dataframe(df, column_config={"price": st.column_config.NumberColumn("Price ($)", format="$%.2f")}, hide_index=True)

# --- CUSTOMER FEATURES ---

def get_user_cart():
    """Retrieves the user's current cart items."""
    user_id = st.session_state.username
    conn = get_db_connection()
    query = f"""
    SELECT T1.id AS cart_item_id, T2.name, T2.price, T1.quantity, T2.size
    FROM CART AS T1 JOIN PRODUCTS AS T2 ON T1.product_id = T2.id
    WHERE T1.user_id = '{user_id}'
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_to_cart(product_id, quantity):
    """Adds or updates a product in the user's cart."""
    user_id = st.session_state.username
    conn = get_db_connection()
    c = conn.cursor()
    try:
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
    except Exception as e:
        st.error(f"Could not add item: {e}")
    finally:
        conn.close()
        st.rerun()

def remove_from_cart(cart_item_id):
    """Removes a single item entry from the cart based on its ID."""
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM CART WHERE id = ?", (cart_item_id,))
        conn.commit()
        st.toast("Item removed from cart!", icon="❌")
    except Exception as e:
        st.error(f"Error removing item: {e}")
    finally:
        conn.close()
        st.rerun()

def clear_user_cart(user_id):
    """Removes all items from the user's cart."""
    conn = get_db_connection()
    conn.execute("DELETE FROM CART WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def customer_checkout(cart_df):
    """Handles the multi-stage fake payment and delivery process."""
    user_id = st.session_state.username
    if cart_df.empty:
        st.error("Your cart is empty. Please add items to buy.")
        st.session_state.checkout_stage = 'catalog'
        return

    # --- STAGE 1: PAYMENT FORM ---
    if st.session_state.get('checkout_substage') != 'delivered':
        total = (cart_df['price'] * cart_df['quantity']).sum()
        st.subheader("1. Order Summary")
        
        # Display cart with remove buttons
        st.dataframe(cart_df[['name', 'size', 'quantity', 'price']], hide_index=True)
        for index, row in cart_df.iterrows():
            st.button(f"Remove 1x {row['name']} ({row['size']})", key=f"remove_{row['cart_item_id']}", 
                      on_click=remove_from_cart, args=(row['cart_item_id'],))

        st.metric("Total Payable", f"${total:.2f}")
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
                # Basic validation
                if len(card_number.replace(' ', '')) != 16 or len(cvv) != 3 or not address:
                    st.error("Please enter valid fake payment details.")
                else:
                    st.session_state.checkout_substage = 'delivered'
                    st.session_state.order_total = total
                    st.session_state.shipping_address = address
                    st.rerun()

    # --- STAGE 2: DELIVERY SIMULATION & CONFIRMATION ---
    if st.session_state.get('checkout_substage') == 'delivered':
        
        tracking_id = f"DEL-{hashlib.sha256(user_id.encode()).hexdigest()[:6].upper()}-{pd.Timestamp.now().strftime('%d%H%M')}"
        
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO ORDERS VALUES (NULL, ?, ?, ?, ?, ?)",
                      (user_id, st.session_state.order_total, tracking_id, str(pd.Timestamp.now()), st.session_state.shipping_address))
            conn.commit()
            clear_user_cart(user_id)
            
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
                st.session_state.checkout_substage = None
                st.rerun()
                
        except Exception as e:
            st.error(f"Error saving order: {e}")
        finally:
            conn.close()

def customer_browse_products():
    """Displays all products and allows adding them to the cart."""
    st.markdown("### 🛍️ Browse Our T-Shirts")
    conn = get_db_connection()
    products_df = pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)
    conn.close()

    if products_df.empty: st.info("No products available.")
    else:
        cols = st.columns(3)
        for index, row in products_df.iterrows():
            col = cols[index % 3]
            with col.container(border=True):
                st.image(row['image_url'], caption=row['name'], width=150)
                st.markdown(f"**{row['name']}**")
                st.markdown(f"**Price:** \${row['price']:.2f} | **Size:** {row['size']}")
                if col.button("Add to Cart", key=f"add_cart_{row['id']}"):
                    add_to_cart(row['id'], 1)

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
                st.subheader("🛒 Your Cart")
                cart_df = get_user_cart()
                
                if cart_df.empty:
                    st.markdown("Your cart is empty.")
                else:
                    total = (cart_df['price'] * cart_df['quantity']).sum()
                    st.markdown(f"Items: **{cart_df['quantity'].sum()}**")
                    st.metric("Total", f"${total:.2f}")

                    if st.button("Proceed to Buy", key="buy_btn", type="primary"):
                        st.session_state.checkout_stage = 'payment'
                        st.session_state.checkout_substage = 'payment_form'
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
        with tab2: admin_view_inventory()

    elif st.session_state.role == 'customer':
        if st.session_state.checkout_stage == 'payment':
            st.title("Secure Checkout")
            customer_checkout(get_user_cart())
        else: # Stage 'catalog'
            st.title("Welcome to the Customer Shop")
            tab1, tab2 = st.tabs(["T-Shirt Catalog", "FAQ / Enquiries"])
            with tab1: customer_browse_products()
            with tab2: customer_faq_enquiries()

if __name__ == '__main__':
    main_app()
#Optima source code corps.
