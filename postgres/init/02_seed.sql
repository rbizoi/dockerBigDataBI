INSERT INTO customers(customer_id, first_name, last_name, country, segment)
VALUES
  (1,'Alice','Martin','FR','Retail'),
  (2,'Benoit','Durand','FR','SMB'),
  (3,'Clara','Bernard','BE','Enterprise'),
  (4,'David','Muller','DE','Retail'),
  (5,'Eva','Rossi','IT','SMB')
ON CONFLICT DO NOTHING;

INSERT INTO products(product_id, product_name, category, unit_price)
VALUES
  (101,'Laptop Pro','Computers',1299.00),
  (102,'Monitor 27','Displays',349.00),
  (103,'Keyboard','Accessories',79.00),
  (104,'Mouse','Accessories',49.00),
  (105,'Dock USB-C','Accessories',159.00)
ON CONFLICT DO NOTHING;

INSERT INTO orders(order_id, customer_id, order_ts, status)
VALUES
  (1001,1,now()-interval '5 days','PAID'),
  (1002,2,now()-interval '3 days','PAID'),
  (1003,3,now()-interval '1 day','SHIPPED'),
  (1004,1,now()-interval '6 hours','PAID'),
  (1005,5,now()-interval '1 hour','NEW')
ON CONFLICT DO NOTHING;

INSERT INTO order_lines(order_id, product_id, quantity, unit_price)
VALUES
  (1001,101,1,1299.00),
  (1001,103,1,79.00),
  (1002,102,2,349.00),
  (1003,105,4,159.00),
  (1004,104,3,49.00),
  (1005,103,2,79.00)
ON CONFLICT DO NOTHING;
