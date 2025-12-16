from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import datetime
import os 
from werkzeug.utils import secure_filename # For secure file naming

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = 'super_secret_key_for_inventory'
DATABASE = 'inventory.db' 
LOW_STOCK_THRESHOLD = 10 

# File Upload Configuration
UPLOAD_FOLDER = 'static' # Images will be stored here
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} 

def allowed_file(filename):
    """Checks if a file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- DATABASE UTILITIES ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. CREATE TABLES (Including new columns: image_url and is_watched)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            low_stock_threshold INTEGER NOT NULL,
            image_url TEXT,                 
            is_watched INTEGER DEFAULT 0    
        );
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            sale_date TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
    ''')
    
    # --- INSERT INITIAL DATA ---
    try:
        conn.execute('INSERT INTO products (name, price, stock, low_stock_threshold, image_url) VALUES (?, ?, ?, ?, ?)',
                     ('Shampoo', 15.00, 200, 20, 'shampoo.png'))
        conn.execute('INSERT INTO products (name, price, stock, low_stock_threshold, image_url, is_watched) VALUES (?, ?, ?, ?, ?, ?)',
                     ('Water Bottle', 5.00, 500, 20, 'water_bottle.png', 1)) 
        conn.execute('INSERT INTO products (name, price, stock, low_stock_threshold, image_url) VALUES (?, ?, ?, ?, ?)',
                     ('Energy Bar', 2.50, 80, 5, 'energy_bar.png'))
        
        conn.commit()
        print("Initial data inserted successfully!")
    except sqlite3.IntegrityError:
        print("Initial data already present (Skipping insertion).")

    conn.close()

# Initialize the database when the app starts
with app.app_context():
    init_db()

# --- ROUTES & BUSINESS LOGIC ---

@app.route('/')
def index():
    """Renders the main inventory dashboard, fetches products and total value."""
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products ORDER BY stock ASC').fetchall()
    
    # Calculate Total Stock Value (Value = SUM(stock * price))
    total_value = conn.execute('SELECT SUM(stock * price) AS total FROM products').fetchone()['total'] or 0.0

    conn.close()
    
    return render_template('index.html', 
                           products=products, 
                           low_stock_limit=LOW_STOCK_THRESHOLD,
                           total_value=total_value)

@app.route('/add_product', methods=('GET', 'POST'))
def add_product():
    """Handles adding a new product, including file upload logic."""
    if request.method == 'POST':
        # Safely retrieve all fields using .get()
        name = request.form.get('name')
        
        # Default image URL is the online URL, used if no file is uploaded
        image_url = request.form.get('image_url_online', '') 
        
        try:
            price = float(request.form.get('price')) if request.form.get('price') else 0
            stock = int(request.form.get('stock')) if request.form.get('stock') else 0
            threshold = int(request.form.get('threshold')) if request.form.get('threshold') else 1
        except (ValueError, TypeError):
            flash('Price, Stock, and Threshold must be numbers.', 'error')
            return redirect(url_for('add_product'))

        # --- IMAGE UPLOAD LOGIC ---
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename != '' and allowed_file(file.filename):
                # Securely save the file to the static folder
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = filename # Store the secured filename (e.g., 'new_item.png')
            elif file.filename != '' and not allowed_file(file.filename):
                flash('File type not allowed. Please use PNG, JPG, JPEG, or GIF.', 'error')
                return redirect(url_for('add_product'))

        # --- VALIDATION ---
        if not name or price <= 0 or stock < 0 or threshold <= 0:
            flash('All fields must be filled out correctly.', 'error')
            return redirect(url_for('add_product'))

        # --- DATABASE INSERT ---
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO products (name, price, stock, low_stock_threshold, image_url) VALUES (?, ?, ?, ?, ?)',
                         (name, price, stock, threshold, image_url))
            conn.commit()
            flash(f'Product "{name}" added successfully!', 'success')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash(f'Product name "{name}" already exists.', 'error')
        finally:
            conn.close()

    return render_template('add_product.html')

@app.route('/delete/<int:product_id>', methods=('POST',))
def delete_product(product_id):
    """Deletes a product by ID."""
    conn = get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/process_sale', methods=('POST',))
def process_sale():
    """Handles the core business logic: processing a sale and updating inventory."""
    product_id = request.form.get('product_id')
    try:
        quantity = int(request.form.get('quantity'))
        if quantity <= 0:
            flash('Quantity must be a positive number.', 'error')
            return redirect(url_for('index'))
    except (ValueError, TypeError):
        flash('Invalid quantity.', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    try:
        # Start a transaction (Crucial for data integrity)
        conn.execute('BEGIN TRANSACTION')
        
        # 1. Check current stock
        product = conn.execute('SELECT stock FROM products WHERE id = ?', (product_id,)).fetchone()

        if product is None:
            flash('Product not found.', 'error')
            conn.execute('ROLLBACK')
            return redirect(url_for('index'))

        current_stock = product['stock']
        
        if current_stock < quantity:
            flash(f'Sale failed: Only {current_stock} units of stock remaining.', 'error')
            conn.execute('ROLLBACK') # Revert any changes
            return redirect(url_for('index'))

        # 2. Update the stock
        new_stock = current_stock - quantity
        conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product_id))

        # 3. Log the sale 
        sale_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('INSERT INTO sales (product_id, quantity, sale_date) VALUES (?, ?, ?)', 
                     (product_id, quantity, sale_date))

        # Commit the transaction 
        conn.commit()
        flash(f'Sale processed successfully: {quantity} units sold.', 'success')
        
    except Exception as e:
        conn.execute('ROLLBACK')
        flash(f'An error occurred during sale processing: {e}', 'error')
    finally:
        conn.close()
        
    return redirect(url_for('index'))

# --- WATCHLIST TOGGLE API ROUTE ---
@app.route('/toggle_watchlist/<int:product_id>', methods=['POST'])
def toggle_watchlist(product_id):
    """Toggles the is_watched flag for a product using an AJAX request."""
    conn = get_db_connection()
    try:
        current_status = conn.execute('SELECT is_watched FROM products WHERE id = ?', (product_id,)).fetchone()
        
        if current_status is None:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
            
        new_status = 1 if current_status['is_watched'] == 0 else 0
        
        conn.execute('UPDATE products SET is_watched = ? WHERE id = ?', (new_status, product_id))
        conn.commit()
        
        return jsonify({'success': True, 'new_status': new_status, 'message': 'Watchlist status updated.'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# --- DATA VISUALIZATION ROUTE ---
@app.route('/visualization')
def visualization():
    """Calculates and renders business metrics from the sales data."""
    conn = get_db_connection()
    
    # 1. Calculate Total Stock Value
    total_value = conn.execute('SELECT SUM(stock * price) AS total FROM products').fetchone()['total'] or 0.0
    
    # 2. Calculate Total Orders Placed 
    total_orders = conn.execute('SELECT COUNT(id) AS count FROM sales').fetchone()['count']

    # 3. Calculate Top 5 Selling Products (Units Sold)
    top_products = conn.execute('''
        SELECT 
            p.name, 
            SUM(s.quantity) AS units_sold 
        FROM sales s
        JOIN products p ON s.product_id = p.id
        GROUP BY p.name
        ORDER BY units_sold DESC
        LIMIT 5
    ''').fetchall()
    
    # 4. Calculate Revenue Metrics (Total Revenue)
    total_revenue = conn.execute('''
        SELECT 
            SUM(s.quantity * p.price) AS revenue
        FROM sales s
        JOIN products p ON s.product_id = p.id
    ''').fetchone()['revenue'] or 0.0

    conn.close()
    
    return render_template('visualization.html', 
                           total_value=total_value, 
                           top_products=top_products,
                           total_orders=total_orders,
                           total_revenue=total_revenue)

if __name__ == '__main__':
    app.run(debug=True)