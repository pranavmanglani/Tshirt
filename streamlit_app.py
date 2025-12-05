import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import threading

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
    
    CRITICAL CHANGE: USERS table is now created non-destructively to prevent losing signed-up users.
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
            
            # Reinitialize if the crucial 'production_type' column is missing or tables are missing
            needs_init = ('production_type' not in prod_columns) or (not prod_columns) 

            # Only perform the destructive drop/recreate if initialization is needed
            if needs_init:
                # Drop and recreate production tables
                st.info("Re-initializing production tables to add 'Mass'/'Retail' tracking.")
                c.executescript('''
                    DROP TABLE IF EXISTS DESIGNS;
                    DROP TABLE IF EXISTS PRODUCTION_LOG;

                    CREATE TABLE DESIGNS (
                        design_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        price_usd REAL NOT NULL DEFAULT 19.99
                    );

                    CREATE TABLE PRODUCTION_LOG (
                        log_id INTEGER PRIMARY KEY,
                        log_date TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        size TEXT NOT NULL,
                        units_produced INTEGER NOT NULL,
                        defects INTEGER NOT NULL,
                        production_type TEXT NOT NULL -- NEW COLUMN
                    );
                ''')
                
                # Populate Designs
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Logo Tee', 'Standard company logo print', 24.99))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Abstract Art', 'Limited edition vibrant print', 35.50))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Vintage Stripes', 'Classic striped design', 19.99))
                c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", ('Holiday Special', 'Seasonal festive design', 29.00))


                # Production Logs (Sample data for the last 30 days)
                today = datetime.now().date()
                data = []
                
                # Split sample data between Mass and Retail
                production_types = ['Mass', 'Retail']
                
                for i in range(1, 31):
                    log_date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                    
                    # Mass production tends to be higher volume
                    data.append((log_date, 'Logo Tee', 'M', 100 + i*2, 5 + (i//5), production_types[0]))
                    data.append((log_date, 'Abstract Art', 'S', 50 + i*3, 2 + (i//3), production_types[0]))
                    
                    # Retail production for higher-priced items
                    data.append((log_date, 'Vintage Stripes', 'L', 30 + i, 1 + (i//5), production_types[1]))
                    if i <= 15:
                        data.append((log_date, 'Holiday Special', 'XL', 20 + i*2, 1 + (i//8), production_types[1]))
                    
                # Add a few logs for today
                today_str = today.strftime('%Y-%m-%d')
                data.append((today_str, 'Logo Tee', 'M', 150, 6, 'Mass'))
                data.append((today_str, 'Abstract Art', 'L', 80, 4, 'Retail'))
                
                # Use a specific list of columns for the insert
                insert_cols = "(log_date, product_name, size, units_produced, defects, production_type)"
                insert_placeholder = "(?, ?, ?, ?, ?, ?)"
                c.executemany(f"INSERT INTO PRODUCTION_LOG {insert_cols} VALUES {insert_placeholder}", data)
            
            conn.commit()
        except Exception as e:
            # st.error(f"Error initializing database: {e}") # Suppressing the error message for cleaner UI
            pass # Allows the app to try again on the next rerun
        finally:
            conn.close() # Ensure the connection is closed after initialization


# --- Authentication Functions ---

def authenticate_user(username, password):
    """Checks credentials and returns the user row or None."""
    conn = get_db_connection()
    c = conn.cursor()
    
    password_hash = hash_password(password)
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
# CRITICAL FIX 3: Add a dummy argument to force cache clearing
@st.cache_data
def get_production_data(cache_refresher): 
    """
    Fetches production log data. 
    The 'cache_refresher' argument is only used to force a cache clear on data updates.
    """
    conn = get_db_connection() # Get a fresh connection object for the query
    df = pd.DataFrame() # Initialize empty DataFrame
    try:
        # Fetch all data, now including production_type
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
             st.warning("No production data available. Log a production run to see the charts.")
             return pd.DataFrame()
             
        # Calculate potential revenue for each log entry
        df['potential_revenue'] = df['units_produced'] * df['price_usd']
        df['log_date'] = pd.to_datetime(df['log_date'])
        return df
        
    except pd.io.sql.DatabaseError as e:
        # st.error(f"Database Read Error: Could not fetch production data. {e}")
        return pd.DataFrame()
    except Exception as e:
        # st.error(f"An unexpected error occurred during data fetching: {e}")
        return pd.DataFrame()
    finally:
        conn.close() # Close the connection after reading

@st.cache_data
def get_designs_data(cache_refresher):
    """Fetches design data using a cacheable function."""
    conn = get_db_connection()
    try:
        df_designs = pd.read_sql_query("SELECT name, description, price_usd FROM DESIGNS ORDER BY name", conn)
        return df_designs
    except pd.io.sql.DatabaseError as e:
        # st.error(f"Database Read Error: Could not fetch designs data. {e}")
        return pd.DataFrame()
    finally:
        conn.close()


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
            username = st.text_input("Username", value="admin") # Pre-fill for ease of use
            password = st.text_input("Password", type="password", value="adminpass") # Pre-fill for ease of use
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


def performance_and_sales_page():
    """Displays improved production performance graphs and revenue metrics."""
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
        st.subheader("Mass Production")
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
        performance_and_sales_page() 
        
    elif st.session_state['role'] == 'customer':
        st.header("Customer Portal")
        st.info("Explore our exclusive T-shirt designs.")
        view_designs_page()

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
        # NEW INPUT FIELD
        prod_type = st.selectbox("Production Type", ['Mass', 'Retail'], help="Select the sales channel for this batch.")
        
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
            description = st.text_area("Description (e.g., color, material)")
            
            price_usd = st.number_input("Unit Price (USD)", min_value=0.01, step=0.01, format="%.2f", value=19.99)
            
            submitted = st.form_submit_button("Add Design")

            if submitted:
                if name:
                    conn = get_db_connection()
                    try:
                        with conn:
                            c = conn.cursor()
                            c.execute("INSERT INTO DESIGNS (name, description, price_usd) VALUES (?, ?, ?)", (name, description, price_usd))
                        
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

def view_designs_page():
    """Displays all available designs."""
    st.subheader("Current T-Shirt Designs")
    
    # Use the cached function to fetch design data
    df_designs = get_designs_data(st.session_state.get('db_refresher', 0))

    if df_designs.empty:
        st.info("No designs have been added yet.")
    else:
        st.dataframe(
            df_designs,
            column_config={
                "name": st.column_config.TextColumn("Design Name", help="The unique name of the T-Shirt design"),
                "description": st.column_config.TextColumn("Description", help="Details about the design and print style"),
                "price_usd": st.column_config.NumberColumn("Unit Price", help="Selling price per unit", format="$%.2f")
            },
            hide_index=True,
            use_container_width=True
        )


def logout():
    """Logs the user out and clears session state."""
    st.session_state['authenticated'] = False
    # Clear specific user session keys but keep app configuration keys
    if 'username' in st.session_state:
        del st.session_state['username']
    if 'role' in st.session_state:
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
    # Initialize db_refresher for cache invalidation
    if 'db_refresher' not in st.session_state:
        st.session_state['db_refresher'] = 0

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
                if st.button("Log Production", key="nav_prod"):
                    st.session_state['page'] = 'manage_production'
                if st.button("Performance & Sales", key="nav_perf"):
                    st.session_state['page'] = 'performance_tracking'
                if st.button("Manage Designs", key="nav_design"):
                    st.session_state['page'] = 'manage_designs'
            
            elif st.session_state['role'] == 'customer':
                st.header("Customer Menu")
                if st.button("Dashboard (Home)", key="nav_dash_cust"):
                    st.session_state['page'] = 'dashboard'
                if st.button("View Designs", key="nav_view_design"):
                    st.session_state['page'] = 'view_designs'

            st.markdown("---")
            if st.button("Logout", type="secondary"):
                logout()
        else:
            st.info("Please log in or sign up. Use **admin**/**adminpass** to view the charts.")

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
