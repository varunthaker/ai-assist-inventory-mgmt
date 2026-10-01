-- AI Warehouse Inventory Assistant — database schema
-- Run in the Supabase SQL editor. Safe to re-run: uses IF NOT EXISTS.

-- Suppliers table
CREATE TABLE IF NOT EXISTS suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    lead_time_days INTEGER,
    min_order_qty INTEGER,
    contact_email TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    quantity INTEGER NOT NULL DEFAULT 0,
    reorder_threshold INTEGER NOT NULL DEFAULT 0,
    supplier_id UUID REFERENCES suppliers(id),
    unit TEXT DEFAULT 'pcs',
    unit_price NUMERIC(10, 2),           -- EUR per unit; see sql/add_unit_price.sql
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Purchase orders table
CREATE TABLE IF NOT EXISTS purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku TEXT REFERENCES products(sku),
    quantity INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
