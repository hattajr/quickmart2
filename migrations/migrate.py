import datetime
import os
import shlex
import subprocess
import time
from pathlib import Path

import polars as pl
import psycopg2
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

BASE_DIR = Path(__file__).parent  # in container -> /app/migrations
logger.debug(f"BASE_DIR: {BASE_DIR}")
MIGRATIONS_DIR = BASE_DIR  # / "migrations"
SNAPSHOT_DIR = BASE_DIR / "snapshots"
SCHEMA_FINAL = BASE_DIR / "schema.sql"


ENV = os.getenv("ENV")
RDB_USER = os.getenv("RDB_USER")
RDB_PASSWORD = os.getenv("RDB_PASSWORD")
RDB_HOST = os.getenv("RDB_HOST")
RDB_HOST_DOCKER = os.getenv("RDB_HOST_DOCKER")
RDB_PORT = os.getenv("RDB_PORT")
RDB_DATABASE = os.getenv("RDB_DATABASE")

RDB_URL = f"postgresql://{RDB_USER}:{RDB_PASSWORD}@{RDB_HOST}:{RDB_PORT}/{RDB_DATABASE}"


def dump_schema_to_file(output_path):
    # Build the shell command string
    command = f"pg_dump --schema-only --no-owner --no-privileges --dbname={shlex.quote(RDB_URL)} > {shlex.quote(str(output_path))}"

    # Run the command with shell=True to allow output redirection
    result = subprocess.run(command, shell=True)

    if result.returncode != 0:
        print(f"❌ Failed to dump schema to {output_path}")
    else:
        print(f"✅ Schema dumped to {output_path}")


def run_migrations():
    db_url = RDB_URL
    for _ in range(5):
        try:
            with psycopg2.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            filename TEXT PRIMARY KEY,
                            applied_at TIMESTAMPTZ DEFAULT now()
                        )
                    """)
                    conn.commit()

                    for file in sorted(MIGRATIONS_DIR.glob("0*.sql")):
                        filename = file.name
                        snapshot_path = SNAPSHOT_DIR / f"{filename}.snapshot.sql"

                        cur.execute(
                            "SELECT 1 FROM schema_migrations WHERE filename = %s",
                            (filename,),
                        )
                        applied = cur.fetchone()

                        if applied:
                            print(f"✅ Already applied: {filename}")
                            continue

                        print(f"📦 Applying: {filename}")
                        sql = file.read_text()
                        cur.execute(sql)
                        cur.execute(
                            "INSERT INTO schema_migrations (filename, applied_at) VALUES (%s, %s)",
                            (filename, datetime.datetime.now(datetime.UTC)),
                        )
                        conn.commit()
                        print(f"✅ Done: {filename}")

                        dump_schema_to_file(snapshot_path)
                        print(f"🧾 Snapshot saved: {snapshot_path}")

            dump_schema_to_file(SCHEMA_FINAL)
            print(f"📄 Final schema snapshot updated: {SCHEMA_FINAL}")
            print("🎉 All migrations applied.")
            break
        except psycopg2.OperationalError as e:
            print(f"❌ Connection failed: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(3)
    else:
        raise RuntimeError("🚨 Failed to connect to DB after 5 attempts.")


def insert_data():
    MASTERDB_USER = os.getenv("MASTERDB_USER")
    MASTERDB_PASSWORD = os.getenv("MASTERDB_PASSWORD")
    MASTERDB_HOST = os.getenv("MASTERDB_HOST")
    MASTERDB_PORT = os.getenv("MASTERDB_PORT")
    MASTERDB_DATABASE = os.getenv("MASTERDB_DATABASE")
    MASTERDB_URL = f"postgresql://{MASTERDB_USER}:{MASTERDB_PASSWORD}@{MASTERDB_HOST}:{MASTERDB_PORT}/{MASTERDB_DATABASE}"

    q = "SELECT * FROM products"
    df_local = pl.read_database_uri(query=q, uri=RDB_URL)
    if df_local.is_empty():
        q = "SELECT * FROM products_new"
        df = pl.read_database_uri(query=q, uri=MASTERDB_URL)
        df = (
            df.select(
                "id",
                "name",
                "barcode",
                "unit",
                "brand",
                "price",
                "search_term",
                "quantity",
                "create_time",
                "update_time",
            )
            .with_columns(
                [
                    pl.col("create_time").dt.replace_time_zone("UTC"),
                    pl.col("update_time").dt.replace_time_zone("UTC"),
                ]
            )
            .rename(
                {
                    "search_term": "keyword",
                    "quantity": "stock",
                    "create_time": "created_at",
                    "update_time": "updated_at",
                }
            )
        )
        df.write_database(
            table_name="products",
            connection=RDB_URL,
            if_table_exists="append",
            engine="sqlalchemy",
        )
        print("✅ Data inserted into products table.")
    else:
        print(
            "❌ products_new table already exists in the local database. No data inserted."
        )


if __name__ == "__main__":
    run_migrations()
    insert_data()
