import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import threading
import json 

# --- Configuration ---
st.set_page_config(layout="wide", page_title="T-Shirt Production Tracker", page_icon="👕")

# --- Database Connection and Setup (Thread-Safe SQLite) ---

# Global lock to prevent multiple threads/reruns from corrupting or fighting over database initialization
DB_INIT_LOCK = threading.Lock() 

# CRITICAL FIX 1: Cache the database file path as a resource.
@st.cache_resource
def get_db_path():
    """Returns the database file path, cached as a resource."""
    return 'tshirt_app.db'

# CRITICAL FIX 2: Thread-safe connection getter.
def get_db_connection():
    """
    Returns a new, isolated SQLite connection for the current operation.
    It uses check_same_thread=False to manage Streamlit's multi-threading, 
    but relies on the global lock during initialization to prevent data corruption.
    """
    db_path = get_db_path()
    # The check_same_thread=False parameter is necessary for Streamlit to prevent
    # "SQLite objects created in a thread can only be used in that same thread" error.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    return conn

def hash_password(password):
    """Hashes the password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """
    Initializes database tables and populates initial data.
    Uses a global lock to ensure this happens safely and only once, 
    preventing race conditions and 'database is locked' errors.
    """
    # Use the lock to ensure only one thread initializes the database at a time
    with DB_INIT_LOCK:
        conn = get_db_connection()
        c = conn.cursor()

        try:
            # --- USERS Table (Prevent Data Loss on Rerun) ---
            # 1. Create USERS table if it doesn't exist
            c.execute('''
                CREATE TABLE IF NOT EXISTS USERS (
                    username TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE, 
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL
                );
            ''')
            
            # 2. Insert default user only if the USERS table is empty
            c.execute("SELECT COUNT(*) FROM USERS")
            user_count = c.fetchone()[0]
            if user_count == 0:
                c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                          ('admin', 'admin@company.com', hash_password('adminpass'), 'admin'))
                c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                          ('customer1', 'cust1@email.com', hash_password('customerpass'), 'customer'))


            # --- DESIGNS and PRODUCTION_LOG Tables (Initial Data Setup) ---
            
            # Check if PRODUCTION_LOG table exists AND has the necessary column (production_type).
            c.execute("PRAGMA table_info(PRODUCTION_LOG)")
            prod_columns = [info[1] for info in c.fetchall()]
            
            # Check if DESIGNS table exists AND has the necessary column (retail_status).
            c.execute("PRAGMA table_info(DESIGNS)")
            design_columns = [info[1] for info in c.fetchall()]
            
            # Reinitialize if the crucial 'production_type' or the new 'retail_status' column is missing or tables are missing
            needs_init = ('production_type' not in prod_columns) or (not prod_columns) or ('retail_status' not in design_columns)

            # Only perform the destructive drop/recreate if initialization is needed
            if needs_init:
                # Drop and recreate production tables
                st.info("Re-initializing production tables to ensure all columns (including new 'retail_status') are present.")
                c.executescript('''
                    DROP TABLE IF EXISTS DESIGNS;
                    DROP TABLE IF EXISTS PRODUCTION_LOG;

                    CREATE TABLE DESIGNS (
                        design_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        price_usd REAL NOT NULL DEFAULT 19.99,
                        retail_status TEXT NOT NULL DEFAULT 'Mass' -- 'Mass' (Wholesale) or 'Retail' (Direct Customer)
                    );

                    CREATE TABLE PRODUCTION_LOG (
                        log_id INTEGER PRIMARY KEY,
                        log_date TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        size TEXT NOT NULL,
                        units_produced INTEGER NOT NULL,
                        defects INTEGER NOT NULL,
                        production_type TEXT NOT NULL
                    );
                ''')
                
                # Populate Designs (Marking some as Retail for the direct customer view)
                c.execute("INSERT INTO DESIGNS (name, description, price_usd, retail_status) VALUES (?, ?, ?, ?)", ('Cosmic Wave', 'High-fidelity screen print on premium Pima cotton. Exclusive design.', 39.99, 'Retail'))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd, retail_status) VALUES (?, ?, ?, ?)", ('Abstract Art', 'Limited edition vibrant print, premium cotton.', 55.50, 'Retail'))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd, retail_status) VALUES (?, ?, ?, ?)", ('Logo Tee', 'Standard company logo print, 100% durable cotton.', 19.99, 'Mass'))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd, retail_status) VALUES (?, ?, ?, ?)", ('Vintage Stripes', 'Classic striped design, durable everyday wear.', 17.50, 'Mass'))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd, retail_status) VALUES (?, ?, ?, ?)", ('Eco Blend Basic', 'Simple sustainable fabric blend, perfect for bulk.', 21.00, 'Mass'))


                # Production Logs (Sample data for the last 30 days)
                today = datetime.now().date()
                data = []
                
                production_types = ['Mass', 'Retail']
                
                for i in range(1, 31):
                    log_date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                    
                    # Mass production
                    data.append((log_date, 'Logo Tee', 'M', 100 + i*2, 5 + (i//5), production_types[0]))
                    data.append((log_date, 'Vintage Stripes', 'S', 50 + i*3, 2 + (i//3), production_types[0]))
                    data.append((log_date, 'Eco Blend Basic', 'L', 120 + i, 6 + (i//6), production_types[0]))
                    
                    # Retail production
                    data.append((log_date, 'Cosmic Wave', 'L', 30 + i, 1 + (i//5), production_types[1]))
                    if i <= 15:
                        data.append((log_date, 'Abstract Art', 'XL', 20 + i*2, 1 + (i//8), production_types[1]))
                    
                # Add a few logs for today
                today_str = today.strftime('%Y-%m-%d')
                data.append((today_str, 'Logo Tee', 'M', 150, 6, 'Mass'))
                data.append((today_str, 'Cosmic Wave', 'L', 80, 4, 'Retail'))
                
                # Use a specific list of columns for the insert
                insert_cols = "(log_date, product_name, size, units_produced, defects, production_type)"
                insert_placeholder = "(?, ?, ?, ?, ?, ?)"
                c.executemany(f"INSERT INTO PRODUCTION_LOG {insert_cols} VALUES {insert_placeholder}", data)
            
            conn.commit()
        except Exception as e:
            # st.error(f"Error initializing database: {e}") 
            pass 
        finally:
            conn.close() 


# --- Authentication Functions ---

def authenticate_user(username, password):
    """Checks credentials and returns the user row or None."""
    conn = get_db_connection()
    c = conn.cursor()
    
    password_hash = hash_password(password)
    # The role is now included in the SELECT query
    c.execute("SELECT * FROM USERS WHERE username = ? AND password_hash = ?", (username, password_hash))
    user = c.fetchone()
    conn.close()
    return user

def signup_user(username, email, password): 
    """Registers a new user, always assigning the 'customer' role."""
    conn = get_db_connection()
    
    try:
        # Use the connection as a context manager for automatic commit/rollback
        with conn:
            c = conn.cursor()
            # Check if user/email already exists
            c.execute("SELECT username FROM USERS WHERE username = ? OR email = ?", (username, email))
            if c.fetchone():
                return False, "Username or Email already exists."
            
            password_hash = hash_password(password)
            default_role = 'customer' 
            # Insert the new user
            c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                      (username, email, password_hash, default_role))
            return True, "Registration successful. You can now log in."
    except sqlite3.IntegrityError:
        return False, "Database error during registration. Ensure username/email is unique."
    except Exception as e:
        # st.error(f"Signup error: {e}") # Debugging aid
        return False, "An unexpected error occurred during registration."
    finally:
        conn.close()

# --- Data Fetching (Caching) ---
@st.cache_data
def get_production_data(cache_refresher): 
    """Fetches production log data."""
    conn = get_db_connection() 
    df = pd.DataFrame() 
    try:
        # Fetch all data, now including production_type and price_usd
        query = """
        SELECT 
            p.*, 
            d.price_usd 
        FROM PRODUCTION_LOG p
        JOIN DESIGNS d ON p.product_name = d.name
        ORDER BY p.log_date
        """
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
             return pd.DataFrame()
             
        df['potential_revenue'] = df['units_produced'] * df['price_usd']
        df['log_date'] = pd.to_datetime(df['log_date'])
        return df
        
    except Exception as e:
        # print(f"Error fetching data: {e}") # Debugging
        return pd.DataFrame()
    finally:
        conn.close() 

@st.cache_data
def get_designs_data(cache_refresher):
    """Fetches design data using a cacheable function."""
    conn = get_db_connection()
    try:
        # Query updated to include retail_status
        df_designs = pd.read_sql_query("SELECT name, description, price_usd, retail_status FROM DESIGNS ORDER BY name", conn)
        return df_designs
    except Exception as e:
        # print(f"Error fetching designs: {e}") # Debugging
        return pd.DataFrame()
    finally:
        conn.close()


# --- Cart Functions (Simulated in Session State) ---
def add_to_cart(design_name, size, quantity, price):
    """Adds an item to the session state cart."""
    if 'cart' not in st.session_state:
        st.session_state['cart'] = []
    
    # Create a unique key for the item (name + size)
    item_key = f"{design_name}-{size}"
    
    # Check if item already exists in the cart
    found = False
    for item in st.session_state['cart']:
        if item['key'] == item_key:
            item['quantity'] += quantity
            found = True
            break
            
    if not found:
        st.session_state['cart'].append({
            'key': item_key,
            'name': design_name,
            'size': size,
            'quantity': quantity,
            'price': price,
            'subtotal': quantity * price
        })
    else:
        # Update subtotal if item was already found
        for item in st.session_state['cart']:
            if item['key'] == item_key:
                item['subtotal'] = item['quantity'] * item['price']
    
    # Force the display to refresh to reflect the new cart item
    st.session_state['page'] = 'view_cart'
    st.rerun()

def clear_cart():
    """Clears all items from the cart."""
    st.session_state['cart'] = []
    st.session_state['page'] = 'view_product_collections'
    st.rerun()
    
# --- App Pages ---

def login_page():
    """Handles user login."""
    st.title("T-Shirt Production Login")
    
    if st.session_state.get('authenticated'):
        st.info("You are already logged in.")
        return

    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Existing User Login")
        with st.form("login_form"):
            username = st.text_input("Username", value="customer1") # Pre-fill for ease of use
            password = st.text_input("Password", type="password", value="customerpass") # Pre-fill for ease of use
            login_submitted = st.form_submit_button("Log In")

            if login_submitted:
                user = authenticate_user(username, password)
                if user:
                    st.session_state['authenticated'] = True
                    st.session_state['username'] = user['username']
                    # The role is fetched from the database
                    st.session_state['role'] = user['role'] 
                    st.session_state['page'] = 'dashboard' # Redirect after successful login
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    
    with col2:
        signup_page()

def signup_page():
    """Handles user sign-up."""
    st.subheader("New User Sign Up")
    with st.form("signup_form"):
        st.markdown("##### Create a New Customer Account")
        new_username = st.text_input("Username", key="su_username")
        new_email = st.text_input("Email", key="su_email", help="Required for notifications and identification.")
        new_password = st.text_input("Password", type="password", key="su_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="su_confirm_password")
        
        signup_submitted = st.form_submit_button("Sign Up")
        
        if signup_submitted:
            if not new_username or not new_email or not new_password or not confirm_password:
                st.error("Please fill in all fields.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif not "@" in new_email:
                st.error("Please enter a valid email address.")
            else:
                success, message = signup_user(new_username, new_email, new_password)
                if success:
                    st.success(message)
                    st.balloons()
                    # Force a login page rerun to clear signup fields after success
                    st.session_state['page'] = 'login'
                    st.rerun()
                else:
                    st.error(message)

# --- Performance and Sales Page (Admin Only) ---
def performance_and_sales_page():
    """Displays production performance graphs and revenue metrics (Admin Only)."""
    if st.session_state.get('role') != 'admin':
        st.error("Access Denied: Only Admins can view performance data.")
        return

    st.title("📈 Production Performance and Sales Tracking")
    st.markdown("---")

    # Use st.session_state.get('db_refresher', 0) to force cache invalidation
    df = get_production_data(st.session_state.get('db_refresher', 0))
    
    if df.empty:
        st.warning("No production data available. Log a production run to see the charts.")
        return
        
    # --- 1. Top Level Metrics (Revenue and Volume) ---
    total_revenue = df['potential_revenue'].sum()
    total_units_produced = df['units_produced'].sum()
    total_defects = df['defects'].sum()
    defect_rate_overall = (total_defects / total_units_produced) * 100 if total_units_produced else 0
    
    st.subheader("Financial and Volume Overview (Last 30 Days)")
    col_rev, col_units, col_def_rate = st.columns(3)
    
    with col_rev:
        st.metric(label="Total Potential Revenue", value=f"${total_revenue:,.2f}")
        
    with col_units:
        st.metric(label="Total Units Produced", value=f"{total_units_produced:,}")
        
    with col_def_rate:
        st.metric(label="Overall Defect Rate", value=f"{defect_rate_overall:.2f}%", 
                  delta=f"{(defect_rate_overall - 3.5):.2f}% vs Target" if defect_rate_overall > 3.5 else None,
                  delta_color="inverse")
        
    st.markdown("---")

    # --- 2. Production Type Breakdown ---
    st.header("Breakdown by Production Type (Mass vs. Retail)")
    
    df_type_summary = df.groupby('production_type').agg(
        total_units=('units_produced', 'sum'),
        total_revenue=('potential_revenue', 'sum'),
        total_defects=('defects', 'sum')
    ).reset_index()

    # Calculate defect rate for each type
    df_type_summary['defect_rate'] = (df_type_summary['total_defects'] / df_type_summary['total_units']) * 100
    df_type_summary.loc[df_type_summary['total_units'] == 0, 'defect_rate'] = 0 
    
    col_mass, col_retail = st.columns(2)

    # Display metrics for Mass
    mass_data = df_type_summary[df_type_summary['production_type'] == 'Mass'].iloc[0] if 'Mass' in df_type_summary['production_type'].values else None
    
    with col_mass:
        st.subheader("Mass Production (Wholesale Channel)")
        if mass_data is not None:
            st.metric("Units Produced", f"{mass_data['total_units']:,}")
            st.metric("Potential Revenue", f"${mass_data['total_revenue']:,.2f}")
            st.metric("Defect Rate", f"{mass_data['defect_rate']:.2f}%", help="Total defects as a percentage of total units produced.")
        else:
            st.info("No Mass production data logged.")

    # Display metrics for Retail
    retail_data = df_type_summary[df_type_summary['production_type'] == 'Retail'].iloc[0] if 'Retail' in df_type_summary['production_type'].values else None
    
    with col_retail:
        st.subheader("Retail Production")
        if retail_data is not None:
            st.metric("Units Produced", f"{retail_data['total_units']:,}")
            st.metric("Potential Revenue", f"${retail_data['total_revenue']:,.2f}")
            st.metric("Defect Rate", f"{retail_data['defect_rate']:.2f}%", help="Total defects as a percentage of total units produced.")
        else:
            st.info("No Retail production data logged.")
            
    st.markdown("---")


    # 3. Prepare Daily Aggregation Data
    df_daily = df.groupby('log_date').agg(
        total_units=('units_produced', 'sum'),
        total_defects=('defects', 'sum'),
        total_revenue=('potential_revenue', 'sum') 
    ).reset_index()
    
    df_daily['defect_rate'] = (df_daily['total_defects'] / df_daily['total_units']) * 100
    df_daily.loc[df_daily['total_units'] == 0, 'defect_rate'] = 0 
    
    # --- Chart 1: Daily Revenue Trend (Bar Chart) ---
    st.subheader("Daily Potential Revenue Trend")
    
    revenue_chart = alt.Chart(df_daily).mark_bar(color='#4c78a8').encode(
        x=alt.X('log_date:T', axis=alt.Axis(title='Date', format='%Y-%m-%d')),
        y=alt.Y('total_revenue:Q', title='Potential Revenue (USD)'),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('total_revenue:Q', title='Revenue', format='$,.2f'),
            alt.Tooltip('total_units:Q', title='Units Produced', format=',.0f'),
        ]
    ).properties(
        title='Daily Revenue from Production Volume (Total)'
    ).interactive()
    st.altair_chart(revenue_chart, use_container_width=True)

    st.markdown("---")
    
    # --- Chart 2: Revenue Trend by Production Type (Line Chart) ---
    st.subheader("Revenue Trend by Production Type")
    df_daily_type = df.groupby(['log_date', 'production_type']).agg(
        daily_revenue=('potential_revenue', 'sum')
    ).reset_index()

    type_revenue_chart = alt.Chart(df_daily_type).mark_line(point=True).encode(
        x=alt.X('log_date:T', title='Date'),
        y=alt.Y('daily_revenue:Q', title='Daily Revenue (USD)'),
        color=alt.Color('production_type:N', title="Channel"),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('production_type:N', title='Channel'),
            alt.Tooltip('daily_revenue:Q', title='Revenue', format='$,.2f')
        ]
    ).properties(
        title='Revenue Split by Mass vs. Retail Over Time'
    ).interactive()
    st.altair_chart(type_revenue_chart, use_container_width=True)
    
    st.markdown("---")

    # Melt data for the layered chart (Production vs Defects)
    df_melted = df_daily.melt(id_vars=['log_date'], 
                             value_vars=['total_units', 'total_defects'], 
                             var_name='Metric', 
                             value_name='Count')

    # --- Chart 3: Daily Units vs. Defects (Layered Column Chart) ---
    st.subheader("Daily Production Volume vs. Daily Defects (Quality Control)")
    
    base = alt.Chart(df_melted).encode(
        x=alt.X('log_date:T', axis=alt.Axis(title='Date', format='%Y-%m-%d')),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('Count:Q', title='Value', format=',.0f'),
            'Metric:N'
        ]
    )

    bars = base.mark_bar().encode(
        y=alt.Y('Count:Q', title='Count'),
        color=alt.Color('Metric:N', 
                        legend=alt.Legend(title="Metric"), 
                        scale=alt.Scale(domain=['total_units', 'total_defects'], range=['#38A169', '#E53E3E'])),
        column=alt.Column('Metric:N', header=alt.Header(titleOrient="bottom", labelOrient="bottom", title="Units Produced / Defects")),
    ).resolve_scale(
        y='independent' 
    ).properties(
        title='Volume vs. Defects' 
    ).interactive()

    st.altair_chart(bars, use_container_width=True)
    
    st.markdown("---")

    # --- Chart 4: Defect Rate Trend (%) (Line Chart) ---
    st.subheader("Defect Rate Trend (%)")

    rate_chart = alt.Chart(df_daily).mark_line(point=True, strokeWidth=3, color='#F06E6E').encode(
        x=alt.X('log_date:T', title='Date'),
        y=alt.Y('defect_rate:Q', title='Defect Rate (%)', scale=alt.Scale(domain=[0, df_daily['defect_rate'].max() * 1.2 or 5])),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('defect_rate:Q', title='Defect Rate', format='.2f'),
            alt.Tooltip('total_units:Q', title='Total Units', format=',.0f'),
            alt.Tooltip('total_defects:Q', title='Total Defects', format=',.0f'),
        ]
    ).properties(
        title='Defect Rate Percentage Over Time (Total)'
    ).interactive() 
    
    st.altair_chart(rate_chart, use_container_width=True)
    
    st.markdown("---")

    # --- Chart 5: Product Contribution to Revenue (Pie Chart) ---
    st.subheader("Revenue Contribution by Design")

    df_product_revenue = df.groupby('product_name').agg(
        total_revenue=('potential_revenue', 'sum')
    ).reset_index().sort_values(by='total_revenue', ascending=False)

    pie_chart = alt.Chart(df_product_revenue).mark_arc(outerRadius=120, innerRadius=50).encode(
        theta=alt.Theta("total_revenue", stack=True),
        color=alt.Color("product_name", title="T-Shirt Design"),
        order=alt.Order("total_revenue", sort="descending"),
        tooltip=[
            "product_name", 
            alt.Tooltip("total_revenue", title="Total Revenue", format="$,.2f"),
            alt.Tooltip("total_revenue", title="Percentage", format=".1%"),
        ]
    ).properties(
        title='Product Revenue Breakdown'
    ).interactive()

    text = alt.Chart(df_product_revenue).mark_text(radius=140).encode(
        theta=alt.Theta("total_revenue", stack=True),
        text=alt.Text("product_name", format="s"),
        order=alt.Order("total_revenue", sort="descending"),
        color=alt.value("black")
    )
    
    st.altair_chart(pie_chart.properties(title="Revenue Split by Design"), use_container_width=True)


def dashboard_page():
    """Main dashboard based on user role."""
    st.title(f"Welcome, {st.session_state['username']}! ({st.session_state['role'].capitalize()})")
    
    if st.session_state['role'] == 'admin':
        st.header("Admin Overview")
        st.info("You have access to production logs and performance tracking. Use the sidebar menu to navigate.")
        # Call the performance page directly for admin dashboard
        performance_and_sales_page() 
        
    elif st.session_state['role'] == 'customer':
        st.header("Customer Portal")
        # Direct customer to the collection view
        view_product_collections() 

def manage_production_page():
    """Allows admins to log new production runs."""
    if st.session_state.get('role') != 'admin':
        st.error("Access Denied: Only Admins can manage production.")
        return
        
    # Use the cached function to get current designs data
    df_designs = get_designs_data(st.session_state.get('db_refresher', 0))
    designs = df_designs['name'].tolist()

    st.title("Log New Production Run")
    
    if not designs:
        st.warning("No designs found. Please add designs first via 'Manage Designs'.")
        return

    with st.form("production_log_form"):
        # Select the Production Type (Mass or Retail)
        prod_type = st.selectbox("Production Channel", ['Mass', 'Retail'], help="Select the sales channel this batch is intended for. Mass for Wholesale, Retail for direct customers.")
        
        prod_date = st.date_input("Date of Production", datetime.now().date())
        prod_name = st.selectbox("Product Design", designs)
        prod_size = st.selectbox("Size", ['XS', 'S', 'M', 'L', 'XL', 'XXL'])
        units_produced = st.number_input("Units Produced (Total)", min_value=1, step=1)
        defects = st.number_input("Defects Recorded", min_value=0, step=1)
        
        submitted = st.form_submit_button("Log Production")

        if submitted:
            if defects > units_produced:
                st.error("Defects cannot exceed total units produced.")
            else:
                conn = get_db_connection()
                try:
                    with conn:
                        c = conn.cursor()
                        # Insert statement updated to include production_type
                        c.execute(
                            "INSERT INTO PRODUCTION_LOG (log_date, product_name, size, units_produced, defects, production_type) VALUES (?, ?, ?, ?, ?, ?)",
                            (prod_date.strftime('%Y-%m-%d'), prod_name, prod_size, units_produced, defects, prod_type)
                        )
                    st.success(f"Production log for {units_produced} units of {prod_name} ({prod_type}) added successfully!")
                    
                    # CRITICAL FIX: Increment a state variable to invalidate the @st.cache_data in get_production_data
                    if 'db_refresher' not in st.session_state:
                         st.session_state['db_refresher'] = 0
                    st.session_state['db_refresher'] += 1
                    
                    st.rerun() 
                    
                except Exception as e:
                    st.error(f"Failed to log production: {e}")
                finally:
                    conn.close()

def manage_designs_page():
    """Allows admins to add and view designs."""
    if st.session_state.get('role') != 'admin':
        st.error("Access Denied: Only Admins can manage designs.")
        return
        
    st.title("Product (Design) Management") 
    
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Add New Product Design") 
        with st.form("add_design_form"):
            name = st.text_input("Design Name (Unique)")
            description = st.area_input("Description (e.g., color, material, quality notes)")
            
            # NEW INPUT: Design channel/status
            retail_status = st.selectbox("Primary Sales Channel", ['Mass', 'Retail'], help="Mass production is high volume (Wholesale), retail is often specialized or premium (Direct Customer).")
            
            price_usd = st.number_input("Unit Price (USD)", min_value=0.01, step=0.01, format="%.2f", value=19.99)
            
            submitted = st.form_submit_button("Add Design")

            if submitted:
                if name:
                    conn = get_db_connection()
                    try:
                        with conn:
                            c = conn.cursor()
                            # Insert statement updated to include retail_status
                            c.execute("INSERT INTO DESIGNS (name, description, price_usd, retail_status) VALUES (?, ?, ?, ?)", (name, description, price_usd, retail_status))
                        
                        # Invalidate the cache for design data after adding a new design
                        st.session_state['db_refresher'] = st.session_state.get('db_refresher', 0) + 1
                        st.success(f"Design '{name}' added successfully! Refreshing data...")
                        st.rerun()
                        
                    except sqlite3.IntegrityError:
                        st.error("A design with this name already exists.")
                    except Exception as e:
                        st.error(f"An error occurred: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("Design Name cannot be empty.")

# --- Product Detail View with Cart Functionality ---
def product_detail_page(design_name):
    """Displays the detail page for a single design and allows adding to cart."""
    df_designs = get_designs_data(st.session_state.get('db_refresher', 0))
    design_data = df_designs[df_designs['name'] == design_name].iloc[0]

    st.title(f"Product Details: {design_name}")
    st.subheader(f"Price: ${design_data['price_usd']:.2f}")

    col_img, col_info = st.columns([1, 2])
    
    with col_img:
        # Placeholder image
        st.image(f"https://placehold.co/400x400/3182CE/ffffff?text={design_name.replace(' ', '+')}", 
                 caption=f"{design_name} Design", use_column_width=True)

    with col_info:
        st.markdown(f"**Description:** {design_data['description']}")
        st.markdown(f"**Channel:** {design_data['retail_status']} (Typically direct customer sale)")
        
        st.markdown("---")
        st.subheader("Add to Cart")
        
        with st.form(f"add_to_cart_form_{design_name}"):
            size = st.selectbox("Select Size", ['S', 'M', 'L', 'XL', 'XXL'], key=f"size_{design_name}")
            quantity = st.number_input("Quantity", min_value=1, value=1, step=1, key=f"qty_{design_name}")
            
            add_submitted = st.form_submit_button("🛒 Add to Cart")
            
            if add_submitted:
                add_to_cart(design_name, size, quantity, design_data['price_usd'])
                st.success(f"{quantity}x {size} {design_name} added to your cart!")
                # No rerun here, add_to_cart handles the redirect to cart page

    st.markdown("---")
    if st.button("← Back to Collections"):
        st.session_state['selected_design'] = None
        st.rerun()

# --- Combined Collections View (Customer Only) ---
def view_product_collections():
    """Displays separate Retail and Wholesale views for the customer."""
    # Check if a design is selected for detail view
    if st.session_state.get('selected_design'):
        product_detail_page(st.session_state['selected_design'])
        return
        
    df_designs = get_designs_data(st.session_state.get('db_refresher', 0))

    if st.session_state.get('role') == 'admin':
        st.subheader("All Product Designs (Admin View)")
        if df_designs.empty:
            st.info("No designs have been added yet.")
            return

        # Admin view shows all data in a table format
        st.dataframe(
            df_designs,
            column_config={
                "name": st.column_config.TextColumn("Design Name"),
                "description": st.column_config.TextColumn("Description"),
                "price_usd": st.column_config.NumberColumn("Unit Price", format="$%.2f"),
                "retail_status": st.column_config.TextColumn("Channel") 
            },
            hide_index=True,
            use_container_width=True
        )
        return

    # --- Customer View (Combined Retail and Wholesale) ---
    st.title("👕 Product Collections")
    
    # Filter data
    df_retail = df_designs[df_designs['retail_status'] == 'Retail'].reset_index(drop=True)
    df_wholesale = df_designs[df_designs['retail_status'] == 'Mass'].reset_index(drop=True)

    # Use tabs to separate the two channels
    tab1, tab2 = st.tabs(["🛍️ Retail Collection", "📦 Wholesale Catalog"])

    with tab1:
        st.subheader("Premium & Exclusive Designs")
        st.markdown("Browse our unique, limited-edition designs. Click **'View Details'** to purchase.")
        
        if df_retail.empty:
            st.info("The Retail Collection is currently empty. Check back soon for new exclusive designs!")
        else:
            # Display designs in a responsive grid format (Retail view)
            cols = st.columns(3)
            
            for index, row in df_retail.iterrows():
                with cols[index % 3]: # Cycle through columns
                    # Card-like layout for each retail item
                    design_name = row['name']
                    # Use unique keys for buttons
                    button_key = f"view_{design_name}" 
                    
                    st.markdown(f"""
                    <div style="border: 2px solid #3182CE; border-radius: 10px; padding: 15px; margin-bottom: 20px; text-align: center; background-color: #EBF8FF; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <h4 style="color: #2B6CB0; margin-top: 0;">{design_name}</h4>
                        <p style="font-size: 1.5em; font-weight: bold; color: #3182CE;">${row['price_usd']:.2f}</p>
                        <p style="font-size: 0.9em; color: #4A5568;">{row['description'].split('.')[0]}.</p>
                    </div>
                    """, unsafe_allow_html=True)
                    # Adding a placeholder image
                    st.image(f"https://placehold.co/400x300/3182CE/ffffff?text={design_name.replace(' ', '+')}", use_column_width=True)

                    # Button to go to the detail page (simulating product click)
                    if st.button("View Details", key=button_key, use_container_width=True):
                         st.session_state['selected_design'] = design_name
                         st.rerun()

    with tab2:
        st.subheader("Bulk Order Catalog")
        st.markdown("For wholesale customers: View our mass-produced items available for bulk purchase.")

        if df_wholesale.empty:
            st.info("The Wholesale Catalog is currently empty.")
        else:
            # Simple table view for wholesale items
            df_display = df_wholesale[['name', 'description', 'price_usd']]
            
            st.dataframe(
                df_display,
                column_config={
                    "name": "Product Name",
                    "description": "Product Description",
                    "price_usd": st.column_config.NumberColumn("Unit Price (Wholesale)", format="$%.2f"),
                },
                hide_index=True,
                use_container_width=True
            )
            
            st.markdown("---")
            st.warning("To place a bulk order, please contact our sales team using the information below.")
            st.markdown("Email: `sales@tshirtco.com` | Phone: `(555) 555-5555`")

def view_cart_page():
    """Displays the simulated shopping cart contents."""
    st.title("🛒 Your Shopping Cart")

    cart = st.session_state.get('cart', [])
    
    if not cart:
        st.info("Your cart is currently empty.")
        if st.button("Continue Shopping", key="cont_shop_empty"):
            st.session_state['page'] = 'view_product_collections'
            st.rerun()
        return

    # Convert cart list of dictionaries to DataFrame for display
    cart_df = pd.DataFrame(cart)
    
    # Calculate total cart value
    total_price = cart_df['subtotal'].sum()
    
    st.subheader(f"Total Items: {len(cart_df)}")
    st.subheader(f"Cart Total: ${total_price:,.2f}")
    st.markdown("---")

    # Display the cart in a user-friendly table
    st.dataframe(
        cart_df[['name', 'size', 'quantity', 'price', 'subtotal']],
        column_config={
            "name": "Product",
            "size": "Size",
            "quantity": st.column_config.NumberColumn("Qty", format="%d"),
            "price": st.column_config.NumberColumn("Unit Price", format="$%.2f"),
            "subtotal": st.column_config.NumberColumn("Subtotal", format="$%.2f")
        },
        hide_index=True,
        use_container_width=True
    )

    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        if st.button("Continue Shopping", key="cont_shop_full", use_container_width=True):
            st.session_state['page'] = 'view_product_collections'
            st.rerun()
    with col_btn2:
        if st.button("Clear Cart", key="clear_cart_btn", type="secondary", use_container_width=True):
            clear_cart()
    with col_btn3:
        # MODIFICATION: Redirect to a dedicated checkout page
        if st.button("Proceed to Checkout", key="checkout_btn", type="primary", use_container_width=True):
            st.session_state['page'] = 'checkout'
            st.rerun()

# --- NEW: Dedicated Checkout Page ---
def checkout_page():
    """Simulated dedicated checkout page."""
    st.title("💳 Checkout")
    
    cart = st.session_state.get('cart', [])
    if not cart:
        st.warning("Your cart is empty. Please add items to proceed to checkout.")
        if st.button("Go to Collections"):
            st.session_state['page'] = 'view_product_collections'
            st.rerun()
        return
        
    cart_df = pd.DataFrame(cart)
    total_price = cart_df['subtotal'].sum()

    st.subheader("Order Summary")
    st.dataframe(
        cart_df[['name', 'size', 'quantity', 'subtotal']],
        column_config={
            "name": "Product",
            "size": "Size",
            "quantity": "Qty",
            "subtotal": st.column_config.NumberColumn("Subtotal", format="$%.2f")
        },
        hide_index=True,
        use_container_width=True
    )
    
    st.markdown("---")
    st.markdown(f"## Final Total: **${total_price:,.2f}**")
    st.markdown("---")

    # --- Shipping and Payment Form Simulation ---
    with st.form("checkout_form"):
        st.subheader("1. Shipping Information")
        st.text_input("Full Name", value=st.session_state['username'].capitalize(), required=True)
        st.text_area("Shipping Address", required=True)
        # Use the customer's email if available, otherwise mock one
        email = next((user['email'] for user in [authenticate_user(st.session_state['username'], 'customerpass')] if user), "default@email.com")
        st.text_input("Email", value=email, required=True)
        
        st.subheader("2. Payment Details (Simulated)")
        st.selectbox("Payment Method", ["Credit Card", "PayPal", "Bank Transfer"], index=0)
        st.text_input("Card Number", placeholder="XXXX XXXX XXXX XXXX")
        col_exp, col_cvv = st.columns(2)
        with col_exp:
            st.text_input("Expiry Date", placeholder="MM/YY")
        with col_cvv:
            st.text_input("CVV", placeholder="XXX", type="password")
            
        st.markdown("---")
        
        # Confirmation button
        submit_order = st.form_submit_button(f"Place Order and Pay ${total_price:,.2f}", type="primary")

        if submit_order:
            # This is the actual final action
            st.success(f"Order successfully placed! Total paid: ${total_price:,.2f}. You will receive a confirmation email shortly.")
            st.balloons()
            # Clear the cart and redirect to a thank you/collections page
            st.session_state['cart'] = []
            st.session_state['page'] = 'view_product_collections'
            st.rerun()
            
    if st.button("← Return to Cart"):
        st.session_state['page'] = 'view_cart'
        st.rerun()


def logout():
    """Logs the user out and clears session state."""
    st.session_state['authenticated'] = False
    if 'username' in st.session_state:
        del st.session_state['username']
    if 'role' in st.session_state:
        del st.session_state['role']
    # Also clear shopping cart on logout
    if 'cart' in st.session_state:
        del st.session_state['cart']
    if 'selected_design' in st.session_state:
        del st.session_state['selected_design']
        
    st.session_state['page'] = 'login'
    st.rerun()

def main_app():
    """The main entry point for the Streamlit application."""
    # Initialize the database and tables if they don't exist
    init_db()

    # Session State Initialization
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        st.session_state['page'] = 'login'
    if 'page' not in st.session_state:
         st.session_state['page'] = 'login'
    if 'db_refresher' not in st.session_state:
        st.session_state['db_refresher'] = 0
    # Initialize state for the shopping cart (empty list)
    if 'cart' not in st.session_state:
        st.session_state['cart'] = []
    # Initialize state for product detail navigation
    if 'selected_design' not in st.session_state:
        st.session_state['selected_design'] = None


    # --- Sidebar Navigation ---
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/4/4c/T-shirt_icon.svg/1200px-T-shirt_icon.svg.png", 
                 width=100)
        st.title("T-Shirt Tracker")
        
        if st.session_state['authenticated']:
            st.markdown(f"**Logged in as:** `{st.session_state['username']}`")
            st.markdown(f"**Role:** _{st.session_state['role'].capitalize()}_")
            st.markdown("---")
            
            # Navigation based on role
            if st.session_state['role'] == 'admin':
                st.header("Admin Menu")
                if st.button("Dashboard (Home)", key="nav_dash"):
                    st.session_state['page'] = 'dashboard'
                    st.session_state['selected_design'] = None # Clear product view state
                if st.button("Log Production", key="nav_prod"):
                    st.session_state['page'] = 'manage_production'
                    st.session_state['selected_design'] = None
                if st.button("Performance & Sales", key="nav_perf"):
                    st.session_state['page'] = 'performance_tracking'
                    st.session_state['selected_design'] = None
                if st.button("Manage Designs", key="nav_design"):
                    st.session_state['page'] = 'manage_designs'
                    st.session_state['selected_design'] = None
            
            elif st.session_state['role'] == 'customer':
                st.header("Customer Menu")
                if st.button("Dashboard (Home)", key="nav_dash_cust"):
                    st.session_state['page'] = 'dashboard'
                    st.session_state['selected_design'] = None
                if st.button("View Collections", key="nav_view_design"):
                    st.session_state['page'] = 'view_product_collections'
                    st.session_state['selected_design'] = None
                
                # Cart button for customers
                cart_count = sum(item['quantity'] for item in st.session_state.get('cart', []))
                cart_label = f"🛒 View Cart ({cart_count})"
                if st.button(cart_label, key="nav_view_cart", type="primary"):
                    st.session_state['page'] = 'view_cart'
                    st.session_state['selected_design'] = None

            st.markdown("---")
            if st.button("Logout", type="secondary"):
                logout()
        else:
            st.info("Please log in or sign up. Use **customer1**/**customerpass** to view the product collections.")

    # --- Page Router ---
    if st.session_state['page'] == 'login' or not st.session_state['authenticated']:
        login_page()
    elif st.session_state['page'] == 'dashboard':
        dashboard_page()
    elif st.session_state['page'] == 'manage_production':
        manage_production_page()
    elif st.session_state['page'] == 'performance_tracking':
        performance_and_sales_page() 
    elif st.session_state['page'] == 'manage_designs':
        manage_designs_page()
    elif st.session_state['page'] == 'view_product_collections':
        view_product_collections()
    elif st.session_state['page'] == 'view_cart':
        view_cart_page()
    # NEW ROUTE: Dedicated Checkout Page
    elif st.session_state['page'] == 'checkout':
        checkout_page()

if __name__ == '__main__':
    main_app()
