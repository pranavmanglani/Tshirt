import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import time # Added for fake delivery simulation

# --- CONFIGURATION & UTILITIES ---

# Set Streamlit page configuration
st.set_page_config(
    page_title="T-Shirt Inventory System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state for user authentication
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'role' not in st.session_state:
    st.session_state.role = None
# New state for managing customer flow: 'catalog', 'payment'
if 'checkout_stage' not in st.session_state:
    st.session_state.checkout_stage = 'catalog'
if 'checkout_substage' not in st.session_state:
    st.session_state.checkout_substage = None

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect('inventory.db')
    return conn

def hash_password(password):
    """Hashes the password for secure storage."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """
    Initializes the database tables and populates initial admin/product data.
    This function should only run once.
    """
    conn = get_db_connection()
    c = conn.cursor()

    # 1. USERS Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS USERS (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # 2. PRODUCTS Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS PRODUCTS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            size TEXT NOT NULL,
            image_url TEXT
        )
    ''')

    # 3. CART Table (stores persistent user cart)
    c.execute('''
        CREATE TABLE IF NOT EXISTS CART (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES USERS(username),
            FOREIGN KEY(product_id) REFERENCES PRODUCTS(id),
            UNIQUE(user_id, product_id)
        )
    ''')
    
    # 4. ORDERS Table (for logging successful transactions)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ORDERS (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            total_amount REAL NOT NULL,
            tracking_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            shipping_address TEXT,
            FOREIGN KEY(user_id) REFERENCES USERS(username)
        )
    ''')

    # Add initial admin user if not exists
    try:
        c.execute("INSERT INTO USERS (username, password, role) VALUES (?, ?, ?)",
                  ('admin', hash_password('adminpass'), 'admin'))
        c.execute("INSERT INTO USERS (username, password, role) VALUES (?, ?, ?)",
                  ('customer1', hash_password('custpass'), 'customer'))
        conn.commit()
    except sqlite3.IntegrityError:
        # Admin already exists
        pass

    # Add initial products if not exists
    try:
        initial_products = [
            ("Classic Navy Tee", 24.99, "M", "https://placehold.co/150x150/1C3144/FFFFFF?text=Navy+Tee"),
            ("Summer V-Neck", 19.50, "S", "https://placehold.co/150x150/FFCC00/000000?text=Yellow+V-Neck"),
            ("Oversized Black Hoodie", 49.99, "L", "https://placehold.co/150x150/000000/FFFFFF?text=Black+Hoodie"),
            ("Striped Casual Shirt", 35.00, "XL", "https://placehold.co/150x150/93A3BC/FFFFFF?text=Striped+Shirt"),
        ]
        for name, price, size, url in initial_products:
            c.execute("INSERT INTO PRODUCTS (name, price, size, image_url) VALUES (?, ?, ?, ?)",
                      (name, price, size, url))
        conn.commit()
    except sqlite3.IntegrityError:
        # Products already exist (though less likely with AUTOINCREMENT ID)
        pass

    conn.close()

# --- AUTHENTICATION FUNCTIONS ---

def authenticate(username, password):
    """Checks credentials and returns user role or None."""
    conn = get_db_connection()
    c = conn.cursor()
    hashed_password = hash_password(password)
    c.execute("SELECT role FROM USERS WHERE username = ? AND password = ?",
              (username, hashed_password))
    user = c.fetchone()
    conn.close()
    if user:
        return user[0]
    return None

def sign_up_user(username, password):
    """Adds a new customer user to the database."""
    conn = get_db_connection()
    c = conn.cursor()
    hashed_password = hash_password(password)

    try:
        # Check if username already exists
        c.execute("SELECT username FROM USERS WHERE username = ?", (username,))
        if c.fetchone():
            return "Username already exists. Please choose a different one."

        # Insert new user as 'customer'
        c.execute("INSERT INTO USERS (username, password, role) VALUES (?, ?, ?)",
                  (username, hashed_password, 'customer'))
        conn.commit()
        return "Success"
    except Exception as e:
        return f"Database error during sign up: {e}"
    finally:
        conn.close()

def auth_forms():
    """Displays the login and sign up forms using tabs."""
    
    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    # --- LOGIN TAB ---
    with tab_login:
        st.subheader("Existing User Login")
        with st.form("login_form_tab", clear_on_submit=False): 
            username = st.text_input("Username (Login)")
            password = st.text_input("Password (Login)", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                role = authenticate(username, password)
                if role:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = role
                    st.session_state.checkout_stage = 'catalog' # Reset stage on successful login
                    st.success(f"Welcome, {username}! Logged in as {role.capitalize()}.")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
                    st.session_state.logged_in = False
                    st.session_state.username = None
                    st.session_state.role = None
    
    # --- SIGN UP TAB ---
    with tab_signup:
        st.subheader("New Customer Sign Up")
        with st.form("signup_form", clear_on_submit=True):
            new_username = st.text_input("Choose Username (Sign Up)")
            new_password = st.text_input("Choose Password (Sign Up)", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            
            submitted_signup = st.form_submit_button("Create Account")

            if submitted_signup:
                if not new_username or not new_password or not confirm_password:
                     st.error("All fields are required.")
                elif new_password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(new_username) < 4 or len(new_password) < 6:
                    st.error("Username must be at least 4 characters and password at least 6 characters.")
                else:
                    result = sign_up_user(new_username, new_password)
                    if result == "Success":
                        st.success("Account created successfully! Please switch to the Login tab to sign in.")
                    else:
                        st.error(result)

def logout():
    """Logs out the user and clears session state."""
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.checkout_stage = 'catalog'
    st.session_state.checkout_substage = None
    st.info("You have been logged out.")
    st.rerun()

# --- ADMIN FEATURES (CRUD) ---

def admin_add_product():
    """Form to add a new product to the inventory."""
    st.markdown("### 👕 Add New T-Shirt Product")

    with st.form("add_product_form"):
        name = st.text_input("Product Name (e.g., 'Red Comfort Fit Tee')")
        price = st.number_input("Price (e.g., 29.99)", min_value=0.01, format="%.2f")
        size = st.selectbox("Size", ["XS", "S", "M", "L", "XL", "XXL"])
        image_url = st.text_input("Image URL (e.g., https://placehold.co/150x150/...)")
        
        submitted = st.form_submit_button("Add Product")

        if submitted:
            if not name or not image_url:
                st.error("Please fill in all mandatory fields (Name and Image URL).")
                return

            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("INSERT INTO PRODUCTS (name, price, size, image_url) VALUES (?, ?, ?, ?)",
                          (name, price, size, image_url))
                conn.commit()
                st.success(f"Product '{name}' added successfully!")
            except Exception as e:
                st.error(f"Error adding product: {e}")
            finally:
                conn.close()

def admin_view_inventory():
    """Displays the current product inventory using pandas."""
    st.markdown("### 📦 Current Inventory")
    
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)
    conn.close()
    
    if df.empty:
        st.info("The inventory is currently empty.")
    else:
        # Display the DataFrame in an interactive table
        st.dataframe(
            df,
            column_config={
                "id": "ID",
                "name": "Product Name",
                "price": st.column_config.NumberColumn("Price ($)", format="$%.2f"),
                "size": "Size",
                "image_url": "Image Link"
            },
            hide_index=True,
        )

# --- CUSTOMER FEATURES (Browsing, Cart, FAQ) ---

def customer_browse_products():
    """Displays all products and allows adding them to the cart."""
    st.markdown("### 🛍️ Browse Our T-Shirts")

    conn = get_db_connection()
    products_df = pd.read_sql_query("SELECT id, name, price, size, image_url FROM PRODUCTS", conn)
    conn.close()

    if products_df.empty:
        st.info("No products are available right now. Please check back later!")
        return

    # Create a layout with up to 3 columns
    cols = st.columns(3)
    
    for index, row in products_df.iterrows():
        col = cols[index % 3] # Cycle through columns
        
        with col.container(border=True):
            st.image(row['image_url'], caption=row['name'], width=150)
            st.markdown(f"**{row['name']}**")
            st.markdown(f"**Price:** \${row['price']:.2f}")
            st.markdown(f"**Size:** {row['size']}")

            # Add to Cart Button (Unique key is essential)
            if col.button("Add to Cart", key=f"add_cart_{row['id']}"):
                add_to_cart(row['id'], 1)

def add_to_cart(product_id, quantity):
    """Adds a product to the user's persistent cart in the database."""
    user_id = st.session_state.username
    conn = get_db_connection()
    c = conn.cursor()

    try:
        # Check if product is already in cart
        c.execute("SELECT quantity FROM CART WHERE user_id = ? AND product_id = ?", 
                  (user_id, product_id))
        cart_item = c.fetchone()

        if cart_item:
            # If exists, update quantity
            new_quantity = cart_item[0] + quantity
            c.execute("UPDATE CART SET quantity = ? WHERE user_id = ? AND product_id = ?",
                      (new_quantity, user_id, product_id))
            st.toast(f"Updated product quantity in cart to {new_quantity}!", icon="🛒")
        else:
            # If new, insert
            c.execute("INSERT INTO CART (user_id, product_id, quantity) VALUES (?, ?, ?)",
                      (user_id, product_id, quantity))
            st.toast(f"Product added to cart!", icon="🛒")

        conn.commit()

    except Exception as e:
        st.error(f"Could not add item to cart: {e}")
    finally:
        conn.close()
        # Rerun to refresh the cart display in the sidebar
        st.rerun()

def get_user_cart():
    """Retrieves the user's current cart items, joining with product details."""
    user_id = st.session_state.username
    conn = get_db_connection()
    
    # SQL query to join CART and PRODUCTS tables
    # NOTE: Using parameterized queries for user input is safer, but user_id is from session, minimizing risk here.
    query = f"""
    SELECT 
        T1.id AS cart_item_id, 
        T2.name, 
        T2.price, 
        T1.quantity,
        T2.size,
        T2.image_url
    FROM CART AS T1
    JOIN PRODUCTS AS T2 ON T1.product_id = T2.id
    WHERE T1.user_id = '{user_id}'
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def clear_user_cart(user_id):
    """Removes all items from the user's cart."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM CART WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def customer_checkout(cart_df):
    """Handles the multi-stage fake payment and delivery process."""
    user_id = st.session_state.username
    
    # Check for empty cart
    if cart_df.empty:
        st.error("Your cart is empty. Please add items to buy.")
        st.session_state.checkout_stage = 'catalog'
        return

    # ------------------ STAGE 1: PAYMENT FORM ------------------
    if st.session_state.get('checkout_substage') != 'delivered':
        
        st.subheader("1. Order Summary")
        total = (cart_df['price'] * cart_df['quantity']).sum()
        
        # Display cart contents in a neat table
        st.dataframe(
            cart_df[['name', 'size', 'quantity', 'price']],
            column_config={
                "name": "Product",
                "size": "Size",
                "price": st.column_config.NumberColumn("Price ($)", format="$%.2f"),
                "quantity": "Qty",
            },
            hide_index=True,
        )
        st.metric("Total Payable", f"${total:.2f}")
        st.markdown("---")


        st.subheader("2. 💳 Fake Payment Gateway")
        with st.form("payment_form", clear_on_submit=False):
            st.warning("⚠️ This is a simulated payment gateway. The transaction will be faked for demonstration.")
            
            # Fake fields
            card_number = st.text_input("Card Number", max_chars=16, value="4111 1111 1111 1111")
            col1, col2 = st.columns(2)
            with col1:
                expiry = st.text_input("Expiry Date (MM/YY)", max_chars=5, value="12/26")
            with col2:
                cvv = st.text_input("CVV", type="password", max_chars=3, value="123")
                
            address = st.text_area("Shipping Address", "123 Main St, Springfield, Anystate, 12345")
            
            submitted = st.form_submit_button("Process Payment & Place Order", type="primary")

            if submitted:
                # Simple validation for non-empty fields
                if len(card_number.replace(' ', '')) != 16 or len(cvv) != 3 or not address:
                    st.error("Please enter valid fake payment details and a shipping address.")
                    return
                
                # Payment Simulation Success
                st.session_state.checkout_substage = 'delivered'
                st.session_state.order_total = total
                st.session_state.shipping_address = address
                st.rerun() # Rerun to move to the next stage

    # ------------------ STAGE 2: DELIVERY SIMULATION & CONFIRMATION ------------------
    if st.session_state.get('checkout_substage') == 'delivered':
        
        # Log Order details
        # Using a combination of hashed user ID and timestamp for a fake tracking ID
        tracking_id = f"DEL-{hash_password(user_id)[:6].upper()}-{pd.Timestamp.now().strftime('%d%H%M')}"
        
        conn = get_db_connection()
        c = conn.cursor()
        
        try:
            # Save the fake order
            c.execute("INSERT INTO ORDERS (user_id, total_amount, tracking_id, order_date, shipping_address) VALUES (?, ?, ?, ?, ?)",
                      (user_id, st.session_state.order_total, tracking_id, str(pd.Timestamp.now()), st.session_state.shipping_address))
            conn.commit()
            
            # Clear the cart (simulating order completion)
            clear_user_cart(user_id)
            
            st.balloons()
            st.success("🎉 Purchase Successful! Your payment was processed.")

            st.markdown("---")
            st.subheader("3. 🚚 Fake Delivery System Confirmation")
            st.info("Your order has been transferred to our shipping department and is now **Processing**.")
            
            # Display simulated delivery details
            st.markdown(f"**Tracking ID:** `{tracking_id}`")
            st.markdown(f"**Shipping Address:** {st.session_state.shipping_address}")
            estimated_delivery = pd.Timestamp.now() + pd.Timedelta(days=7)
            st.markdown(f"**Estimated Delivery:** **{estimated_delivery.strftime('%A, %B %d, %Y')}**")
            
            st.markdown("---")
            if st.button("Back to Shopping", type="secondary"):
                # Reset all checkout states and go back to catalog
                st.session_state.checkout_stage = 'catalog'
                st.session_state.checkout_substage = None
                st.session_state.order_total = None
                st.session_state.shipping_address = None
                st.rerun()
                
        except Exception as e:
            st.error(f"Error saving order: {e}")
        finally:
            conn.close()
            # Reset sub-stage in case of an error to prevent looping
            st.session_state.checkout_substage = None

def customer_faq_enquiries():
    """Section for FAQs and enquiries."""
    st.markdown("### ❓ Customer Enquiries & FAQ")
    
    st.markdown(
        """
        **Q: How long does shipping take?**
        A: Standard shipping takes 5-7 business days. Express options are available at checkout.

        **Q: What is your return policy?**
        A: We accept returns within 30 days of purchase, provided the item is unworn and has the original tags.

        **Q: Can I change my order after placing it?**
        A: We process orders quickly, so changes may not be possible. Please contact support immediately.
        """
    )
    
    st.subheader("Contact Us")
    st.info("For any other enquiries, please email support@tshirts.com. We aim to respond within 24 hours.")

# --- MAIN APP LAYOUT ---

def main_app():
    """The main entry point for the Streamlit application."""
    # Ensure database is initialized
    init_db()

    # Sidebar for Login/Logout and Cart Status
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/T-shirt_blue_outline.svg/100px-T-shirt_blue_outline.svg.png")
        st.title("T-Shirt Shop")

        if st.session_state.logged_in:
            st.success(f"User: {st.session_state.username} ({st.session_state.role.capitalize()})")
            if st.button("Logout", key="logout_btn"):
                logout()

            # Display persistent cart in the sidebar for customers
            if st.session_state.role == 'customer':
                st.divider()
                st.subheader("🛒 Your Cart")
                cart_df = get_user_cart()
                
                if cart_df.empty:
                    st.markdown("Your cart is empty.")
                else:
                    # Calculate total without displayi
