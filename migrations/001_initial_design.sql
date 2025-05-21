CREATE TABLE "products" (
	"id" SERIAL NOT NULL,
	"barcode" VARCHAR(255),
	"name" VARCHAR(255) NOT NULL UNIQUE,
	"brand" VARCHAR(255),
	"price" INTEGER NOT NULL DEFAULT 1,
	"unit" VARCHAR(20),
	"stock" INTEGER DEFAULT 0,
	"description" VARCHAR(255),
	"category_id" INTEGER,
	"keyword" VARCHAR(255),
	"image_url" TEXT,
	"created_at" TIMESTAMPTZ,
	"updated_at" TIMESTAMPTZ,
	PRIMARY KEY("id")
);
CREATE INDEX "idx_products_category_id"
ON "products" ("category_id");

CREATE INDEX "products_index_1"
ON "products" ("name");

CREATE INDEX "products_index_2"
ON "products" ("barcode");

CREATE TABLE "categories" (
	"id" SERIAL NOT NULL,
	"name" VARCHAR(255) NOT NULL UNIQUE,
	"parent_id" INTEGER,
	PRIMARY KEY("id")
);
CREATE INDEX "categories_index_0"
ON "categories" ("name");

CREATE TABLE "sessions" (
	"id" UUID NOT NULL,
	"created_at" TIMESTAMPTZ,
	PRIMARY KEY("id")
);

CREATE TABLE "orders" (
	"id" SERIAL NOT NULL,
	"session_id" UUID NOT NULL,
	"created_at" TIMESTAMPTZ NOT NULL,
	PRIMARY KEY("id")
);
CREATE INDEX "orders_index_0"
ON "orders" ("created_at");

CREATE TABLE "order_items" (
	"id" SERIAL NOT NULL,
	"order_id" INTEGER NOT NULL,
	"product_id" INTEGER,
	"quantity" INTEGER,
	"price_at_purchase" INTEGER,
	PRIMARY KEY("id")
);
CREATE INDEX "idx_order_items_product_id"
ON "order_items" ("product_id");

CREATE TABLE "events" (
	"id" SERIAL NOT NULL,
	"session_id" UUID NOT NULL,
	"event_code" INTEGER NOT NULL,
	"created_at" TIMESTAMPTZ NOT NULL,
	PRIMARY KEY("id")
);
CREATE INDEX "idx_events_event_type"
ON "events" ("event_code");

CREATE TABLE "event_code" (
	"code" INTEGER NOT NULL,
	"name" VARCHAR(30) NOT NULL,
	PRIMARY KEY("code")
);
CREATE INDEX "event_code_index_0"
ON "event_code" ("code");
