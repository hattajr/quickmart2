import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, List

# --- Application Setup ---
app = FastAPI()

# Mount static files (optional, if you have local images/css)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# --- Test Data (NO ORM - using in-memory dictionaries) ---
PRODUCTS = {
    "prod1": {"id": "prod1", "name": "Wireless Mouse", "price": 29.99, "description": "Ergonomic wireless mouse", "image_url": "https://via.placeholder.com/300x200/777/fff?text=Wireless+Mouse"},
    "prod2": {"id": "prod2", "name": "Mechanical Keyboard", "price": 79.99, "description": "RGB Backlit Keyboard", "image_url": "https://via.placeholder.com/300x200/555/fff?text=Mech+Keyboard"},
    "prod3": {"id": "prod3", "name": "USB-C Hub", "price": 45.50, "description": "7-in-1 USB-C Hub Adapter", "image_url": None}, # No image example
    "prod4": {"id": "prod4", "name": "Monitor Stand", "price": 35.00, "description": "Adjustable height stand", "image_url": "https://via.placeholder.com/300x200/999/fff?text=Monitor+Stand"},
    "prod5": {"id": "prod5", "name": "Webcam HD 1080p", "price": 55.00, "description": "Webcam with privacy shutter", "image_url": "https://via.placeholder.com/300x200/444/fff?text=Webcam+HD"},
    "prod6": {"id": "prod6", "name": "Laptop Sleeve", "price": 19.99, "description": "13-inch Neoprene Sleeve", "image_url": "https://via.placeholder.com/300x200/666/fff?text=Laptop+Sleeve"},
}

# In-memory cart storage (for demonstration purposes ONLY)
# In a real app, this should be tied to user sessions (e.g., using cookies/session middleware)
CART: Dict[str, int] = {"prod1": 1, "prod3": 2} # Start with some items for testing


# --- Helper Functions ---
def get_all_products() -> List[Dict]:
    return list(PRODUCTS.values())

def search_products(query: str) -> List[Dict]:
    if not query:
        return get_all_products()
    query = query.lower()
    return [
        p for p in PRODUCTS.values()
        if query in p['name'].lower() or (p['description'] and query in p['description'].lower())
    ]

def get_cart_details() -> (List[Dict], float):
    """ Returns a list of cart item details and the total price """
    cart_items = []
    total = 0.0
    for product_id, quantity in CART.items():
        product = PRODUCTS.get(product_id)
        if product:
            item_total = product['price'] * quantity
            cart_items.append({
                "product": product,
                "quantity": quantity,
                "item_total": item_total
            })
            total += item_total
    return cart_items, total

def get_cart_item_count() -> int:
    """ Returns the total number of individual items in the cart """
    return sum(CART.values())


# --- Routes ---

# Product Listing / Home Page
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    products = get_all_products()
    cart_item_count = get_cart_item_count()
    return templates.TemplateResponse("products/products.html", {
        "request": request,
        "products": products,
        "cart_item_count": cart_item_count, # Pass initial count
        "search_query": ""
    })

# Product Search (HTMX)
@app.get("/products/search", response_class=HTMLResponse)
async def search_products_htmx(request: Request, query: Optional[str] = ""):
    products = search_products(query)
    # Return only the product list partial
    return templates.TemplateResponse("products/_product_list.html", {
        "request": request,
        "products": products
        # No need to pass cart_item_count here as it's not used in the partial
    })


# Shopping Cart Page
@app.get("/cart", response_class=HTMLResponse)
async def view_cart(request: Request):
    cart_items, cart_total = get_cart_details()
    cart_item_count = get_cart_item_count()
    return templates.TemplateResponse("cart/cart.html", {
        "request": request,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_item_count": cart_item_count
    })

# Add Item to Cart (HTMX)
@app.post("/cart/add/{product_id}", response_class=HTMLResponse)
async def add_to_cart(request: Request, product_id: str):
    if product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="Product not found")

    current_quantity = CART.get(product_id, 0)
    CART[product_id] = current_quantity + 1

    # Return the updated cart count badge HTML fragment
    # This replaces the target specified in the button's hx-target
    new_count = get_cart_item_count()
    return HTMLResponse(f"""
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-4 w-4 bg-indigo-500 text-white text-xs items-center justify-center">
            {new_count}
        </span>
    """)

# Update Cart Item Quantity (HTMX)
@app.post("/cart/update/{product_id}", response_class=HTMLResponse)
async def update_cart_item(request: Request, product_id: str, action: str = Form(...)):
    if product_id not in CART:
        raise HTTPException(status_code=404, detail="Item not in cart")

    current_quantity = CART[product_id]

    if action == "increase":
        CART[product_id] = current_quantity + 1
    elif action == "decrease":
        if current_quantity > 1:
            CART[product_id] = current_quantity - 1
        else:
            # If decreasing quantity to 0, remove the item
            del CART[product_id]
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Re-render the entire cart details section as requested by hx-target="#cart-details"
    cart_items, cart_total = get_cart_details()
    cart_item_count = get_cart_item_count() # Need this for the base template context if we were rendering the full page
                                            # For just the cart details partial, it's not strictly needed in the context
                                            # unless cart.html itself expects it. Let's be safe.

    # We need to simulate rendering the block inside cart.html
    # A cleaner way might be a dedicated partial template for #cart-details content
    # For simplicity here, we re-render cart.html but *only* return the #cart-details block
    # NOTE: This is inefficient. A dedicated partial or OOB swaps would be better.
    # Let's render the full cart template and assume the browser handles the swap correctly.
    return templates.TemplateResponse("cart/cart.html", {
        "request": request,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_item_count": cart_item_count # Need for base context when rendering full page
    }, headers={"HX-Trigger": "cartUpdate"}) # Also trigger global event


# Remove Item from Cart (HTMX)
@app.post("/cart/remove/{product_id}", response_class=HTMLResponse)
async def remove_from_cart(request: Request, product_id: str):
    if product_id not in CART:
        # Item might already be removed, just render the current state
        pass
    else:
        del CART[product_id]

    # Re-render the entire cart details section
    cart_items, cart_total = get_cart_details()
    cart_item_count = get_cart_item_count()

    # Render the full cart page/template again, HTMX will swap #cart-details
    return templates.TemplateResponse("cart/cart.html", {
        "request": request,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_item_count": cart_item_count
    }, headers={"HX-Trigger": "cartUpdate"}) # Trigger global event

# Get Cart Count (HTMX - for header badge)
@app.get("/cart/count", response_class=HTMLResponse)
async def get_cart_count_htmx(request: Request):
    # This endpoint is triggered by the cart icon in the header
    # It returns the HTML fragment for the badge count
    count = get_cart_item_count()
    # Check if cart is empty to potentially hide the badge or show 0
    if count == 0:
         # Return an empty span or styled '0' - let's return 0 styled
         return HTMLResponse(f"""
             <span class="relative inline-flex rounded-full h-4 w-4 bg-gray-400 text-white text-xs items-center justify-center">
                 0
             </span>
         """)
    else:
        return HTMLResponse(f"""
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-4 w-4 bg-indigo-500 text-white text-xs items-center justify-center">
                {count}
            </span>
        """)


# --- Run the App ---
if __name__ == "__main__":
    # Use host="0.0.0.0" to make it accessible on your network
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)