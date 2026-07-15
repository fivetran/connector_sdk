# Setup Guide for Snowflake

This guide provides the necessary steps to set up your Snowflake environment before running the connector example.

## Prerequisites
- A Snowflake account with appropriate privileges
- Snowflake credentials (`username`, `password` and `account`)
- Python with the `snowflake-connector-python` package installed

## Setting up Snowflake environment

1. **Create a Database and Schema**:
   ```sql
   CREATE DATABASE IF NOT EXISTS <DATABASE_NAME>;
   CREATE SCHEMA IF NOT EXISTS <SCHEMA_NAME>;
   ```
   The `<DATABASE_NAME>` and `<SCHEMA_NAME>` should match the values in your `configuration.json` file.
2. **Create Tables**:

The tables should follow the following conditions:
- Tables should have a created_at timestamp column.
- The tables should have name as defined in the configuration file.
- The tables can be defined with the following SQL commands:

    ```sql
    -- Create PRODUCTS table
    CREATE OR REPLACE TABLE PRODUCTS (
        product_id INT PRIMARY KEY,
        product_code VARCHAR(10),
        product_name VARCHAR(100),
        price FLOAT,
        in_stock BOOLEAN,
        description VARCHAR(255),
        weight FLOAT,
        created_at DATE DEFAULT CURRENT_DATE()
    );
    
    -- Create ORDERS table
    CREATE OR REPLACE TABLE ORDERS (
        order_id VARCHAR(20) PRIMARY KEY,
        customer_id INT,
        order_date DATE,
        product_id INT,
        quantity INT,
        unit_price FLOAT,
        amount FLOAT,
        payment_method VARCHAR(50),
        status VARCHAR(20),
        street_address VARCHAR(100),
        city VARCHAR(50),
        state VARCHAR(2),
        zip VARCHAR(10),
        discount_applied FLOAT,
        created_at DATE DEFAULT CURRENT_DATE()
    );
    ```
3. **Insert Sample Data**:
   You can insert sample data into the tables to test the connector. Here’s an example for each table:
    
    ```sql
    -- Insert data into PRODUCTS table
    INSERT INTO PRODUCTS (product_id, product_code, product_name, price, in_stock, description, weight)
    VALUES
        (101, 'LP01', 'Laptop Pro', 1299.99, TRUE, 'High-performance laptop', 2.5),
        (102, 'SW01', 'Smart Watch', 249.50, TRUE, 'Fitness tracking smart watch', 0.3),
        (103, 'OC01', 'Office Chair', 189.95, FALSE, 'Ergonomic office chair', 12.8);
    
    -- Insert data into ORDERS table
    INSERT INTO ORDERS (order_id, customer_id, order_date, product_id, quantity, unit_price, amount, payment_method, status, street_address, city, state, zip, discount_applied)
    VALUES
        ('ord-45678-a', 1, '2023-08-15', 101, 1, 1299.99, 1299.99, 'Credit Card', 'Completed', '123 Main St', 'Austin', 'TX', '78701', 10.00),
        ('ord-45678-b', 1, '2023-08-15', 103, 1, 189.95, 189.95, 'Credit Card', 'Completed', '123 Main St', 'Austin', 'TX', '78701', 0.00),
        ('ord-98765', 2, '2023-09-03', 102, 1, 249.50, 249.50, 'PayPal', 'Processing', '456 Park Ave', 'New York', 'NY', '10022', 0.00),
        ('ord-12345-a', 3, '2023-09-10', 101, 1, 1299.99, 1299.99, 'Debit Card', 'Shipped', '789 Beach Rd', 'Miami', 'FL', '33139', 15.50),
        ('ord-12345-b', 3, '2023-09-10', 102, 1, 249.50, 249.50, 'Debit Card', 'Shipped', '789 Beach Rd', 'Miami', 'FL', '33139', 0.00);
    ```

## Additional considerations
- Table names in Snowflake are case-sensitive. Ensure your configuration uses the correct case.
- The connector relies on the created_at timestamp for incremental updates.
- Ensure your Snowflake user has permissions to access the information schema and show primary keys.