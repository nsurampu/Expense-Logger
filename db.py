from datetime import datetime
import pandas as pd
import sqlalchemy

class DB:


    def __init__(self, db_url):
        self.engine = sqlalchemy.create_engine(db_url)


    def get_record_count(self):
        return pd.read_sql("SELECT MAX(id) from expenses AS max", self.engine)


    def insert_record(self, timestamp, type, category, amount, note):
        id = int(self.get_record_count()['max'].values[0] + 1)
        query = sqlalchemy.text("""
            INSERT INTO expenses (id, timestamp, type, category, note, amount)
            VALUES (:id, :timestamp, :type, :category, :note, :amount)
        """)
        with self.engine.begin() as conn:
            conn.execute(query, {
                "id": id,
                "timestamp": timestamp,
                "type": type,
                "category": category,
                "note": note,
                "amount": amount
            })

    def fetch_daily_records(self):
        timestamp = datetime.now().strftime("%Y-%m-%d")
        return pd.read_sql(f"SELECT * FROM expenses WHERE timestamp='{timestamp}'", self.engine)


    def fetch_transaction_records(self):
        return pd.read_sql("SELECT * FROM expenses", self.engine)


    def fetch_investment_records(self):
        return pd.read_sql("SELECT * FROM investments", self.engine)
