import datetime
import sys
import uuid
from collections import deque
from typing import Any

import shutil
from tempfile import NamedTemporaryFile
import polars as pl
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks
from loguru import logger
from sqlalchemy.orm import Session
from fastapi.middleware.gzip import GZipMiddleware


from db.database import get_local_db
from inference import get_prediction_result

load_dotenv()

logger.remove()
logger.add(sys.stderr, level="DEBUG")

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


def query_products(query: str, db: Session) -> pl.DataFrame:
    df = pl.read_database(query=query, connection=db)
    logger.debug(df)
    if not df.is_empty():
        df = df.with_columns(
            image_url=pl.when(pl.col("barcode").is_not_null())
            .then(
                pl.concat_str(
                    [pl.lit(PRODUCT_IMAGE_URL), pl.col("barcode")], separator="/"
                )
            )
            .otherwise(None)
        ).with_columns(
            image_url=pl.when(pl.col("image_url").is_not_null())
            .then(
                pl.concat_str(
                    [pl.col("image_url"), pl.lit(IMAGE_FORMAT)], separator="."
                )
            )
            .otherwise(None)
        )
        return df
    return pl.DataFrame()


def search_product_by_keyword(keyword: str, db: Session) -> pl.DataFrame:
    q = f"SELECT id, barcode, name, price, unit FROM products WHERE name ILIKE '%{keyword}%' OR keyword ILIKE '%{keyword}%'"
    return query_products(q, db)


def search_product_by_id(id: int | list[int], db: Session) -> pl.DataFrame:
    if isinstance(id, list):
        id = ",".join([str(i) for i in id])
        query = f"SELECT * FROM products WHERE id IN ({id})"
    else:
        id = str(id)
        query = f"SELECT * FROM products WHERE id = {id}"
    return query_products(query, db)


@app.get("/", response_class=HTMLResponse)
def root(request: Request, response: Response, db: Session = Depends(get_local_db)):
    if not request.headers.get("HX-Request"):
        response = templates.TemplateResponse(request=request, name="index.html")
        response.delete_cookie(SESSION_COOKIE_NAME)
        return response

    context = {"request": request}
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
        response = templates.TemplateResponse(request=request, name="index.html")
        return response

    session_id, response = get_or_create_session(request=request, response=response)
    url = request.headers.get("HX-Current-URL").split("/")[-1]
    if url == "cart":
        logger.debug(session_data[session_id])
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

    keyword = q
    products = search_product_by_keyword(keyword, db)
    session_data[session_id]["search_history"].append(keyword)
    logger.debug(session_data[session_id]["search_history"])
    logger.debug(f"{session_id}: {session_data[session_id]}")

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
    df_cart = get_cart(session_id, db=db)
    logger.debug(df_cart)

    context = dict(
        cart=df_cart.to_dicts(),
        total_price=f"{df_cart['total_price'].sum():,.0f}",
        total_items=df_cart["qty"].sum(),
        last_query=session_data[session_id]["search_history"][-1],
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
    response =  response(status_code=204)
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


# @app.get("/update-database", response_class=HTMLResponse)
# async def update_database(request: Request, response:Response):
#     sqlite_DB = LOCAL_DATABASE_URL
#     q = f"SELECT * FROM products_new"
#     df = pl.read_database_uri(query=q, uri=MASTER_DATABASE_URL)
#     df.write_database(
#         table_name="products_new",
#         connection=sqlite_DB,
#         if_table_exists="replace",
#         engine="sqlalchemy"
#     )
#     context = {
#         "request": request,
#     }
#     return templates.TemplateResponse("index.html", context=context, block_name="update_database")


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
        # TODO: change this
        q = "aya"
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

    # image_id = str(uuid.uuid4())
    # file_path = f"./{image_id}.jpg"

    with NamedTemporaryFile(delete=True, suffix=".jpg") as temp_file:
        file_path = temp_file.name
        logger.debug(file_path)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            df_prediction = get_prediction_result(file_path)
            logger.debug(df_prediction)

        # with open(file_path, "wb") as f:
        #     shutil.copyfileobj(file.file, f)

    context = {"request": request, "products": {}}
    if df_prediction is None:
        logger.info("No prediction found None")
        return templates.TemplateResponse("index.html", context=context)

    if df_prediction.is_empty():
        logger.info("No prediction found Empty")
        return templates.TemplateResponse("index.html", context=context)

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
                break
        if found:
            continue

    logger.debug(session_data[session_id]["search_history"])
    logger.debug(f"{session_id}: {session_data[session_id]}")

    # IF NOT FOUND, SPLIT ALL THE KEYWORD FOR EACH WORD AND START SEAARCH AGAIN

    df_result = pl.concat(dfs_queried, how="vertical_relaxed")
    products = df_result.to_dicts()
    logger.debug(df_result)
    # df_result = pl.DataFrame()
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
