import datetime
import os
import shutil
import sys
import uuid
from collections import deque, defaultdict, Counter
from tempfile import NamedTemporaryFile
from typing import Any
from rapidfuzz import process, fuzz, utils

import polars as pl
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Query, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks
from loguru import logger
from sqlalchemy.orm import Session

from db.database import get_local_db
from inference import get_prediction_result
from schema.schema import SearchLog
from services.db_services import log_search_query

load_dotenv()

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "DEBUG").upper())
logger.info(f"Web server run at port {os.getenv('APP_PORT')}")


app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)

PRODUCT_IMAGE_URL = "/static/images"
IMAGE_FORMAT = "png"
SESSION_COOKIE_NAME = "ikmimart_session_id"
SESSION_EXPIRY_MINUTES = 30

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Blocks(directory="templates")

session_data = {}


def get_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def generate_session_id() -> str:
    return str(uuid.uuid4())


def get_session_id(request: Request) -> str | None:
    """Get session ID from cookie"""
    return request.cookies.get(SESSION_COOKIE_NAME)


def create_session_id(response: Response) -> tuple[str, Response]:
    session_id = generate_session_id()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_EXPIRY_MINUTES * 60,  # 30 minutes in seconds
        httponly=True,  # Set to True if you don't need JS access
        secure=False,  # Set to False for development (HTTP)
        samesite="lax",
    )

    # Initialize empty session data in Redis
    session_data[session_id] = {
        "created_at": get_now(),
        "cart": {},
        "search_history": deque(maxlen=5),
    }
    return session_id, response


def get_or_create_session(request: Request, response: Response) -> tuple[str, Response]:
    """Get existing session or create new one"""
    session_id = get_session_id(request)

    logger.debug(session_id)
    logger.debug(session_data.keys())
    if session_id and session_id in session_data:
        # Session exists, extend expiry
        logger.info("Session exists")
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            max_age=SESSION_EXPIRY_MINUTES * 60,  # 30 minutes in seconds
            httponly=True,  # Set to True if you don't need JS access
            secure=False,  # Set to False for development (HTTP)
            samesite="lax",
        )
        return session_id, response
    logger.info("Create NEW SESSION")
    return create_session_id(response)


def get_session_data(session_id: str) -> dict[str, Any]:
    """Get session data from Redis"""
    data = session_data.get(session_id)
    if data:
        return data
    return {}


async def get_session(request: Request, response: Response) -> str:
    return get_or_create_session(request, response)


def get_cart(session_id: str, db: Session) -> pl.DataFrame:
    session_data = get_session_data(session_id)
    cart = session_data.get("cart")
    if not cart:
        return pl.DataFrame()
    logger.debug(cart)

    cart_ = []
    for product_id, product in cart.items():
        cart_.append(
            dict(
                id=product_id,
                qty=product["qty"],
                updated_at=product["updated_at"],
            )
        )

    df_cart = pl.DataFrame(cart_)
    df_product = search_product_by_id(list(cart.keys()), db=db)
    logger.debug(df_product)
    if df_product.is_empty():
        return pl.DataFrame()

    df_result = (
        df_cart.join(
            df_product,
            left_on="id",
            right_on="id",
        )
        .with_columns(total_price=pl.col("qty") * pl.col("price"))
        .sort("updated_at", descending=True)
    )
    return df_result

def postprocess_query_result(df: pl.DataFrame) -> pl.DataFrame:
    df = (
        df.with_columns(
            image_url=pl.when(
                ~(pl.col("image_url").is_not_null())
                & (pl.col("barcode").is_not_null())
            )
            .then(
                pl.concat_str(
                    [pl.lit(PRODUCT_IMAGE_URL), pl.col("barcode")], separator="/"
                )
            )
            .otherwise(pl.col("image_url"))
        )
        .with_columns(
            image_url=pl.when(
                pl.col("image_url").str.starts_with(PRODUCT_IMAGE_URL)
            )
            .then(
                pl.concat_str(
                    [pl.col("image_url"), pl.lit(IMAGE_FORMAT)], separator="."
                )
            )
            .otherwise(pl.col("image_url"))
        )
        .with_columns(name=pl.col("name").str.to_titlecase())
    )
    logger.debug(df)
    return df

def query_products(query: str, db: Session) -> pl.DataFrame:
    df = pl.read_database(query=query, connection=db, infer_schema_length=500)
    logger.debug(df)
    if not df.is_empty():
        df = postprocess_query_result(df)
        return df
    return pl.DataFrame()

def fuzz_search_products(keyword: str, db: Session) -> pl.DataFrame:
    df = pl.read_database(query="SELECT id, barcode, name, brand, keyword, price, unit, image_url FROM products", connection=db, infer_schema_length=500)
    logger.debug(df)
    df = df.with_columns(join_str=pl.concat_str(["name", "brand", "keyword"], separator=" ", ignore_nulls=True)).sort("id")
    prodcuts_names = df['join_str'].to_list()
    results = process.extract(keyword, prodcuts_names, scorer=fuzz.WRatio, limit=6, processor=utils.default_process, score_cutoff=60)
    logger.debug(f"Fuzz search results for '{keyword}': {results}")
    if results:
        selected_rows = []
        for result in results:
            if result[1] >= 60:
                _d = dict(
                    product_str = result[0],
                    score = result[1],
                    index = result[2]
                )
                selected_rows.append(_d)
        df_matched = pl.from_dicts(selected_rows)
        logger.debug(df_matched)

        df_result = df.join(
            df_matched,
            left_on="join_str",
            right_on="product_str",
        ).select(
            "id", "barcode", "name", "price", "unit", "image_url", "score"
        ).sort("score", descending=True)

        df_result = postprocess_query_result(df_result)
        logger.debug(df_result)
        return df_result
    return pl.DataFrame()

def search_product_by_keyword(keyword: str, db: Session) -> pl.DataFrame:
    if keyword == "CATALOG":
        q = "SELECT id, barcode, name, price, unit, image_url FROM products"
        return query_products(q, db)
    q = f"""
        SELECT id, barcode, name, price, unit, image_url
        FROM public.products
        WHERE (COALESCE(name, '') || ' ' || COALESCE(brand, '') || ' ' || COALESCE(keyword, '')) ILIKE '%{keyword}%';
    """
    df = query_products(q, db)
    if df.is_empty():
        df = fuzz_search_products(keyword, db)
    return df


def search_product_by_id(id: int | list[int], db: Session) -> pl.DataFrame:
    if isinstance(id, list):
        id = ",".join([str(i) for i in id])
        query = f"SELECT * FROM products WHERE id IN ({id})"
        logger.debug(query)
    else:
        id = str(id)
        query = f"SELECT * FROM products WHERE id = {id}"
        logger.debug(query)
    return query_products(query, db)

def get_top_queries(db, top_n=15):
    q = """
    SELECT query 
    FROM search_logs 
    WHERE searched_at > NOW() - INTERVAL '14 days'
      AND items_found BETWEEN 1 AND 10
    """
    df = pl.read_database(query=q, connection=db)

    if df.is_empty():
        return []
    
    df = df.filter(
        (pl.col("query").str.len_chars() >= 4) &
        pl.col("query").str.contains("^[a-zA-Z0-9 ]+$")
    )
    
    queries = [q.strip().lower() for q in df['query'].to_list()]
    queries = [q.replace("  ", " ") for q in queries if q]  # Remove empty strings and extra spaces
    counts = Counter(queries)

    unvisited = set(counts.keys())
    clusters = []

    while unvisited:
        q = unvisited.pop()
        matches = process.extract(q, unvisited, scorer=fuzz.token_sort_ratio, limit=20)
        group = [q] + [m[0] for m in matches if m[1] > 85]
        unvisited.difference_update(group[1:]) 
        clusters.append(group)

    results = []
    for group in clusters:
        canonical = max(group, key=lambda q: (len(q)))
        total = sum(counts[q] for q in group)
        results.append((canonical, total))

    return sorted(results, key=lambda x: x[1], reverse=True)[:top_n]

@app.get("/", response_class=HTMLResponse)
def root(request: Request, response: Response, db: Session = Depends(get_local_db)):
    top_queries = get_top_queries(db)
    context = {"request": request, "top_queries": top_queries}
    if not request.headers.get("HX-Request"):
        response = templates.TemplateResponse(request=request, name="index.html", context=context)
        response.delete_cookie(SESSION_COOKIE_NAME)
        logger.debug(session_data.keys())
        return response
    response = templates.TemplateResponse(
        request=request, name="index.html", context=context
    )
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    response: Response,
    q: str = Query(...),
    db: Session = Depends(get_local_db),
):
    if not request.headers.get("HX-Request"):
        response = RedirectResponse(url="/")
        response.delete_cookie(SESSION_COOKIE_NAME)
        logger.debug(session_data.keys())
        return response
    session_id, response = get_or_create_session(request=request, response=response)
    top_queries = get_top_queries(db)
    url = request.headers.get("HX-Current-URL").split("/")[-1]
    if url == "cart":
        logger.debug(session_data[session_id])
        q = session_data[session_id]["search_history"][-1] if session_data[session_id]["search_history"] else ""
        products_search = search_product_by_keyword(q, db)
        products = get_cart(session_id, db=db)
        context = dict(
            products=products_search.to_dicts(),
            total_price=products["total_price"].sum(),
            total_items=products["qty"].sum(),
            top_queries=top_queries,
        )
        return templates.TemplateResponse(
            request=request, name="index.html", context=context
        )

    keyword = q
    products = search_product_by_keyword(keyword, db)
    session_data[session_id]["search_history"].append(keyword)
    logger.debug(session_data[session_id]["search_history"])
    logger.debug(f"{session_id}: {session_data[session_id]}")

    log_search_query(
        db=db,
        search_log=SearchLog(
            session_id=session_id,
            query=keyword,
            searched_at=get_now().isoformat(),
            items_found=len(products) if not products.is_empty() else 0,
        ),
    )

    context = {"request": request, "products": products.to_dicts()}
    response = templates.TemplateResponse(
        "index.html", context=context, block_names=["result_list"]
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_EXPIRY_MINUTES * 60,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return response


@app.get("/show-camera", response_class=HTMLResponse)
async def show_camera(request: Request, response: Response):
    logger.debug("Show camera")
    if not request.headers.get("HX-Request"):
        response = templates.TemplateResponse(request=request, name="index.html")
        return response
    response = templates.TemplateResponse(
        request=request, name="camera_modal.html", context={"request": request}
    )
    return response


@app.get("/cart", response_class=HTMLResponse)
async def view_cart(
    request: Request, response: Response, db: Session = Depends(get_local_db)
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id or session_id not in session_data:
        response = RedirectResponse(url="/")
        response.delete_cookie(SESSION_COOKIE_NAME)
        return response

    df_cart = get_cart(session_id, db=db)
    logger.debug(df_cart)
    context = dict(
        cart=df_cart.to_dicts(),
        total_price=f"{df_cart['total_price'].sum():,.0f}",
        total_items=df_cart["qty"].sum(),
        last_query=session_data[session_id]["search_history"][-1],
    )

    if not request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request, name="cart.html", context=context
        )
    return templates.TemplateResponse(
        request=request, name="cart.html", context=context
    )


@app.post("/cart/add", response_class=HTMLResponse)
async def add_to_cart(
    request: Request,
    response: Response,
    product_id: int = Query(...),
    db: Session = Depends(get_local_db),
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if product_id not in session_data[session_id]["cart"]:
        session_data[session_id]["cart"][product_id] = {
            "qty": 0,
            "updated_at": get_now(),
        }
    session_data[session_id]["cart"][product_id]["qty"] += 1
    session_data[session_id]["cart"][product_id]["updated_at"] = get_now()

    df_cart = get_cart(session_id, db=db)
    logger.debug(df_cart)

    url = request.headers.get("HX-Current-URL").split("/")[-1]
    logger.debug(url)
    if url == "cart":
        df_product = df_cart.filter(pl.col("id") == product_id)
        context = dict(
            product=df_product.to_dicts()[0] if not df_product.is_empty() else None,
            total_price=f"{df_cart['total_price'].sum():,.0f}",
            total_items=df_cart["qty"].sum(),
        )
        return templates.TemplateResponse(
            request=request, name="cart/partials/item.html", context=context
        )

    context = {
        "session_id": session_id,
        "total_items": df_cart["qty"].sum(),
    }
    logger.debug(context)
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context=context,
        block_name="cart_count_badge",
    )
    # _, response = get_or_create_session(request, response)
    logger.debug(session_data[session_id])
    return response


@app.post("/cart/item/{product_id}", response_class=HTMLResponse)
async def cart_item_change_count(
    request: Request,
    response: Response,
    product_id: int,
    action: str = Query(...),
    db: Session = Depends(get_local_db),
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    def _updated_data():
        logger.info("Get data from cart")
        df_cart = get_cart(session_id, db=db)
        df_product = df_cart.filter(pl.col("id") == product_id)
        context = {
            "product": df_product.to_dicts()[0] if not df_product.is_empty() else None,
            "total_price": f"{df_cart['total_price'].sum():,.0f}",
            "total_items": df_cart["qty"].sum(),
        }
        return templates.TemplateResponse(
            request=request,
            name="cart/partials/item_count_change.html",
            context=context,
        )

    cart = session_data[session_id]["cart"]
    if action == "increase":
        cart[product_id]["qty"] += 1
        return _updated_data()
    elif action == "decrease":
        if cart[product_id]["qty"] <= 1:
            cart[product_id]["qty"] = 1
            return _updated_data()
        else:
            cart[product_id]["qty"] -= 1
            return _updated_data()
    elif action == "remove":
        del session_data[session_id]["cart"][product_id]
        df_cart = get_cart(session_id, db=db)
        logger.debug(df_cart)
        context = dict(
            cart=df_cart.to_dicts(),
            total_price=f"{df_cart['total_price'].sum():,.0f}"
            if not df_cart.is_empty()
            else 0,
            total_items=df_cart["qty"].sum() if not df_cart.is_empty() else 0,
        )
        return templates.TemplateResponse(
            request=request,
            name="cart.html",
            context=context,
            block_name="main_content",
        )

    else:
        raise ValueError("Invalid action")


@app.post("/cart/clear", response_class=HTMLResponse)
async def clear_cart(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    cart = session_data[session_id]["cart"]
    if cart:
        del session_data[session_id]["cart"]
    response = templates.TemplateResponse(
        request=request,
        # name="cart/partials/cart.html",
        name="cart.html",
    )
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/cart/checkout", response_class=HTMLResponse)
async def checkout(
    request: Request, response: Response, db: Session = Depends(get_local_db)
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    df_cart = get_cart(session_id, db=db)
    item_count = df_cart["qty"].sum()
    total_price = df_cart["total_price"].sum()

    account_info = {
        "bank": "HANA BANK",
        "name": "APRILIYANTO FADA",
        "account_number": "3989 1053 191007",
        "phone": "010 5608 2996",
    }
    context = {
        "item_count": item_count,
        "total_price": f"{total_price:,.0f}",
        "account_info": account_info,
    }

    return templates.TemplateResponse(
        request=request, name="cart/checkout_modal.html", context=context
    )


@app.get("/cart/checkout/confirm", response_class=HTMLResponse)
async def checkout_confirm(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id and session_id in session_data:
        del session_data[session_id]
    # Create a response with cache-control headers to prevent back navigation
    response = response(status_code=204)
    # response = templates.TemplateResponse(request=request, name="index.html")
    # Add headers to prevent caching
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, post-check=0, pre-check=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["HX-Redirect"] = "/"
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.post("/upload", response_class=HTMLResponse)
async def upload_image(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_local_db),
):
    if not request.headers.get("HX-Request"):
        response = templates.TemplateResponse(request=request, name="index.html")
        return response

    session_id, response = get_or_create_session(request=request, response=response)
    url = request.headers.get("HX-Current-URL").split("/")[-1]
    if url == "cart":
        logger.debug(session_data[session_id])
        q = session_data[session_id]["search_history"][-1]
        products_search = search_product_by_keyword(q, db)
        products = get_cart(session_id, db=db)
        context = dict(
            products=products_search.to_dicts(),
            total_price=products["total_price"].sum(),
            total_items=products["qty"].sum(),
        )
        return templates.TemplateResponse(
            request=request, name="index.html", context=context
        )

    with NamedTemporaryFile(delete=True, suffix=".jpg") as temp_file:
        file_path = temp_file.name
        logger.debug(file_path)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            df_prediction = get_prediction_result(file_path)
            logger.debug(df_prediction)

    context = {"request": request, "products": {}}
    if df_prediction is None:
        logger.info("No prediction found None")
        return templates.TemplateResponse(
            "index.html", context=context, block_name="result_list"
        )

    if df_prediction.is_empty():
        logger.info("No prediction found Empty")
        return templates.TemplateResponse(
            "index.html", context=context, block_name="result_list"
        )

    dfs_queried = []
    for product in df_prediction.to_dicts():
        logger.debug(product)
        keywords = product.get("keywords")
        found = False
        for keyword in keywords:
            df = search_product_by_keyword(keyword, db=db)
            session_data[session_id]["search_history"].append(keyword)
            logger.debug(df)
            if not df.is_empty():
                dfs_queried.append(df)
                found = True
                log_search_query(
                    db=db,
                    search_log=SearchLog(
                        session_id=session_id,
                        query=keyword,
                        searched_at=get_now().isoformat(),
                        items_found=len(df) if not df.is_empty() else 0,
                    ),
                )
                break
        if found:
            continue

    logger.debug(session_data[session_id]["search_history"])
    logger.debug(f"{session_id}: {session_data[session_id]}")

    # IF NOT FOUND, SPLIT ALL THE KEYWORD FOR EACH WORD AND START SEAARCH AGAIN

    df_result = pl.concat(dfs_queried, how="vertical_relaxed")
    products = df_result.to_dicts()
    logger.debug(df_result)

    # TODO: Log not found image
    # if df_result.is_empty():
    #     new_path = f"/home/hattajr/lab/ikmimart/.trash/test_images/{image_id}__not_found.jpg"
    #     os.rename(file_path, new_path)

    context = {"request": request, "products": products}
    response = templates.TemplateResponse(
        "index.html", context=context, block_names=["result_list"]
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_EXPIRY_MINUTES * 60,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return response

@app.get("/catalog", response_class=HTMLResponse)
def get_catalog(request: Request, response: Response, db: Session = Depends(get_local_db)):
    products = search_product_by_keyword("CATALOG", db).sort("name")
    context = {"request": request, "products": products.to_dicts()}
    response = templates.TemplateResponse(
        "index.html", context=context
    )
    return response

@app.get("/contact", response_class=HTMLResponse)
def contact(request: Request, response: Response):
    account_info_1 = {
        "bank": "HANA BANK",
        "name": "APRILIYANTO FADA",
        "account_number": "3989 1053 191007",
        "phone": "010 5608 2996",
    }
    account_info_2 = {
        "name": "HATTA",
        "phone": "010 3854 6810",
    }

    context = {"request": request, "account_info_1": account_info_1, "account_info_2": account_info_2}
    response = templates.TemplateResponse(
        name="contact_modal.html", context=context
    )
    return response