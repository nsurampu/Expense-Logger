from datetime import datetime
from db import DB
import json
import pandas as pd
from pandas.core.arrays.arrow.array import date
import streamlit as st



@st.cache_resource
def get_db_obj():
    return DB(st.secrets['supabase']['url'])

db_obj = get_db_obj()

st.header("Transaction Logger")

with open('config.json', 'rb') as f:
    config = json.load(f)

# timestamp autopopulates
# type dropdown
# category dropdown
# note text
# amount numeric

with st.form("expense_form"):
    st.write("Log Transaction - Income/Expense")
    timestamp = st.date_input("Transaction Date", date(datetime.now().year, datetime.now().month, datetime.now().day))
    type = st.radio("Select record type", ("Expense", "Income"))
    if type=='Expense':
        category = st.selectbox("Select expense category", config['expense_choices'])
    else:
        category = st.selectbox("Select income category", config['income_choices'])
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
