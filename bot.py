import os
import sys

import polars as pl
import psycopg2
from dotenv import load_dotenv
from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logger.remove()
logger.add(sys.stdout, level="DEBUG")

MASTERDB_USER = os.getenv("MASTERDB_USER")
MASTERDB_PASSWORD = os.getenv("MASTERDB_PASSWORD")
MASTERDB_HOST = os.getenv("MASTERDB_HOST")
MASTERDB_PORT = os.getenv("MASTERDB_PORT")
MASTERDB_DATABASE = os.getenv("MASTERDB_DATABASE")

RDB_USER = os.getenv("RDB_USER")
RDB_PASSWORD = os.getenv("RDB_PASSWORD")
RDB_HOST = os.getenv("RDB_HOST")
RDB_HOST_DOCKER = os.getenv("RDB_HOST_DOCKER")
RDB_PORT = os.getenv("RDB_PORT")
RDB_DATABASE = os.getenv("RDB_DATABASE")

RDB_URL = f"postgresql://{RDB_USER}:{RDB_PASSWORD}@{RDB_HOST}:{RDB_PORT}/{RDB_DATABASE}"
MASTER_DATABASE_URL = f"postgresql://{MASTERDB_USER}:{MASTERDB_PASSWORD}@{MASTERDB_HOST}:{MASTERDB_PORT}/{MASTERDB_DATABASE}"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def get_products(keyword: str) -> list[dict]:
    q = f"SELECT id, name, price FROM products WHERE name ILIKE '%{keyword}%' OR keyword ILIKE '%{keyword}%'"
    df = pl.read_database_uri(query=q, uri=RDB_URL)
    logger.debug(f"Query executed: {q}")
    return df.to_dicts()


def insert_product(product):
    try:
        with psycopg2.connect(RDB_URL) as conn:
            with conn.cursor() as cur:
                # "INSERT/Product Name/3000/4000"
                q = """
                INSERT INTO products (name, purchase_price, price)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET purchase_price = EXCLUDED.purchase_price, price = EXCLUDED.price
                """
                cur.execute(
                    q,
                    (
                        product["name"],
                        product["purchase_price"],
                        product["selling_price"],
                    ),
                )
                conn.commit()
                logger.debug(f"Product inserted: {product}")
                formatted_product_details = f"Name: {product['name']}\nHarga Beli: {product['purchase_price']}\nHarga Jual: {product['selling_price']}"
                return f"✅ Product '{product['name']}' inserted successfully.\n{formatted_product_details}"
    except psycopg2.Error as e:
        logger.error(f"Error inserting product: {e}")
        return f"❌ Error inserting product: {e}"
    return f"✅ Product '{product['name']}' inserted successfully. {product}"


def update_product(product_id, new_selling_price):
    try:
        with psycopg2.connect(RDB_URL) as conn:
            with conn.cursor() as cur:
                q = """
                UPDATE products
                SET price = %s
                WHERE id = %s
                RETURNING id, name, price
                """
                cur.execute(q, (new_selling_price, product_id))
                conn.commit()
                logger.debug(f"Product updated: {product_id}, {new_selling_price}")
                if cur.rowcount == 0:
                    return f"❌ Product ID {product_id} not found."
                updated_product = cur.fetchone()
                formatted_product_details = f"Product ID: {updated_product[0]}\nName: {updated_product[1]}\nHarga Jual: {updated_product[2]}"
                return f"✅ Product ID {product_id} updated successfully.\n{formatted_product_details}"
    except psycopg2.Error as e:
        logger.error(f"Error updating product: {e}")
        return f"❌ Error updating product: {e}"


def delete_product(product_id):
    try:
        with psycopg2.connect(RDB_URL) as conn:
            with conn.cursor() as cur:
                q = """
                DELETE FROM products
                WHERE id = %s
                RETURNING id, name, price
                """
                cur.execute(q, (product_id,))
                conn.commit()
                logger.debug(f"Product deleted: {product_id}")
                if cur.rowcount == 0:
                    return f"❌ Product ID {product_id} not found."
                deleted_product = cur.fetchone()
                formatted_product_details = f"Product ID: {deleted_product[0]}\nName: {deleted_product[1]}\nHarga Jual: {deleted_product[2]}"
                return f"✅ Product ID {product_id} deleted successfully.\n{formatted_product_details}"
    except psycopg2.Error as e:
        logger.error(f"Error deleting product: {e}")
        return f"❌ Error deleting product: {e}"


def sync_supabase():
    logger.debug(MASTER_DATABASE_URL)
    logger.debug(RDB_URL)

    df_supabase = pl.read_database_uri(
        query="SELECT name, price FROM products_new", uri=MASTER_DATABASE_URL
    ).cast({"price": pl.Int32})
    df_local = pl.read_database_uri(
        query="SELECT name, price FROM products", uri=RDB_URL
    )

    df_diff = df_local.join(
        df_supabase,
        on=["name", "price"],
        how="anti",  # Get rows in local that are not in supabase
    )

    logger.debug(df_diff)
    if not df_diff.is_empty():
        with psycopg2.connect(MASTER_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # on conflict update price
                for row in df_diff.iter_rows(named=True):
                    q = """
                    INSERT INTO products_new (name, price)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO UPDATE
                    SET price = EXCLUDED.price
                    """
                    cur.execute(q, (row["name"], row["price"]))
                conn.commit()
    logger.debug("Database synced with the legacy supabase database.")
    logger.debug("Sync completed.")
    formatted_diff = "\n".join(
        [f"{row['name']}: {row['price']}" for row in df_diff.iter_rows(named=True)]
    )

    return f"✅ Database synced with the legacy supabase database.\n{formatted_diff}\nPlease update the local database at ikmimart.onrender.com"


def parse_message(text):
    # NOTE
    # FORMAT: "command/product_id/product_name/purchase_price/selling_price"
    # Command: INSERT, UPDATE, DELETE
    # EXAMPLE:
    # "GET/keyword" or "GET/keyword1,keyword2"
    # "INSERT/Product Name/3000/4000"
    # "UPDATE/123/4000"
    # "DELETE/123"

    parts = text.split("/")
    command = parts[0]

    if command not in ["HELP", "GET", "INSERT", "UPDATE", "DELETE", "SYNC"]:
        logger.debug(f"Invalid command: {command}")
        return (
            None,
            f"❌ Invalid command: {command}, expected GET, INSERT, UPDATE, DELETE, or SYNC.",
        )
    if command == "HELP":
        help_text = (
            "Available commands:\n"
            "- GET/keyword or GET/keyword1,keyword2: Search for products by keyword(s).\n"
            "- INSERT/product_name/purchase_price(set 1 if not sure)/selling_price: Add a new product.\n"
            "- UPDATE/product_id/selling_price: Update an existing product's selling price.\n"
            "- DELETE/product_id: Delete a product by ID.\n"
            "- SYNC: Sync the database with the legacy supabase database.\n"
        )
        logger.debug("Help command received.")
        return None, help_text

    if command == "GET":
        keywords = parts[1].split(",") if len(parts) > 1 else []

        products = []
        for keyword in keywords:
            p = get_products(keyword)
            if p:
                products.extend(p)
                logger.debug(f"Products found for keyword '{keyword}': {p}")
            else:
                logger.debug(f"No products found for keyword '{keyword}'.")

        formatted_products = "\n".join(
            [f"({p['id']}) {p['name']}: {p['price']}" for p in products]
        )
        return (
            None,
            f"Products found:\n{formatted_products}"
            if products
            else "❌ No products found.",
        )

    if command == "INSERT":
        # "INSERT/Product Name/3000/4000"
        if len(parts) < 4:
            logger.debug("Invalid INSERT command format.")
            return (
                None,
                "❌ Invalid INSERT command format. Expected: INSERT/product_name/harga_modal/harga_jual.",
            )
        product_name = parts[1]
        if not product_name:
            logger.debug("Product name is required.")
            return None, "❌ Product name is required."
        purchase_price = parts[2] if len(parts) > 2 else None
        if not purchase_price.isdigit():
            logger.debug(f"Invalid purchase_price: {purchase_price}")
            return (
                None,
                f"❌ Invalid purchase_price: {purchase_price}, must be a number.",
            )
        selling_price = parts[3] if len(parts) > 3 else None
        if not selling_price.isdigit():
            logger.debug(f"Invalid selling_price: {selling_price}")
            return None, f"❌ Invalid selling_price: {selling_price}, must be a number."

        product = {
            "name": product_name,
            "purchase_price": int(purchase_price),
            "selling_price": int(selling_price),
        }
        msg = insert_product(product)
        return None, msg
    elif command == "UPDATE":
        # "- UPDATE/product_id/selling_price: Update an existing product's selling price.\n"
        if len(parts) < 3:
            logger.debug("Invalid UPDATE command format.")
            return (
                None,
                "❌ Invalid UPDATE command format. Expected: UPDATE/product_id/selling_price.",
            )
        product_id = parts[1]
        if not product_id.isdigit():
            logger.debug(f"Invalid product_id: {product_id}")
            return None, f"❌ Invalid product_id: {product_id}, must be a number."
        selling_price = parts[2]
        if not selling_price.isdigit():
            logger.debug(f"Invalid selling_price: {selling_price}")
            return None, f"❌ Invalid selling_price: {selling_price}, must be a number."
        msg = update_product(int(product_id), int(selling_price))
        return None, msg

    elif command == "DELETE":
        # "DELETE/123"
        if len(parts) < 2:
            logger.debug("Invalid DELETE command format.")
            return (
                None,
                "❌ Invalid DELETE command format. Expected: DELETE/product_id.",
            )
        product_id = parts[1]
        if not product_id.isdigit():
            logger.debug(f"Invalid product_id: {product_id}")
            return None, f"❌ Invalid product_id: {product_id}, must be a number."
        msg = delete_product(int(product_id))
        return None, msg
    
    elif command == "SYNC":
        logger.debug("Sync command received.")
        msg = sync_supabase()
        return None, msg

    else:
        return (
            None,
            f"❌ Unknown command: {command}. Please use HELP to see available commands.",
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me any text and I'll save it to the database."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"Message text: {text}")

    product, error = parse_message(text)
    if error:
        logger.error(error)
        await update.message.reply_text(error)
        return
    logger.info(f"Parsed product: {product}")
    await update.message.reply_text(f"Parsed product: {product}")

def main():
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Start the bot
    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
