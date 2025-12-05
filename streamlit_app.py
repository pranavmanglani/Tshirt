import streamlit as st
import sqlite3
import hashlib
from datetime import datetime
import json
import base64
import time

# --- Configuration ---
DB_NAME = 'tshirt_db.sqlite'

# Use st.cache_resource to ensure the database connection is a singleton
# and is created only once, preventing concurrent access issues.
# check_same_thread=False is necessary for SQLite in Streamlit's multi-threaded environment.
@st.cache_resource
def get_db_connection():
    """
    Establishes and caches the SQLite database connection.
    This function runs only once across all sessions.
    """
    try:
        # connect to the database. check_same_thread=False is crucial for Streamlit.
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Immediately run the initialization logic after connecting
        _initialize_schema_and_data(conn)
        
        return conn
    except Exception as e:
        st.error(f"Failed to establish or initialize database connection: {e}")
        # In a real app, you might raise here to stop the script
        return None

def _initialize_schema_and_data(conn):
    """Initializes database tables and populates initial data using the established connection."""
    c = conn.cursor()

    # 1. Define all necessary tables using IF NOT EXISTS for idempotence
    c.executescript('''
        CREATE TABLE IF NOT EXISTS USERS (
            username TEXT PRIMARY KEY,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS TSHIRTS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image_url TEXT,
            stock INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS CART_ITEMS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            tshirt_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (username) REFERENCES USERS(username),
            FOREIGN KEY (tshirt_id) REFERENCES TSHIRTS(id),
            UNIQUE (username, tshirt_id)
        );

        CREATE TABLE IF NOT EXISTS ORDERS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            order_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (username) REFERENCES USERS(username)
        );

        CREATE TABLE IF NOT EXISTS ORDER_DETAILS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            tshirt_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_at_purchase REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES ORDERS(id),
            FOREIGN KEY (tshirt_id) REFERENCES TSHIRTS(id)
        );
    ''')
    
    # 2. Add initial users and mock products
    try:
        # Hashing passwords for security
        admin_pass_hash = hashlib.sha256('adminpass'.encode()).hexdigest()
        customer1_pass_hash = hashlib.sha256('custpass'.encode()).hexdigest()

        # Insert users only if they don't exist
        c.execute("INSERT OR IGNORE INTO USERS (username, hashed_password, role) VALUES (?, ?, ?)", 
                  ('admin', admin_pass_hash, 'admin'))
        c.execute("INSERT OR IGNORE INTO USERS (username, hashed_password, role) VALUES (?, ?, ?)", 
                  ('customer1', customer1_pass_hash, 'customer'))
        
        # Insert mock products only if the table is empty
        c.execute("SELECT COUNT(*) FROM TSHIRTS")
        if c.fetchone()[0] == 0:
            mock_products = [
                ('The Gemini Tee', 'A classic tee featuring the Gemini logo in deep blue.', 29.99, 'https://placehold.co/400x400/0000FF/FFFFFF?text=Gemini+Tee', 50),
                ('Python Dev Shirt', 'Elegant black shirt for the coding enthusiast.', 34.99, 'https://placehold.co/400x400/306998/FFFFFF?text=Python+Code', 30),
                ('Streamlit Flow Tee', 'Simple design highlighting data flow.', 24.99, 'https://placehold.co/400x400/FF4B4B/FFFFFF?text=Streamlit+App', 75),
            ]
            c.executemany("INSERT INTO TSHIRTS (name, description, price, image_url, stock) VALUES (?, ?, ?, ?, ?)", mock_products)

        conn.commit()

    except sqlite3.IntegrityError: 
        # This catches primary key violations if we used INSERT instead of INSERT OR IGNORE
        pass
    except Exception as e:
        # Catch any other error during initialization
        st.warning(f"Warning: Could not populate initial data. This may be expected if data already exists: {e}")
        conn.rollback()

# --- Authentication and Utility Functions (Assuming they exist) ---

def hash_password(password):
    """Hashes the given password."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, provided_password):
    """Verifies a provided password against the stored hash."""
    return stored_hash == hash_password(provided_password)

# ... (rest of your functions like get_user, add_to_cart, etc.) ...

# --- Main App Entry Point ---

def main_app():
    """The main entry point for the Streamlit application."""
    # Since get_db_connection is cached and handles initialization,
    # simply calling it here ensures the DB is ready on the first run.
    db = get_db_connection()
    if db is None:
        st.stop() # Stop execution if DB connection failed

    # Initialize session state for user authentication if it's not present
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.role = None
        st.session_state.page = 'Shop'
        st.session_state.cart = {} # {tshirt_id: quantity}

    # ... rest of the app logic ...

    # The rest of the script is unchanged from the previous version.
    pass # Placeholder for the rest of your app content
