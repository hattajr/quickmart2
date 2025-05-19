from db.database import MASTER_DATABASE_URL, LOCAL_DATABASE_URL, get_local_db
import polars as pl

SQLITE_DB = "sqlite:///data.db"  # Valid SQLite connection string format for relative path to db/data.db

# q = f"SELECT * FROM products_new"
# df = pl.read_database_uri(query=q, uri=MASTER_DATABASE_URL)


# Create SQLite connection string

# df.write_database(
#     table_name="products_new",
#     connection=SQLITE_DB,
#     if_table_exists="replace",
#     engine="sqlalchemy"
# )

q = f"SELECT * FROM products_new limit 1"
df = pl.read_database(query=q, connection=next(get_local_db()))
print(df)
