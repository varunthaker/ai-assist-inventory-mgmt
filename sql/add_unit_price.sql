-- Adds a unit price (EUR) to products, so order value = quantity x unit_price
-- can be checked against the approval limits in the procurement policy.
-- Run in the Supabase SQL editor. Safe to re-run.

ALTER TABLE products ADD COLUMN IF NOT EXISTS unit_price NUMERIC(10, 2);

-- Sample prices (EUR per unit of the product's `unit`).
UPDATE products SET unit_price = 2.50  WHERE sku = 'PKG-TAPE-001'; -- Packing Tape 48mm, per roll
UPDATE products SET unit_price = 1.20  WHERE sku = 'PKG-BOX-002';  -- Corrugated Box Medium, per piece
UPDATE products SET unit_price = 12.50 WHERE sku = 'PAL-STD-001';  -- Standard Euro Pallet, per piece
UPDATE products SET unit_price = 4.80  WHERE sku = 'SAF-GLV-001';  -- Safety Gloves L, per pair
UPDATE products SET unit_price = 6.90  WHERE sku = 'SAF-VST-001';  -- Hi-Vis Safety Vest, per piece

-- Check: every product should now have a price.
SELECT sku, name, unit, unit_price FROM products ORDER BY sku;
