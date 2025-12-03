import streamlit as st
import sqlite3
import pandas as pd
import hashlib

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

def login_form():
    """Displays the login form."""
    st.subheader("Inventory System Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            role = authenticate(username, password)
            if role:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = role
                st.success(f"Welcome, {username}! Logged in as {role.capitalize()}.")
                # Rerun to switch to the appropriate dashboard
                st.rerun()
            else:
                st.error("Invalid username or password.")
                st.session_state.logged_in = False
                st.session_state.username = None
                st.session_state.role = None

def logout():
    """Logs out the user and clears session state."""
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None
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
    query = f"""
    SELECT 
        T1.id AS cart_item_id, 
        T2.name, 
        T2.price, 
        T1.quantity,
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
    """Simulates the 'Buy' process."""
    if cart_df.empty:
        st.error("Your cart is empty. Please add items to buy.")
        return
    
    total = (cart_df['price'] * cart_df['quantity']).sum()
    
    st.subheader("Confirm Purchase")
    st.write(f"Total payable amount: **${total:.2f}**")
    
    if st.button("Complete Purchase", type="primary"):
        clear_user_cart(st.session_state.username)
        st.balloons()
        st.success("🎉 Purchase successful! Your order is being processed. Thank you for shopping with us.")
        st.rerun() # Refresh the view to show an empty cart

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
                    # Display cart items and calculate total
                    for index, row in cart_df.iterrows():
                        st.markdown(f"**{row['name']}**")
                        st.markdown(f"Quantity: {row['quantity']} | \${row['price']:.2f} each")
                        st.markdown("---")
                    
                    total = (cart_df['price'] * cart_df['quantity']).sum()
                    st.metric("Cart Total", f"${total:.2f}")

                    # Buy Button
                    if st.button("Proceed to Buy", key="buy_btn", type="primary"):
                        st.session_state.checkout_mode = True
                        st.rerun()

        else:
            login_form()
            st.markdown("---")
            st.caption("Admin User: `admin` / `adminpass`")
            st.caption("Customer User: `customer1` / `custpass`")


    # Main Content Area
    if not st.session_state.logged_in:
        st.title("Welcome to the T-Shirt Inventory Portal")
        st.info("Please log in on the sidebar to access the Customer Shop or Admin Dashboard.")

    elif st.session_state.role == 'admin':
        st.title("👨‍💻 Admin Dashboard")
        
        # Tabs for Admin functionality
        tab1, tab2 = st.tabs(["Add Product", "View Inventory (Pandas)"])
        
        with tab1:
            admin_add_product()

        with tab2:
            admin_view_inventory()

    elif st.session_state.role == 'customer':
        if st.session_state.get('checkout_mode', False):
            st.title("Checkout")
            cart_df = get_user_cart()
            customer_checkout(cart_df)
            st.session_state.checkout_mode = False # Reset mode after purchase attempt or confirmation

        else:
            st.title("Welcome to the Customer Shop")

            # Tabs for Customer functionality
            tab1, tab2 = st.tabs(["T-Shirt Catalog", "FAQ / Enquiries"])
            
            with tab1:
                customer_browse_products()

            with tab2:
                customer_faq_enquiries()


if __name__ == '__main__':
    main_app()
