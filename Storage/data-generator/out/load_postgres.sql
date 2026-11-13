-- Chargement des CSV (psql, depuis ce dossier). Base vide ou après TRUNCATE.
BEGIN;
\copy inventory.warehouse (id, name, city, capacity_units) FROM 'inventory.warehouse.csv' CSV HEADER
\copy orders.customers (id, name, email, auth_user_id, created_at) FROM 'orders.customers.csv' CSV HEADER
\copy orders.orders (id, customer_id, status, total_cents, currency, created_at, updated_at) FROM 'orders.orders.csv' CSV HEADER
\copy orders.order_items (id, order_id, order_created_at, product_id, product_name, quantity, unit_price_cents) FROM 'orders.order_items.csv' CSV HEADER
\copy payments.payments (id, order_id, amount_cents, currency, status, failure_reason, idempotency_key, created_at, updated_at) FROM 'payments.payments.csv' CSV HEADER
\copy inventory.stock (product_id, warehouse_id, quantity, reserved_quantity, reorder_threshold) FROM 'inventory.stock.csv' CSV HEADER
\copy inventory.reservations (id, order_id, product_id, warehouse_id, quantity, status, created_at, updated_at, expires_at) FROM 'inventory.reservations.csv' CSV HEADER
SELECT setval('orders.orders_id_seq', COALESCE((SELECT MAX(id) FROM orders.orders), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('orders.customers', 'id'), COALESCE((SELECT MAX(id) FROM orders.customers), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('orders.order_items', 'id'), COALESCE((SELECT MAX(id) FROM orders.order_items), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('payments.payments', 'id'), COALESCE((SELECT MAX(id) FROM payments.payments), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('inventory.warehouse', 'id'), COALESCE((SELECT MAX(id) FROM inventory.warehouse), 0) + 1, false);
SELECT setval(pg_get_serial_sequence('inventory.reservations', 'id'), COALESCE((SELECT MAX(id) FROM inventory.reservations), 0) + 1, false);
ANALYZE;
COMMIT;
