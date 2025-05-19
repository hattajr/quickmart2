import sys
import uuid
import os

import polars as pl
from fastapi import FastAPI, File, Request, UploadFile, Query, Form, Depends, Response
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
import shutil
from dotenv import load_dotenv
from aiocache import SimpleMemoryCache
from uuid import uuid4
import asyncio
from jinja2_fragments.fastapi import Jinja2Blocks
import datetime

    


from db.database import get_local_db
from inference import get_prediction_result
from sqlalchemy.orm import Session

load_dotenv()

logger.remove()
logger.add(sys.stderr, level="DEBUG")

app = FastAPI()
cache = SimpleMemoryCache()

PRODUCT_IMAGE_URL = os.getenv("PRODUCT_IMAGE_URL")
IMAGE_FORMAT = "png"

app.mount("/static", StaticFiles(directory="static"), name="static")
# app.mount("/images", StaticFiles(directory="images"), name="images")
# templates = Jinja2Templates(directory="templates")
templates = Jinja2Blocks(directory="templates")


# Data structure to hold user carts
# {session_id: {product_id: qty}}
user_carts = {}


def get_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)

def query_products(query:str, db:Session) -> pl.DataFrame:
    df = pl.read_database(query=query, connection=db)
    logger.debug(df)
    if not df.is_empty():
        df = (
            df
            .with_columns(
                image_url = pl.when(pl.col("barcode").is_not_null())
                .then(pl.concat_str([
                    pl.lit(PRODUCT_IMAGE_URL),
                    pl.col("barcode")
                ], separator="/"))
                .otherwise(None)
            )
            .with_columns(
                image_url = pl.when(pl.col("image_url").is_not_null())
                .then(pl.concat_str([
                    pl.col("image_url"),
                    pl.lit(IMAGE_FORMAT)
                ], separator="."))
                .otherwise(None)
            )
        )
        return df
    return pl.DataFrame()

def search_product_by_keyword(keyword: str, db:Session) -> pl.DataFrame:    
    q = f"SELECT * FROM products_new WHERE name LIKE '%{keyword}%'"
    return query_products(q, db)

def search_product_by_id(id: int | list[int], db:Session) -> pl.DataFrame:
    if isinstance(id, list):
        id = ",".join([str(i) for i in id])
        query = f"SELECT * FROM products_new WHERE id IN ({id})"
    else:
        id = str(id)
        query = f"SELECT * FROM products_new WHERE id = {id}"
    return query_products(query, db)

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db:Session=Depends(get_local_db)):
    # if not request.headers.get('HX-Request'):
    #     user_carts.clear()
    #     return templates.TemplateResponse("index.html", {"request": request})
    session_id = request.cookies.get("session_id")
    if session_id and session_id in user_carts:
        logger.debug(user_carts[session_id])
        df_cart = get_cart(session_id, db=db)
        total_items = df_cart["qty"].sum()
        logger.debug(total_items)
    else:
        total_items = 0
    context = {
        "request": request,
        "last_query": user_carts[session_id].get("last_query") if session_id and session_id in user_carts else None,
        "products": [],
        "total_items": total_items,
    }


    return templates.TemplateResponse(request=request, name="index.html", context=context)

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q:str = Query(...), db:Session=Depends(get_local_db)):
    if not request.headers.get('HX-Request'):
        return RedirectResponse(url="/")

    keyword = q
    logger.debug(keyword)
    if not keyword:
        return templates.TemplateResponse("result_fragment.html", {"request": request, "products": []})

    products = search_product_by_keyword(keyword, db)

    session_id = request.cookies.get("session_id")
    total_items = 0
    if session_id and session_id in user_carts:
        logger.debug(session_id)
        df_cart = get_cart(session_id, db=db)
        total_items = df_cart["qty"].sum()
        context = {
                "request": request,
                "last_query": keyword,
                "products": products.to_dicts(),
                "total_items": total_items,
            }
        return templates.TemplateResponse(
            "index.html",
            context=context
        )


    context = {
            "request": request,
            "query": keyword,
            "products": products.to_dicts(),
        }
    return templates.TemplateResponse(
        "result_fragment.html",
        context=context
    )


@app.post("/search/add/{query}", response_class=HTMLResponse)
async def add_to_cart(request: Request, query:str,  product_id: int=Query(...), db:Session=Depends(get_local_db)):
    session_id = request.cookies.get("session_id")
    logger.debug(session_id)
    if not session_id:
        session_id = str(uuid4())
        user_carts[session_id] = {}
    if session_id not in user_carts:
        user_carts[session_id] = {"items": {}}
    if product_id not in user_carts[session_id]["items"]:
        user_carts[session_id]["items"][product_id] = {"qty": 0}
    user_carts[session_id]["items"][product_id]["qty"] += 1
    user_carts[session_id]["items"][product_id]["updated_at"] = get_now()
    user_carts[session_id]["last_query"]=query
    logger.debug(user_carts)

    df_cart = get_cart(session_id, db=db)

    context={
        "session_id": session_id,
        "total_items": df_cart["qty"].sum(),
    }
    logger.debug(context)
    response =  templates.TemplateResponse(
        request = request,
        name="cart_count_badge.html",
        context=context,
        # block_name="cart_icon"
    )
    response.set_cookie(key="session_id", value=session_id)
    return response

@app.post("/cart/remove/{product_id}", response_class=HTMLResponse)
async def remove_from_cart(request: Request, product_id: int, qty: int = 1):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in user_carts:
        if product_id in user_carts[session_id]["items"]:
            user_carts[session_id]["items"][product_id]["qty"] -= qty
            if user_carts[session_id]["items"][product_id]["qty"] <= 0:
                del user_carts[session_id]["items"][product_id]
    return

@app.post("/cart/item/{product_id}", response_class=HTMLResponse)
async def cart_item_change_count(request: Request, product_id: int, action: str = Query(...), db:Session=Depends(get_local_db)):
    session_id = request.cookies.get("session_id")
    def _updated_data():
        logger.info("Get data from cart")
        df_cart = get_cart(session_id, db=db)
        df_product = df_cart.filter(pl.col("id") == product_id)
        context={
            "session_id": session_id,
            "product": df_product.to_dicts()[0] if not df_product.is_empty() else None,
            "total_price": df_cart["total_price"].sum(),
            "total_items": df_cart["qty"].sum()
        }
        return templates.TemplateResponse(
            request = request,
            name="cart/partials/item_count_change.html",
            context=context,
        )
    if session_id and session_id in user_carts:
        if product_id in user_carts[session_id]["items"]:
            if action == "increase":
                user_carts[session_id]["items"][product_id]["qty"] += 1
                return _updated_data()
            elif action == "decrease":
                if user_carts[session_id]["items"][product_id]["qty"] <= 1:
                    user_carts[session_id]["items"][product_id]["qty"] = 1
                    return _updated_data()
                else:
                    user_carts[session_id]["items"][product_id]["qty"] -= 1
                    return _updated_data()
            elif action == "remove":
                del user_carts[session_id]["items"][product_id]
                logger.info("Remove item from cart")
                df_cart = get_cart(session_id, db=db)
                if df_cart.is_empty():
                    return templates.TemplateResponse(
                        request = request,
                        name="cart/partials/cart.html",
                    )
                context={
                    "cart": df_cart.to_dicts(),
                    "session_id": session_id,
                    "total_price": df_cart["total_price"].sum(),
                    "total_items": df_cart["qty"].sum()
                }
                return templates.TemplateResponse(
                    request = request,
                    name="cart/partials/cart.html",
                    context=context,
                )

@app.post("/cart/clear", response_class=HTMLResponse)
async def clear_cart(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in user_carts:
        del user_carts[session_id]
    return templates.TemplateResponse(
        request = request,
        name="cart/partials/cart.html",
    )

@app.get("/cart", response_class=HTMLResponse)
async def get_cart(request: Request, db:Session=Depends(get_local_db)):
    session_id = request.cookies.get("session_id")
    logger.debug(user_carts[session_id])
    # if not session_id:
    #     session_id = str(uuid4())
    #     user_carts[session_id] = {}
    # if session_id not in user_carts:
    #     user_carts[session_id] = {}
    # if session_id in user_carts:
    #     user_carts[session_id] = user_carts[session_id]
    # else:
    #     user_carts[session_id] = {}

    df_cart = get_cart(session_id, db=db)
    logger.debug(df_cart)

    context = dict(
        cart=df_cart.to_dicts(),
        total_price=df_cart["total_price"].sum(),
        total_items=df_cart["qty"].sum(),
        last_query=user_carts[session_id].get("last_query"),
    )
    if request.headers.get('HX-Request'):
        return templates.TemplateResponse(
            request=request,
            name="cart/partials/cart.html",
            context=context
        )
    return templates.TemplateResponse(
        request=request,
        name="cart/cart.html",
        context=context
    )

def get_cart(session_id:str, db:Session) -> pl.DataFrame:
    logger.debug(user_carts[session_id])
    if not user_carts.get(session_id):
        return pl.DataFrame()

    cart = []
    for product_id, product in user_carts[session_id]["items"].items():
        cart.append(
            dict(
                id = product_id,
                qty = product["qty"],
                updated_at = product["updated_at"],
            )
        )
    
    df_cart = pl.DataFrame(cart)
    df_product = search_product_by_id(list(user_carts[session_id]["items"].keys()), db=db)
    logger.debug(df_product)
    if df_product.is_empty():
        return pl.DataFrame()

    df_result = (
        df_cart
        .join(
            df_product,
            left_on="id",
            right_on="id",
        )
        .with_columns(
            total_price = pl.col("qty") * pl.col("price")
        )
        .sort("updated_at", descending=True)
    )
    return df_result


@app.get("/cart/checkout", response_class=HTMLResponse)
async def checkout(request: Request, db:Session=Depends(get_local_db)):
    session_id = request.cookies.get("session_id")
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
        request=request,
        name="cart/checkout_modal.html",
        context=context
    )
@app.get("/cart/checkout/confirm", response_class=HTMLResponse)
async def checkout_confirm(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in user_carts:
        # Clear the cart data
        del user_carts[session_id]
        # Expire the session cookie
        response.set_cookie(key="session_id", value="", expires=0, max_age=0)
        logger.debug(user_carts)
    
    # Create a response with cache-control headers to prevent back navigation
    redirect = RedirectResponse(url="/", status_code=303)
    # Add headers to prevent caching
    redirect.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0"
    redirect.headers["Pragma"] = "no-cache"
    redirect.headers["Expires"] = "0"
    return redirect



@app.post("/upload", response_class=HTMLResponse)
async def upload_image(request: Request, file: UploadFile = File(...), db:Session=Depends(get_local_db)):

    image_id = str(uuid.uuid4())
    file_path = f"/home/hattajr/lab/ikmimart/.trash/test_images/{image_id}.jpg"

    file_paths = [
        # "/home/hattajr/lab/ikmimart/.trash/belinis2.jpg"
        # "/home/hattajr/lab/ikmimart/.trash/many.jpg",
        # "/home/hattajr/lab/ikmimart/.trash/many1.jpg",
        "/home/hattajr/lab/ikmimart/.trash/many2.jpg",
    ]
    file_path = file_paths[uuid.uuid4().int % len(file_paths)]

    logger.debug(file_path)
    # with open(file_path, "wb") as f:
    #     shutil.copyfileobj(file.file, f)
    

    context = {
            "request": request,
            "products": {}
        }
    df_prediction = get_prediction_result(file_path)
    if df_prediction is None:
        logger.info("No prediction found None")
        return templates.TemplateResponse(
            "result_fragment.html",
            context=context
        )

    if df_prediction.is_empty():
        logger.info("No prediction found Empty")
        return templates.TemplateResponse(
            "result_fragment.html",
            context=context
        )

    dfs_queried = []
    for product in df_prediction.to_dicts():
        logger.debug(product)
        keywords = product.get("keywords")
        found = False
        for keyword in keywords:
            df = search_product_by_keyword(keyword, db=db)
            logger.debug(df)
            if not df.is_empty():
                dfs_queried.append(df)
                found = True
                break
        if found:
            continue

    # IF NOT FOUND, SPLIT ALL THE KEYWORD FOR EACH WORD AND START SEAARCH AGAIN

    df_result = pl.concat(dfs_queried, how="vertical_relaxed")
    # df_result = pl.DataFrame()
    # if df_result.is_empty():
    #     new_path = f"/home/hattajr/lab/ikmimart/.trash/test_images/{image_id}__not_found.jpg"
    #     os.rename(file_path, new_path)

    logger.debug(df_result)
    products = df_result.to_dicts()
    context = {
            "request": request,
            "products": products,
        }
    return templates.TemplateResponse(
        "result_fragment.html",
        context=context
    )
