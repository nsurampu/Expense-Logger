from datetime import datetime
import json
import pandas as pd
from pandas.core.arrays.arrow.array import date
import plotly.express as px
import streamlit as st
import sqlalchemy

from db import DB


# --- App Configuration ---
st.set_page_config(
    page_title="Wealth Detective - Net Worth & FIRE Dashboard",
    page_icon="💰",
    layout="wide"
)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    entered_password = st.text_input("Enter password", type='password')
    if st.button("Unlock"):
        if entered_password == st.secrets['app']['password']:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

@st.cache_resource
def get_db_obj():
    return DB(st.secrets['supabase']['url'])

db_obj = get_db_obj()

@st.cache_data
def load_data():
    try:
        transactions = db_obj.fetch_transaction_records()
        transactions['timestamp'] = pd.to_datetime(transactions['timestamp'])
        transactions['Year'] = transactions['timestamp'].dt.year
        transactions['Month'] = transactions['timestamp'].dt.month
        transactions['Month-Year'] = transactions['timestamp'].dt.strftime('%m-%Y')
    except Exception as e:
        print(e)
        # Fallback dummy structure if DB isn't connected yet
        transactions = pd.DataFrame(columns=['timestamp', 'type', 'category', 'amount', 'note', 'Year', 'Month', 'Month-Year'])

    try:
        investments = db_obj.fetch_investment_records()
    except Exception:
        investments = pd.DataFrame(columns=['type', 'name', 'principal', 'current'])

    investments['principal'] = investments['principal'].fillna(0)
    investments['current'] = investments['current'].fillna(investments['principal'])

    return transactions, investments

transactions, investments = load_data()

# --- Sidebar Controls & Navigation ---
st.sidebar.title("💰 Wealth Detective - Net Worth & FIRE Dashboard")
tab_selection = st.sidebar.radio("Navigation", ["Savings & Expense Summary", "Investments & FIRE", "Goal Modeling", "Expense Logging"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Global Simulation Sliders")
swr_slider = st.sidebar.slider("Safe Withdrawal Rate (%)", 3.0, 6.0, 4.0, 0.2)
inflation_slider = st.sidebar.slider("Assumed YoY Inflation (%)", 3.0, 20.0, 6.0, 0.5)
cagr_slider = st.sidebar.slider("Annualized CAGR (%)", -50.0, 50.0, 11.0, 1.0)
years_slider = st.sidebar.slider("Years to Horizon", 0, 50, 30, 1)

# --- Process Monthly Flow ---
if not transactions.empty:
    monthly_flow = transactions.pivot_table(
        index=['Year', 'Month'],
        columns='type',
        values='amount',
        aggfunc='sum',
        fill_value=0
    ).reset_index()

    if 'Income' in monthly_flow.columns and 'Expense' in monthly_flow.columns:
        monthly_flow['Net Savings'] = monthly_flow['Income'] - monthly_flow['Expense']
        monthly_flow['Savings Rate'] = (monthly_flow['Net Savings'] / monthly_flow['Income']) * 100
        monthly_flow['Rolling Burn (3 months)'] = monthly_flow['Expense'].rolling(window=3).mean()

    monthly_flow['Timestamp'] = monthly_flow['Year'].astype(str) + "-" + monthly_flow['Month'].astype(str).str.zfill(2)
else:
    monthly_flow = pd.DataFrame(columns=['Year', 'Month', 'Income', 'Expense', 'Net Savings', 'Savings Rate', 'Rolling Burn (3 months)', 'Timestamp'])

# Default fallback burn calculation
default_burn = 80000
if not monthly_flow.empty and 'Rolling Burn (3 months)' in monthly_flow.columns and not pd.isna(monthly_flow['Rolling Burn (3 months)'].iloc[-1]):
    default_burn = round(monthly_flow['Rolling Burn (3 months)'].iloc[-1])

# ==========================================
# TAB 1: SAVINGS & EXPENSE SUMMARY
# ==========================================
if tab_selection == "Savings & Expense Summary":
    st.title("📊 Savings & Expense Summary")

    if not monthly_flow.empty and 'Income' in monthly_flow.columns and 'Expense' in monthly_flow.columns:
        monthly_flow['Savings %'] = (monthly_flow['Net Savings'] / monthly_flow['Income']) * 100
        monthly_flow['Expense %'] = (monthly_flow['Expense'] / monthly_flow['Income']) * 100

        fig_savings_stack = px.bar(
            monthly_flow,
            x='Timestamp',
            y=['Savings %', 'Expense %'],
            title="Monthly Income Allocation (%)",
            labels={'value': 'Percentage (%)', 'Timestamp': 'Month', 'variable': 'Allocation'},
            color_discrete_map={'Savings %': '#2ecc71', 'Expense %': '#e74c3c'}
        )
        fig_savings_stack.update_layout(barmode='stack', yaxis=dict(range=[0, 100]), template="plotly_dark")

        st.plotly_chart(fig_savings_stack, use_container_width=True)

        st.info("💡 **Tip:** Inspect individual months by checking your transaction database filters below.")

        selected_month = st.selectbox("Select Month to Inspect", options=monthly_flow['Timestamp'].unique() if 'Timestamp' in monthly_flow.columns else [])

        if selected_month:
            month_filter = selected_month.split("-")[1] + "-" + selected_month.split("-")[0]
            filtered_txns = transactions[transactions['Month-Year']==month_filter][['timestamp', 'type', 'category', 'note', 'amount']]
            st.markdown(f"### 📋 Transactions & Expense Distribution for {selected_month}")

            col1, col2 = st.columns(2)

            with col1:
                st.dataframe(filtered_txns, use_container_width=True)

            with col2:
                cat_breakdown = filtered_txns[filtered_txns['type']!='Income'].groupby('category')['amount'].sum().reset_index()
                fig_pie = px.pie(
                    cat_breakdown,
                    names='category',
                    values='amount',
                    title=f"Expense Categories for {selected_month}",
                    hole=0.4
                )
                fig_pie.update_layout(template="plotly_dark")
                st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.warning("No transaction records found in the database. Please verify your Supabase/SQLite connection.")

# ==========================================
# TAB 2: INVESTMENTS & FIRE
# ==========================================
elif tab_selection == "Investments & FIRE":
    st.title("🚀 Investments & FIRE Tracker")

    burn_slider = st.number_input("Monthly Expense Baseline (₹)", min_value=0, value=int(default_burn), step=5000)

    total_portfolio_value = investments['current'].sum() if not investments.empty else 9400000
    total_principal = investments['principal'].sum() if not investments.empty else 8000000
    simulated_annual_burn = burn_slider * 12
    inflation_rate = inflation_slider / 100.0
    selected_swr = swr_slider / 100.0
    annualized_cagr = cagr_slider / 100.0

    simulated_future_annual_burn = simulated_annual_burn * ((1 + inflation_rate) ** years_slider)
    baseline_corpus_multiplier = total_portfolio_value / simulated_annual_burn
    future_portfolio_value = total_portfolio_value * ((1 + annualized_cagr) ** years_slider)
    future_corpus_multiplier = future_portfolio_value / simulated_future_annual_burn

    target_corpus_multiplier = 1.0 / selected_swr
    progress_pct = min(100.0, (future_corpus_multiplier / target_corpus_multiplier) * 100)

    # Top Metrics Display
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Portfolio", f"₹{int(total_portfolio_value):,}")
    col2.metric("Forecasted Portfolio", f"₹{int(future_portfolio_value):,}")
    col3.metric("Baseline Multiplier", f"{baseline_corpus_multiplier:.2f}x")
    col4.metric("Future Multiplier", f"{future_corpus_multiplier:.2f}x", delta=f"{progress_pct:.1f}% of target")

    st.markdown("---")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Asset Allocation Distribution")
        if not investments.empty and 'type' in investments.columns:
            investments_breakdown = investments.groupby(['type'])['current'].sum().reset_index()
            investments_pie = px.pie(
                investments_breakdown,
                names='type',
                values='current',
                title="Portfolio by Asset Class",
                hole=0.4
            )
            investments_pie.update_layout(template="plotly_dark")
            st.plotly_chart(investments_pie, use_container_width=True)
        else:
            st.info("No asset breakdown found.")

    with col_right:
        st.subheader("Simulation Parameters Summary")
        st.markdown(f"""
        - **Current Annual Burn:** ₹{int(simulated_annual_burn):,}
        - **Forecasted Annual Burn (Yr {years_slider}):** ₹{int(simulated_future_annual_burn):,}
        - **Assumed CAGR:** {cagr_slider}%
        - **Inflation Rate:** {inflation_slider}%
        - **Safe Withdrawal Rate:** {swr_slider}%
        """)

# ==========================================
# TAB 3: GOAL MODELING (Dynamic Multi-Goal)
# ==========================================
elif tab_selection == "Goal Modeling":
    st.title("🎯 Goal Modeling & Event Simulator")
    st.markdown("Simulate scheduled life milestones (cars, real estate, sabbaticals) with lumpy outflows and duration-based EMIs.")

    # Initialize Session State for Goals
    if "goals" not in st.session_state:
        st.session_state.goals = [
            {"name": "Car Purchase", "year": 3, "lumpsum": 1000000, "emi": 25000, "tenure": 5},
            {"name": "House Down Payment", "year": 6, "lumpsum": 3000000, "emi": 60000, "tenure": 15}
        ]

    # Add Goal Form
    with st.form("add_goal_form", clear_on_submit=True):
        st.subheader("Add New Milestone")
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            new_name = st.text_input("Goal Name", value="Sabbatical")
            new_lumpsum = st.number_input("Lumpsum Outflow (₹)", value=500000, step=50000)
        with col_f2:
            new_year = st.slider("Target Year", 1, 20, 4)
            new_tenure = st.slider("Loan Tenure (Years)", 1, 20, 1)
        with col_f3:
            new_emi = st.number_input("Monthly EMI (₹)", value=0, step=5000)

        submitted = st.form_submit_button("➕ Add Goal to Timeline")
        if submitted:
            st.session_state.goals.append({
                "name": new_name,
                "year": new_year,
                "lumpsum": new_lumpsum,
                "emi": new_emi,
                "tenure": new_tenure
            })
            st.rerun()

    st.markdown("---")
    st.subheader("📋 Active Configured Goals")

    # Render Active Goals with Deletion
    if st.session_state.goals:
        for idx, goal in enumerate(st.session_state.goals):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.info(f"**{goal['name']}** | Year: **{goal['year']}** | Lumpsum Outflow: **₹{goal['lumpsum']:,.0f}** | EMI: **₹{goal['emi']:,.0f}/mo** for **{goal['tenure']} yrs**")
            with c2:
                if st.button("Delete", key=f"del_goal_{idx}"):
                    st.session_state.goals.pop(idx)
                    st.rerun()
    else:
        st.markdown("*No goals currently configured.*")

    st.markdown("---")
    st.subheader("📈 Multi-Goal Trajectory Simulation")

    # Run Year-by-Year Simulation Loop with Goals
    starting_portfolio = investments['current'].sum() if not investments.empty else 9400000
    base_annual_burn = default_burn * 12
    horizon = years_slider
    inflation_rate = inflation_slider / 100.0
    annualized_cagr = cagr_slider / 100.0
    selected_swr = swr_slider / 100.0

    timeline_years = list(range(horizon + 1))
    portfolio_timeline = []
    burn_timeline = []
    current_port = starting_portfolio

    for t in timeline_years:
        inflated_base_burn = base_annual_burn * ((1 + inflation_rate) ** t)

        # Cumulative active EMIs
        total_active_emi = sum(
            g['emi'] * 12 for g in st.session_state.goals
            if g['year'] <= t < g['year'] + g['tenure']
        )

        total_year_burn = inflated_base_burn + total_active_emi
        burn_timeline.append(total_year_burn)

        # Lumpsum outflows
        for g in st.session_state.goals:
            if t == g['year']:
                current_port = max(0, current_port - g['lumpsum'])

        portfolio_timeline.append(current_port)

        if t < horizon:
            current_port = current_port * (1 + annualized_cagr)

    final_port = portfolio_timeline[-1]
    final_burn = burn_timeline[-1]
    goal_future_multiplier = final_port / final_burn
    target_mult = 1.0 / selected_swr
    goal_progress = min(100.0, (goal_future_multiplier / target_mult) * 100)

    # Clean Baseline for comparison
    clean_burn = base_annual_burn * ((1 + inflation_rate) ** horizon)
    clean_port = starting_portfolio * ((1 + annualized_cagr) ** horizon)
    clean_mult = clean_port / clean_burn
    clean_progress = min(100.0, (clean_mult / target_mult) * 100)
    delta_progress = goal_progress - clean_progress

    col_res1, col_res2, col_res3 = st.columns(3)
    col_res1.metric("Projected Corpus (With Goals)", f"₹{int(final_port):,}")
    col_res2.metric("Future Multiplier", f"{goal_future_multiplier:.2f}x", delta=f"{delta_progress:+.1f}% vs baseline")
    col_res3.metric("Goal Progress", f"{goal_progress:.1f}%", f"Target: {target_mult*int(100)}x")

# ==========================================
# TAB 4: GOAL MODELING (Dynamic Multi-Goal)
# ==========================================
elif tab_selection == "Expense Logging":

    st.header("Transaction Logger")

    with open('config.json', 'rb') as f:
        config = json.load(f)

    with st.form("expense_form"):
        st.write("Log Transaction - Income/Expense")
        timestamp = st.date_input("Transaction Date", date(datetime.now().year, datetime.now().month, datetime.now().day))
        type = st.radio("Select record type", ("Expense", "Income"))
        category = st.selectbox("Select expense category", config['transaction_choices'])
        amount = st.number_input("Enter transaction amount", value=0)
        note = st.text_input("Any additional details")
        submitted = st.form_submit_button("Submit")
        if submitted:
            try:
                db_obj.insert_record(timestamp, type, category, amount, note)
                st.toast('Transaction logged successfully', icon="✅")
            except Exception as e:
                st.error(f'Unable to log transation: {e}')

    st.divider()

    st.header("Daily Log")
    if st.button("Refresh"):
        st.write("Today's Transactions")
        daily_records = db_obj.fetch_daily_records()
        st.table(daily_records)
        # fetch latest from DB for today
