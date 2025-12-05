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
    # DDL is executed outside the DML transaction block
    c.executescript('''
        -- UPDATED: Added EMAIL column for sign-up
        CREATE TABLE IF NOT EXISTS USERS (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE, 
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS DESIGNS (
            design_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT
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
        # Use 'with conn:' context manager to ensure proper transaction boundaries (COMMIT/ROLLBACK)
        # This resolves the "cannot start a transaction within a transaction" error.
        with conn:
            # Add initial users (with new EMAIL column)
            if not c.execute("SELECT 1 FROM USERS").fetchone():
                c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                          ('admin', 'admin@company.com', hash_password('adminpass'), 'admin'))
                c.execute("INSERT INTO USERS (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                          ('customer1', 'cust1@email.com', hash_password('customerpass'), 'customer'))

            # Add initial designs
            if not c.execute("SELECT 1 FROM DESIGNS").fetchone():
                c.execute("INSERT INTO DESIGNS (name, description) VALUES (?, ?)", ('Logo Tee', 'Standard company logo print'))
                c.execute("INSERT INTO DESIGNS (name, description) VALUES (?, ?)", ('Abstract Art', 'Limited edition vibrant print'))
                c.execute("INSERT INTO DESIGNS (name, description) VALUES (?, ?)", ('Vintage Stripes', 'Classic striped design'))

            # Add mock production logs for chart demonstration
            if not c.execute("SELECT 1 FROM PRODUCTION_LOG").fetchone():
                today = datetime.now().date()
                data = [
                    ((today - timedelta(days=7)).strftime('%Y-%m-%d'), 'Logo Tee', 'M', 100, 5),
                    ((today - timedelta(days=6)).strftime('%Y-%m-%d'), 'Logo Tee', 'L', 120, 4),
                    ((today - timedelta(days=6)).strftime('%Y-%m-%d'), 'Abstract Art', 'S', 50, 1),
                    ((today - timedelta(days=5)).strftime('%Y-%m-%d'), 'Vintage Stripes', 'XL', 80, 2),
                    ((today - timedelta(days=4)).strftime('%Y-%m-%d'), 'Logo Tee', 'M', 150, 6),
                    ((today - timedelta(days=3)).strftime('%Y-%m-%d'), 'Abstract Art', 'L', 70, 3),
                    ((today - timedelta(days=2)).strftime('%Y-%m-%d'), 'Logo Tee', 'M', 90, 4),
                    ((today - timedelta(days=1)).strftime('%Y-%m-%d'), 'Vintage Stripes', 'M', 110, 3),
                    (today.strftime('%Y-%m-%d'), 'Logo Tee', 'S', 130, 5),
                ]
                c.executemany("INSERT INTO PRODUCTION_LOG (log_date, product_name, size, units_produced, defects) VALUES (?, ?, ?, ?, ?)", data)
            
        # conn.commit() is implicitly called by 'with conn:' on success
    except sqlite3.IntegrityError:
        # This handles cases where initial data might already be present
        pass
    except Exception as e:
        # Catch any other initialization errors
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
            # conn.commit() is implicitly called by 'with conn:'
            return True, "Registration successful. You can now log in."
    except sqlite3.IntegrityError:
        return False, "Database error during registration."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"


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
        
        # REMOVED: new_role = st.selectbox("Role", ["customer", "admin"], key="su_role")
        
        signup_submitted = st.form_submit_button("Sign Up")
        
        if signup_submitted:
            if not new_username or not new_email or not new_password or not confirm_password:
                st.error("Please fill in all fields.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif not "@" in new_email:
                st.error("Please enter a valid email address.")
            else:
                # Call signup_user without the role argument
                success, message = signup_user(new_username, new_email, new_password)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)


def get_production_data(conn):
    """Fetches all production log data for charting."""
    try:
        # Fetch all data from the PRODUCTION_LOG table
        df = pd.read_sql_query("SELECT * FROM PRODUCTION_LOG ORDER BY log_date", conn)
        df['log_date'] = pd.to_datetime(df['log_date'])
        return df
    except pd.io.sql.DatabaseError:
        # Return empty DataFrame if table is missing or query fails
        st.error("Could not fetch production data.")
        return pd.DataFrame()


def performance_tracking_page():
    """Displays improved production performance graphs."""
    conn = get_db_connection()
    st.title("📈 Production Performance Tracking")

    df = get_production_data(conn)
    if df.empty:
        st.info("No production data available yet. Please log some production runs to see the graphs.")
        return

    # 1. Prepare Daily Aggregation Data
    df_daily = df.groupby('log_date').agg(
        total_units=('units_produced', 'sum'),
        total_defects=('defects', 'sum')
    ).reset_index()
    
    # Calculate defect rate for the trend chart
    df_daily['defect_rate'] = (df_daily['total_defects'] / df_daily['total_units']) * 100
    # Handle division by zero for days with no production
    df_daily.loc[df_daily['total_units'] == 0, 'defect_rate'] = 0 
    
    # Melt data for the layered chart (Production vs Defects)
    df_melted = df_daily.melt(id_vars=['log_date'], 
                             value_vars=['total_units', 'total_defects'], 
                             var_name='Metric', 
                             value_name='Count')

    # --- Chart 1: Daily Production and Defects (Layered Column Chart) ---
    st.subheader("Daily Production Volume and Defects")
    
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
        title='Daily Units Produced vs. Defects Recorded'
    )

    st.altair_chart(bars, use_container_width=True)
    
    st.markdown("---")

    # --- Chart 2: Defect Rate Trend (%) (Line Chart) ---
    st.subheader("Defect Rate Trend (%)")
    
    # Find the latest defect rate
    latest_rate = df_daily['defect_rate'].iloc[-1]
    
    col_rate, col_gap = st.columns([1, 4])
    with col_rate:
        st.metric(label="Latest Defect Rate", value=f"{latest_rate:.2f}%")

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
        performance_tracking_page() # Admins see the performance tracking by default
        
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
                        # conn.commit() is implicitly called by 'with conn:'
                    st.success(f"Production log for {units_produced} units of {prod_name} added successfully!")
                except Exception as e:
                    st.error(f"Failed to log production: {e}")

def manage_designs_page():
    """Allows admins to add and view designs."""
    if st.session_state.get('role') != 'admin':
        st.error("Access Denied: Only Admins can manage designs.")
        return

    conn = get_db_connection()
    st.title("Design Management")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Add New Design")
        with st.form("add_design_form"):
            name = st.text_input("Design Name (Unique)")
            description = st.text_area("Description")
            submitted = st.form_submit_button("Add Design")

            if submitted:
                if name:
                    try:
                        with conn:
                            c = conn.cursor()
                            c.execute("INSERT INTO DESIGNS (name, description) VALUES (?, ?)", (name, description))
                            # conn.commit() is implicitly called by 'with conn:'
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
    
    df_designs = pd.read_sql_query("SELECT name, description FROM DESIGNS ORDER BY name", conn)

    if df_designs.empty:
        st.info("No designs have been added yet.")
    else:
        st.dataframe(
            df_designs,
            column_config={
                "name": st.column_config.TextColumn("Design Name", help="The unique name of the T-Shirt design"),
                "description": st.column_config.TextColumn("Description", help="Details about the design and print style")
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
                if st.button("Performance Tracking", key="nav_perf"):
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
        performance_tracking_page()
    elif st.session_state['page'] == 'manage_designs':
        manage_designs_page()
    elif st.session_state['page'] == 'view_designs':
        view_designs_page()

if __name__ == '__main__':
    main_app()
