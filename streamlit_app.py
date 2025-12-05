import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

# --- Configuration ---
st.set_page_config(layout="wide", page_title="T-Shirt Production Tracker", page_icon="👕")

# --- Database Connection and Setup ---

# Use st.cache_resource for persistent, safe connection across reruns.
# This ensures the connection object is shared across all sessions.
@st.cache_resource
def get_db_connection():
    """Returns a cached, thread-safe SQLite database connection."""
    # Use check_same_thread=False for Streamlit environment to avoid threading issues
    conn = sqlite3.connect('tshirt_app.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    return conn

def hash_password(password):
    """Hashes the password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Initializes database tables and populates initial data."""
    conn = get_db_connection()
    c = conn.cursor()

    # Define all necessary tables (DDL)
    c.executescript('''
        CREATE TABLE IF NOT EXISTS USERS (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE, 
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS DESIGNS (
            design_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            price_usd REAL NOT NULL DEFAULT 19.99
        );

        CREATE TABLE IF NOT EXISTS PRODUCTION_LOG (
            log_id INTEGER PRIMARY KEY,
            log_date TEXT NOT NULL,
            product_name TEXT NOT NULL,
            size TEXT NOT NULL,
            units_produced INTEGER NOT NULL,
            defects INTEGER NOT NULL
        );
    ''')

    # Add initial data if tables are empty (DML)
    try:
        # Use 'with conn:' context manager for proper transaction boundaries (COMMIT/ROLLBACK)
        with conn:
            # Add initial users
            if not c.execute("SELECT 1 FROM USERS").fetchone():
                c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                          ('admin', 'admin@company.com', hash_password('adminpass'), 'admin'))
                c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                          ('customer1', 'cust1@email.com', hash_password('customerpass'), 'customer'))

            # Add initial designs
            if not c.execute("SELECT 1 FROM DESIGNS").fetchone():
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Logo Tee', 'Standard company logo print', 24.99))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Abstract Art', 'Limited edition vibrant print', 35.50))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Vintage Stripes', 'Classic striped design', 19.99))

            # Add significantly more mock production logs (10 days of data)
            if not c.execute("SELECT 1 FROM PRODUCTION_LOG").fetchone():
                today = datetime.now().date()
                data = []
                
                # Generate data for the last 10 days
                for i in range(1, 11):
                    log_date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                    
                    # Design 1: Logo Tee (High volume, low defect rate)
                    data.append((log_date, 'Logo Tee', 'M', 100 + i*10, 5 + (i//3)))
                    data.append((log_date, 'Logo Tee', 'L', 120 + i*5, 4 + (i//4)))

                    # Design 2: Abstract Art (Medium volume, medium defect rate)
                    data.append((log_date, 'Abstract Art', 'S', 50 + i*3, 2 + (i//2)))
                    data.append((log_date, 'Abstract Art', 'XL', 70 + i*2, 3 + (i//2)))
                    
                    # Design 3: Vintage Stripes (Low volume, high defect rate simulation)
                    data.append((log_date, 'Vintage Stripes', 'M', 30 + i*2, 1 + i))
                    
                # Add a few logs for today
                data.append((today.strftime('%Y-%m-%d'), 'Logo Tee', 'M', 150, 6))
                data.append((today.strftime('%Y-%m-%d'), 'Abstract Art', 'L', 80, 4))
                
                c.executemany("INSERT INTO PRODUCTION_LOG (log_date, product_name, size, units_produced, defects) VALUES (?, ?, ?, ?, ?)", data)
            
    except sqlite3.IntegrityError:
        pass # Data already present
    except Exception as e:
        st.error(f"Error initializing data: {e}")


# --- Authentication Functions ---

def authenticate_user(username, password):
    """Checks credentials and returns the user row or None."""
    conn = get_db_connection()
    c = conn.cursor()
    
    password_hash = hash_password(password)
    c.execute("SELECT * FROM USERS WHERE username = ? AND password_hash = ?", (username, password_hash))
    user = c.fetchone()
    return user

def signup_user(username, email, password): # Removed 'role' argument
    """Registers a new user, always assigning the 'customer' role."""
    conn = get_db_connection()
    
    # Check if username or email already exists and insert using transaction context manager
    try:
        with conn:
            c = conn.cursor()
            if c.execute("SELECT username FROM USERS WHERE username = ? OR email = ?", (username, email)).fetchone():
                return False, "Username or Email already exists."
            
            password_hash = hash_password(password)
            # HARDCODE ROLE: Assign 'customer' role to all new sign-ups
            default_role = 'customer' 
            c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                      (username, email, password_hash, default_role))
            return True, "Registration successful. You can now log in."
    except sqlite3.IntegrityError:
        return False, "Database error during registration."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"

# --- Data Fetching (Caching added to force refresh after DB change) ---
# Use st.cache_data to store the returned DataFrame. The cache will be cleared when 
# the 'Production Log Added' message is shown, triggering a chart update.
@st.cache_data
def get_production_data(conn, cache_refresher): # Added placeholder argument for manual cache clearing
    """Fetches production log data along with current product price for revenue calculation."""
    try:
        # Fetch all data from the PRODUCTION_LOG table, joining with DESIGNS to get current price
        query = """
        SELECT 
            p.*, 
            d.price_usd 
        FROM PRODUCTION_LOG p
        JOIN DESIGNS d ON p.product_name = d.name
        ORDER BY p.log_date
        """
        df = pd.read_sql_query(query, conn)
        # Calculate potential revenue for each log entry
        df['potential_revenue'] = df['units_produced'] * df['price_usd']
        df['log_date'] = pd.to_datetime(df['log_date'])
        return df
    except pd.io.sql.DatabaseError:
        st.error("Could not fetch production data.")
        return pd.DataFrame()


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
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            login_submitted = st.form_submit_button("Log In")

            if login_submitted:
                user = authenticate_user(username, password)
                if user:
                    st.session_state['authenticated'] = True
                    st.session_state['username'] = user['username']
                    st.session_state['role'] = user['role']
                    st.session_state['page'] = 'dashboard' # Redirect after successful login
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    
    with col2:
        signup_page()

def signup_page():
    """Handles user sign-up. Role selection removed."""
    st.subheader("New User Sign Up")
    with st.form("signup_form"):
        st.markdown("##### Create a New Customer Account")
        new_username = st.text_input("Username", key="su_username")
        # Email field
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
                else:
                    st.error(message)


def performance_and_sales_page():
    """Displays improved production performance graphs and revenue metrics."""
    conn = get_db_connection()
    st.title("📈 Performance and Sales Tracking")

    # Use st.session_state.get('db_refresher', 0) to force cache invalidation
    # when new data is successfully logged.
    df = get_production_data(conn, st.session_state.get('db_refresher', 0))
    if df.empty:
        st.info("No production data available yet. Please log some production runs to see the graphs.")
        return
        
    # --- 1. Top Level Metrics (Revenue and Volume) ---
    total_revenue = df['potential_revenue'].sum()
    total_units_produced = df['units_produced'].sum()
    total_defects = df['defects'].sum()
    defect_rate_overall = (total_defects / total_units_produced) * 100 if total_units_produced else 0
    
    st.subheader("Financial and Volume Overview")
    col_rev, col_units, col_def_rate = st.columns(3)
    
    with col_rev:
        st.metric(label="Total Potential Revenue", value=f"${total_revenue:,.2f}")
        
    with col_units:
        st.metric(label="Total Units Produced", value=f"{total_units_produced:,}")
        
    with col_def_rate:
        st.metric(label="Overall Defect Rate", value=f"{defect_rate_overall:.2f}%")
        
    st.markdown("---")

    # 2. Prepare Daily Aggregation Data
    df_daily = df.groupby('log_date').agg(
        total_units=('units_produced', 'sum'),
        total_defects=('defects', 'sum'),
        total_revenue=('potential_revenue', 'sum') 
    ).reset_index()
    
    # Calculate defect rate for the trend chart
    df_daily['defect_rate'] = (df_daily['total_defects'] / df_daily['total_units']) * 100
    df_daily.loc[df_daily['total_units'] == 0, 'defect_rate'] = 0 
    
    # --- Chart 1: Daily Revenue Trend (Bar Chart) ---
    st.subheader("Daily Potential Revenue")
    
    revenue_chart = alt.Chart(df_daily).mark_bar().encode(
        x=alt.X('log_date:T', axis=alt.Axis(title='Date', format='%Y-%m-%d')),
        y=alt.Y('total_revenue:Q', title='Potential Revenue (USD)'),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('total_revenue:Q', title='Revenue', format='$,.2f'),
            alt.Tooltip('total_units:Q', title='Units Produced', format=',.0f'),
        ]
    ).properties(
        title='Daily Revenue from Production Volume'
    )
    st.altair_chart(revenue_chart, use_container_width=True)

    st.markdown("---")
    
    # Melt data for the layered chart (Production vs Defects)
    df_melted = df_daily.melt(id_vars=['log_date'], 
                             value_vars=['total_units', 'total_defects'], 
                             var_name='Metric', 
                             value_name='Count')

    # --- Chart 2: Daily Units vs. Defects (Layered Column Chart) ---
    # UPDATED SUBHEADER AND TITLE FOR CLARITY
    st.subheader("Daily Production Volume vs. Daily Defects (Quality Control)")
    
    # Base chart setup
    base = alt.Chart(df_melted).encode(
        x=alt.X('log_date:T', axis=alt.Axis(title='Date', format='%Y-%m-%d')),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('Count:Q', title='Value', format=',.0f'),
            'Metric:N'
        ]
    )

    # Use column separation for distinct charts with independent scales
    bars = base.mark_bar().encode(
        y=alt.Y('Count:Q', title='Count'),
        color=alt.Color('Metric:N', legend=alt.Legend(title="Metric")),
        column=alt.Column('Metric:N', header=alt.Header(titleOrient="bottom", labelOrient="bottom")),
    ).resolve_scale(
        y='independent' # Key: Ensures 'Units Produced' and 'Defects' have separate Y-axes
    ).properties(
        title='Daily Production Volume (Units) vs. Defects Recorded' # Final Updated Title
    )

    st.altair_chart(bars, use_container_width=True)
    
    st.markdown("---")

    # --- Chart 3: Defect Rate Trend (%) (Line Chart) ---
    st.subheader("Defect Rate Trend (%)")

    rate_chart = alt.Chart(df_daily).mark_line(point=True, strokeWidth=3, color='#F06E6E').encode(
        x=alt.X('log_date:T', title='Date'),
        # Set a clear, fixed domain for a better visual comparison
        y=alt.Y('defect_rate:Q', title='Defect Rate (%)', scale=alt.Scale(domain=[0, df_daily['defect_rate'].max() * 1.2 or 5])),
        tooltip=[
            alt.Tooltip('log_date:T', title='Date'),
            alt.Tooltip('defect_rate:Q', title='Defect Rate', format='.2f'),
            alt.Tooltip('total_units:Q', title='Total Units', format=',.0f'),
            alt.Tooltip('total_defects:Q', title='Total Defects', format=',.0f'),
        ]
    ).properties(
        title='Defect Rate Percentage Over Time'
    ).interactive() # Allow zoom and pan
    
    st.altair_chart(rate_chart, use_container_width=True)

def dashboard_page():
    """Main dashboard based on user role."""
    st.title(f"Welcome, {st.session_state['username']}! ({st.session_state['role'].capitalize()})")
    
    if st.session_state['role'] == 'admin':
        st.header("Admin Overview")
        st.info("Use the sidebar navigation to manage products, log production, or view performance.")
        performance_and_sales_page() # Admins see the performance tracking by default
        
    elif st.session_state['role'] == 'customer':
        st.header("Customer Portal")
        st.write("View our latest designs and place an order request.")
        view_designs_page()

def manage_production_page():
    """Allows admins to log new production runs."""
    if st.session_state.get('role') != 'admin':
        st.error("Access Denied: Only Admins can manage production.")
        return

    conn = get_db_connection()
    st.title("Log New Production Run")
    
    designs = pd.read_sql_query("SELECT name FROM DESIGNS", conn)['name'].tolist()
    if not designs:
        st.warning("No designs found. Please add designs first.")
        return

    with st.form("production_log_form"):
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
                try:
                    with conn:
                        c = conn.cursor()
                        c.execute(
                            "INSERT INTO PRODUCTION_LOG (log_date, product_name, size, units_produced, defects) VALUES (?, ?, ?, ?, ?)",
                            (prod_date.strftime('%Y-%m-%d'), prod_name, prod_size, units_produced, defects)
                        )
                    st.success(f"Production log for {units_produced} units of {prod_name} added successfully!")
                    
                    # CRITICAL FIX: Increment a state variable to invalidate the @st.cache_data in get_production_data
                    if 'db_refresher' not in st.session_state:
                         st.session_state['db_refresher'] = 0
                    st.session_state['db_refresher'] += 1
                    
                    st.rerun() # Rerun the script to ensure the chart page updates
                    
                except Exception as e:
                    st.error(f"Failed to log production: {e}")

def manage_designs_page():
    """Allows admins to add and view designs."""
    if st.session_state.get('role') != 'admin':
        st.error("Access Denied: Only Admins can manage designs.")
        return

    conn = get_db_connection()
    st.title("Product (Design) Management") 
    
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Add New Product Design") 
        with st.form("add_design_form"):
            name = st.text_input("Design Name (Unique)")
            description = st.text_area("Description (e.g., color, material)")
            
            price_usd = st.number_input("Unit Price (USD)", min_value=0.01, step=0.01, format="%.2f", value=19.99)
            
            submitted = st.form_submit_button("Add Design")

            if submitted:
                if name:
                    try:
                        with conn:
                            c = conn.cursor()
                            c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", (name, description, price_usd))
                        st.success(f"Design '{name}' added successfully!")
                    except sqlite3.IntegrityError:
                        st.error("A design with this name already exists.")
                    except Exception as e:
                        st.error(f"An error occurred: {e}")
                else:
                    st.error("Design Name cannot be empty.")

    with col2:
        view_designs_page()

def view_designs_page():
    """Displays all available designs."""
    conn = get_db_connection()
    st.subheader("Current T-Shirt Designs")
    
    df_designs = pd.read_sql_query("SELECT name, description, price_usd FROM DESIGNS ORDER BY name", conn)

    if df_designs.empty:
        st.info("No designs have been added yet.")
    else:
        st.dataframe(
            df_designs,
            column_config={
                "name": st.column_config.TextColumn("Design Name", help="The unique name of the T-Shirt design"),
                "description": st.column_config.TextColumn("Description", help="Details about the design and print style"),
                "price_usd": st.column_config.NumberColumn("Unit Price", help="Selling price per unit", format="%.2f", default=19.99)
            },
            hide_index=True,
            use_container_width=True
        )


def logout():
    """Logs the user out and clears session state."""
    st.session_state['authenticated'] = False
    del st.session_state['username']
    del st.session_state['role']
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
                if st.button("Dashboard", key="nav_dash"):
                    st.session_state['page'] = 'dashboard'
                if st.button("Log Production", key="nav_prod"):
                    st.session_state['page'] = 'manage_production'
                if st.button("Performance & Sales", key="nav_perf"):
                    st.session_state['page'] = 'performance_tracking'
                if st.button("Manage Designs", key="nav_design"):
                    st.session_state['page'] = 'manage_designs'
            
            elif st.session_state['role'] == 'customer':
                st.header("Customer Menu")
                if st.button("Dashboard", key="nav_dash_cust"):
                    st.session_state['page'] = 'dashboard'
                if st.button("View Designs", key="nav_view_design"):
                    st.session_state['page'] = 'view_designs'

            st.markdown("---")
            if st.button("Logout", type="secondary"):
                logout()
        else:
            st.info("Please log in or sign up.")

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
    elif st.session_state['page'] == 'view_designs':
        view_designs_page()

if __name__ == '__main__':
    main_app()
