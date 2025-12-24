from db_connection import get_connection
from flask import Flask, render_template, request, redirect, url_for, flash
from flask import session,jsonify
from datetime import date
from flask_mysqldb import MySQL
from datetime import date,datetime,timedelta,time
import os
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash

# import razorpay




app = Flask(__name__)
app.secret_key = "secretkey"  # needed for flash messages

# MySQL Config
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'your_password'
app.config['MYSQL_DB'] = 'your_databasename'
mysql = MySQL(app)

# Razorpay test credentials
# RAZORPAY_KEY_ID = "YOUR_TEST_KEY_ID"
# RAZORPAY_KEY_SECRET = "YOUR_TEST_KEY_SECRET"

# client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
# ================= EMAIL CONFIG (for OTP / Password Reset) =================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_Gmail'   # your Gmail
app.config['MAIL_PASSWORD'] = 'password'   # your 16-digit app password

from flask_mail import Mail, Message
mail = Mail(app)

# ======================= Flask-Login Setup =======================
login_manager = LoginManager()  # Create LoginManager object
login_manager.init_app(app)     # Initialize it with the Flask app
login_manager.login_view = 'login'  # Redirect to 'login' page if user not logged in



# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email,address=None):
        self.id = str(id)   # user_id should be string for Flask-Login
        self.name = name
        self.email = email
        self.address = address


# User loader function (Flask-Login uses this to reload user from session)
@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            return User(user['id'], user['name'], user['email'])
        return None
    except Exception as e:
        print("Error loading user:", e)
        return None
    
# ============================forgot password
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if not user:
            flash("Email not found!", "danger")
            return redirect(url_for('forgot_password'))

        import random
        otp = str(random.randint(100000, 999999))

        expiry = datetime.now() + timedelta(minutes=5)

        cursor.execute("UPDATE users SET reset_otp=%s, otp_expiry=%s WHERE email=%s",
                       (otp, expiry, email))
        conn.commit()

        # Send email
        msg = Message("Password Reset OTP",
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[email])
        msg.body = f"Your OTP is {otp}. It is valid for 5 minutes."
        mail.send(msg)

        flash("OTP sent to your email!", "success")
        return redirect(url_for('verify_otp', email=email))

    return render_template('forgot_password.html')

@app.route('/verify_otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    if request.method == 'POST':
        entered_otp = request.form['otp']

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT reset_otp, otp_expiry FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if user['reset_otp'] != entered_otp:
            flash("Invalid OTP!", "danger")
            return redirect(url_for('verify_otp', email=email))

        if datetime.now() > user['otp_expiry']:
            flash("OTP expired!", "danger")
            return redirect(url_for('forgot_password'))

        return redirect(url_for('reset_password', email=email))

    return render_template('verify_otp.html', email=email)

@app.route('/reset_password/<email>', methods=['GET', 'POST'])
def reset_password(email):
    if request.method == 'POST':
        new_pass = request.form['password']
        hashed_pass = generate_password_hash(new_pass)

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users 
            SET password=%s, reset_otp=NULL, otp_expiry=NULL 
            WHERE email=%s
        """, (hashed_pass, email))
        conn.commit()

        flash("Password reset successful!", "success")
        return redirect(url_for('login'))

    return render_template('reset_password.html', email=email)


def get_today_meals():
    today = date.today()
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)# works with mysql.connector or pymysql
        cursor.execute("SELECT * FROM daily_meals WHERE meal_date=%s", (today,))
        meals = cursor.fetchall()
        cursor.close()
        conn.close()

        lunch = next((m for m in meals if m['meal_type']=='Lunch'), None)
        dinner = next((m for m in meals if m['meal_type']=='Dinner'), None)
        #         # Ensure keys exist even if null in DB (helps avoid KeyError in template)
        # if lunch:
        #     lunch.setdefault('lunch_nonveg_name', None)
        #     lunch.setdefault('lunch_nonveg_image', None)

        # if dinner:
        #     dinner.setdefault('dinner_nonveg_name', None)
        #     dinner.setdefault('dinner_nonveg_image', None)
 # Avoid missing keys (important for Jinja)
        for meal in (lunch, dinner):
            if meal:
                for key in ['lunch_nonveg_name', 'lunch_nonveg_image', 'dinner_nonveg_name', 'dinner_nonveg_image']:
                    meal.setdefault(key, None)

        return lunch, dinner
    except Exception as e:
        print("Error fetching today's meals:", e)
        return None, None


@app.route('/')
def homef():  # Landing page before login
    try:
        cur = mysql.connection.cursor()  # tuples, no dictionary=True
        cur.execute("SELECT * FROM plans ORDER BY id")
        plans = cur.fetchall()
        cur.close()
    except Exception as e:
        print("Error fetching plans:", e)
        plans = []
    return render_template('homef.html',plans=plans,
                           logged_in=session.get('user_id') is not None)

# ===================User Dashboard
@app.route('/dashboard')
def user_dashboard():
    if not session.get('user_id'):
        return redirect(url_for('homef'))  # redirect if not logged in
     
    lunch_meal, dinner_meal = get_today_meals()

     # Get all plans
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM plans ORDER BY id")
        plans = cur.fetchall()
        cur.close()
    except Exception as e:
        print("Error fetching plans:", e)
        plans = []
    return render_template('user_dashboard.html',user_name=session.get('user_name'), lunch_meal=lunch_meal, dinner_meal=dinner_meal,plans=plans, now=datetime.now())

# ===================User login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            # Check if user exists
            # cursor.execute("SELECT * FROM users WHERE email=%s AND password=%s", (email, password))
            # user = cursor.fetchone()
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()

            cursor.close()
            conn.close()

           # Check if user exists and password matches
            if user and check_password_hash(user['password'], password):
                login_user(User(user['id'], user['name'], user['email']))
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                return redirect(url_for('user_dashboard'))

            
            # if user:
            #     login_user(User(user['id'], user['name'], user['email']))  # <-- add this
            #     session['user_id'] = user['id']
            #     session['user_name'] = user['name']

            #     return redirect(url_for('user_dashboard'))

                # Later, you can redirect to user dashboard
            else:
                flash("Invalid email or password!", "danger")
                return redirect(url_for('login'))

        except Exception as e:
            print("Login error:", e)
            flash("Something went wrong!", "danger")
            return redirect(url_for('login'))


    # GET → show login page
    return render_template('login.html')

# ------------------- USER LOGOUT -------------------
@app.route('/user_logout')
@login_required
def user_logout():
    logout_user()   # Flask-Login logout

    session.clear()  # clears all session data
    return redirect(url_for('homef'))  # redirect to landing page


# ==========================Admin login page
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # dummy check for admin
        if username == "admin" and password == "admin123":

            
            session['is_admin'] = True

            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid admin credentials!"
    return render_template('admin_login.html')
# Admin login route

# ===========================Admin dashboard
@app.route('/admin_dashboard')
def admin_dashboard():

    lunch_meal, dinner_meal = get_today_meals()

     # Fetch plans from DB
    # conn = get_connection()
    # cursor = conn.cursor(dictionary=True)
    # cursor.execute("SELECT * FROM plans ORDER BY id")
    # plans = cursor.fetchall()
    # cursor.close()
    # conn.close()

    # Fetch plans
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM plans")
    plans = cur.fetchall()  # This returns a list of tuples
    print(cur.fetchall())

    cur.close()

    return render_template('admin_dashboard.html',lunch_meal=lunch_meal, dinner_meal=dinner_meal ,plans=plans,now=datetime.now())
# =============================================


@app.route('/registered_users')
def registered_users():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('registered_users.html', users=users)
    except Exception as e:
        print("Error fetching users:", e)
        return "Something went wrong!"

    # return render_template('admin_dashboard.html')

# ---------------------------update plan
# Update plans (using flask_mysqldb)
@app.route("/update-plan", methods=["POST"])
def update_plan():  # for saving updates
    data = request.get_json()
    try:
        cur = mysql.connection.cursor()  # simple cursor, tuples are fine
        cur.execute("""
            UPDATE plans
            SET plan_type=%s, days=%s, veg_price=%s, nonveg_price=%s, description=%s
            WHERE id=%s
        """, (data['type'], data['days'], data['veg_price'], data['nonveg_price'], data['description'], data['id']))
        mysql.connection.commit()
        cur.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    
    # /update_plan (GET) → To show the table (update_plan.html) with data from DB.
@app.route('/update_plan',methods=["GET"])
def update_plan_page(): # for showing table
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM plans ORDER BY id")
        plans = cur.fetchall()
        cur.close()
        return render_template('update_plan.html', plans=plans)
    except Exception as e:
        return f"Error: {e}"


# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        password = request.form['password']
        hashed_password = generate_password_hash(password)  # <-- hash password

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Insert into MySQL table
            cursor.execute("""
                INSERT INTO users (name, email, phone, address, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, email, phone, address, hashed_password))

            conn.commit()
            cursor.close()
            conn.close()

            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))

        except Exception as e:
            print("Error:", e)
            flash("Something went wrong. Try again!", "danger")
            return redirect(url_for('register'))

    # GET request → just show the form
    return render_template('register.html')

# ========================Meal_update
@app.route('/meal_update', methods=['GET', 'POST'])
def meal_update():
    if request.method == 'POST':
        # Get uploaded files
        meal_date = request.form['meal_date']
        lunch_name = request.form['lunch_name']
        dinner_name = request.form['dinner_name']

        # New optional non-veg fields
        lunch_nonveg_name = request.form.get('lunch_nonveg_name')
        dinner_nonveg_name = request.form.get('dinner_nonveg_name')

        lunch_file = request.files['lunch_image']
        dinner_file = request.files['dinner_image']

        # Optional non-veg image files
        lunch_nonveg_file = request.files.get('lunch_nonveg_image')
        dinner_nonveg_file = request.files.get('dinner_nonveg_image')

        folder = 'static/images/meals'
        if not os.path.exists(folder):
            os.makedirs(folder)

        # Filenames
        lunch_filename = f"lunch_{meal_date}.jpg"
        dinner_filename = f"dinner_{meal_date}.jpg"

        # Save files
        lunch_file.save(os.path.join(folder, lunch_filename))
        dinner_file.save(os.path.join(folder, dinner_filename))

        # Handle optional non-veg uploads (only if provided)
        lunch_nonveg_filename = None
        dinner_nonveg_filename = None

        if lunch_nonveg_file and lunch_nonveg_file.filename:
            lunch_nonveg_filename = f"lunch_nonveg_{meal_date}.jpg"
            lunch_nonveg_file.save(os.path.join(folder, lunch_nonveg_filename))

        if dinner_nonveg_file and dinner_nonveg_file.filename:
            dinner_nonveg_filename = f"dinner_nonveg_{meal_date}.jpg"
            dinner_nonveg_file.save(os.path.join(folder, dinner_nonveg_filename))

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Insert or update lunch
            # cursor.execute("""
            #     INSERT INTO daily_meals (meal_date, meal_type, meal_name, meal_image)
            #     VALUES (%s, 'Lunch', %s, %s)
            #     ON DUPLICATE KEY UPDATE meal_name=%s, meal_image=%s
            # """, (meal_date, lunch_name, lunch_filename, lunch_name, lunch_filename))

            # Insert or update dinner
            # cursor.execute("""
            #     INSERT INTO daily_meals (meal_date, meal_type, meal_name, meal_image)
            #     VALUES (%s, 'Dinner', %s, %s)
            #     ON DUPLICATE KEY UPDATE meal_name=%s, meal_image=%s
            # """, (meal_date, dinner_name, dinner_filename, dinner_name, dinner_filename))
            # Insert or update lunch (includes optional non-veg)
            cursor.execute("""
                INSERT INTO daily_meals 
                    (meal_date, meal_type, meal_name, meal_image, lunch_nonveg_name, lunch_nonveg_image)
                VALUES (%s, 'Lunch', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    meal_name=%s, meal_image=%s, 
                    lunch_nonveg_name=%s, lunch_nonveg_image=%s
            """, (
                meal_date, lunch_name, lunch_filename, lunch_nonveg_name, lunch_nonveg_filename,
                lunch_name, lunch_filename, lunch_nonveg_name, lunch_nonveg_filename
            ))

            # Insert or update dinner (includes optional non-veg)
            cursor.execute("""
                INSERT INTO daily_meals 
                    (meal_date, meal_type, meal_name, meal_image, dinner_nonveg_name, dinner_nonveg_image)
                VALUES (%s, 'Dinner', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    meal_name=%s, meal_image=%s,
                    dinner_nonveg_name=%s, dinner_nonveg_image=%s
            """, (
                meal_date, dinner_name, dinner_filename, dinner_nonveg_name, dinner_nonveg_filename,
                dinner_name, dinner_filename, dinner_nonveg_name, dinner_nonveg_filename
            ))


            conn.commit()
            cursor.close()
            conn.close()

            flash("Meals updated successfully!", "success")
            return redirect(url_for('admin_dashboard'))

        except Exception as e:
            print("Error updating meals:", e)
            flash("Failed to update meals", "danger")
            return redirect(url_for('meal_update'))

    return render_template('meal_update.html')
# ================================================



# --------------------------------
# from datetime import datetime, timedelta, date
  # adjust import according to your project

@app.route('/subscribe', methods=['POST'])
def subscribe():
    try:
        data = request.get_json()
        user_id = session.get('user_id')   # Ensure user is logged in
        if not user_id:
            return jsonify({"success": False, "error": "User not logged in!"})

        plan_type = data.get("plan_type")
        meal_date_str = data.get("meal_date")
        meal_type = data.get("meal_type")
        food_type = data.get("food_type")
        total_cost = data.get("total_cost")

        # Validate inputs
        if not all([plan_type, meal_date_str, meal_type, food_type, total_cost]):
            return jsonify({"success": False, "error": "All fields are required!"})

        # Convert meal_date to date object
        try:
            meal_date = datetime.strptime(meal_date_str, "%Y-%m-%d").date()
        except:
            return jsonify({"success": False, "error": "Invalid date format!"})

        # Prevent past date subscription
        if meal_date < datetime.today().date():
            return jsonify({"success": False, "error": "Cannot select past dates!"})

        # Non-veg restriction (only Sundays)
        if food_type.lower() == "nonveg" and meal_date.weekday() != 6:  # 6 = Sunday
            return jsonify({"success": False, "error": "Non-Veg meals are only available on Sundays!"})

        # Calculate end_date based on plan_type
        plan_type_lower = plan_type.lower()
        if plan_type_lower == "trial":
            end_date = meal_date
        elif plan_type_lower == "weekly":
            end_date = meal_date + timedelta(days=6)
        elif plan_type_lower == "monthly":
            end_date = meal_date + timedelta(days=29)
        elif plan_type_lower == "quarterly":
            end_date = meal_date + timedelta(days=89)
        else:
            return jsonify({"success": False, "error": "Invalid plan type"})

        # DB connection
        # conn = get_connection()
        # cursor = conn.cursor()
        #  DB connection
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        

# Insert new subscription
        cursor.execute("""
            INSERT INTO subscriptions
                (user_id, plan_type, meal_date, end_date, meal_type, food_type, amount_paid, subscription_date, status)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, NOW(), 'active')
        """, (user_id, plan_type, meal_date, end_date, meal_type, food_type, total_cost))

        # Insert new subscription (mark 'Paid', can change to 'active' after real payment)
        # cursor.execute("""
        #     INSERT INTO subscriptions 
        #     (user_id, plan_type, meal_date, end_date, meal_type, food_type, amount_paid, status) 
        #     VALUES (%s, %s, %s, %s, %s, %s, %s, 'Paid')
        # """, (user_id, plan_type, meal_date, end_date, meal_type, food_type, total_cost))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("Error saving subscription:", e)
        return jsonify({"success": False, "error": str(e)})

# ---------------------------overlap-----------------
@app.route('/check_overlap', methods=['POST'])
def check_overlap():
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "User not logged in!"})

        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')

        if not start_date_str or not end_date_str:
            return jsonify({"success": False, "error": "Missing start or end date!"})

        # Convert strings to date objects
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "error": "Invalid date format!"})

        # DB connection
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query: check for overlapping active subscriptions
        cursor.execute("""
            SELECT id, meal_date, end_date 
            FROM subscriptions
            WHERE user_id = %s
              AND status = 'active'
              AND NOT (%s > end_date OR %s < meal_date)
        """, (user_id, start_date, end_date))

        overlapping_plans = cursor.fetchall()
        cursor.close()
        conn.close()

        if overlapping_plans:
            first = overlapping_plans[0]
            return jsonify({
                "success": False,
                "error": f"You already have an active plan from {first['meal_date']} to {first['end_date']}."
            })

        return jsonify({"success": True})

    except Exception as e:
        print("Error in check_overlap:", e)
        return jsonify({"success": False, "error": str(e)})

# =======================================
@app.route('/trial')
@login_required
def trial():
    # fetch plan details if needed
    if session.get('user_id'):  # regular user
        back_url = url_for('user_dashboard')
    elif session.get('is_admin'):  # admin
        back_url = url_for('admin_dashboard')
    return render_template('trial.html',back_url=back_url,current_user=current_user)

@app.route('/weekly')
def weekly():
    if session.get('user_id'):  # regular user
        back_url = url_for('user_dashboard')
    elif session.get('is_admin'):  # admin
        back_url = url_for('admin_dashboard',back_url=back_url)

    return render_template('weekly.html',back_url=back_url)

@app.route('/monthly')
def monthly():
    if session.get('user_id'):  # regular user
        back_url = url_for('user_dashboard')
    elif session.get('is_admin'):  # admin
        back_url = url_for('admin_dashboard')
    return render_template('monthly.html',back_url=back_url)

@app.route('/quarterly')
def quarterly():
    if session.get('user_id'):  # regular user
        back_url = url_for('user_dashboard')
    elif session.get('is_admin'):  # admin
        back_url = url_for('admin_dashboard')
    return render_template('quarterly.html',back_url=back_url)


# --------------------------subscribed_customers
@app.route('/subscribed_customers')
def subscribed_customers():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Join subscriptions with users to get customer name
        cursor.execute("""
            SELECT 
                s.id AS subscription_id,
                u.name AS customer_name,
                s.plan_type,
                s.meal_date,
                s.meal_type,
                s.food_type,
                s.amount_paid,
                s.status,
                s.subscription_date
            FROM subscriptions s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.subscription_date ASC
        """)
        subscriptions = cursor.fetchall()
        cursor.close()
        conn.close()

        today = datetime.today().date()

        # Calculate end_date for each subscription
        for sub in subscriptions:
            start_date = sub['meal_date']
            plan_type = sub['plan_type'].lower()
            if plan_type == "weekly":
                sub['end_date'] = start_date + timedelta(days=6)
            elif plan_type == "monthly":
                sub['end_date'] = start_date + timedelta(days=29)
            elif plan_type == "quarterly":
                sub['end_date'] = start_date + timedelta(days=89)
            else:  # Trial or unknown plans
                sub['end_date'] = start_date

                # ======= Add dynamic status =======
         # Calculate dynamic status for display
            if sub['status'].lower() == 'cancelled':
                sub['status_display'] = 'cancelled'
            elif start_date > today:
                sub['status_display'] = 'upcoming'
            elif sub['end_date'] < today:
                sub['status_display'] = 'completed'
            else:
                sub['status_display'] = 'active'


        return render_template('subscribed_customers.html', subscriptions=subscriptions)
    
    except Exception as e:
        print("Error fetching subscriptions:", e)
        return "Something went wrong!"
# ==============================================


# =================History=============================
@app.route('/history')
@login_required
def history():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM subscriptions 
        WHERE user_id=%s 
        ORDER BY subscription_date DESC
    """, (current_user.id,))
    
    subscriptions = cursor.fetchall()

    today = datetime.today().date()
    # Update status for display (not in DB)
    for sub in subscriptions:
        if sub['status'] == 'cancelled':
            sub['status_display'] = 'cancelled'
        elif sub['end_date'] < today:
            sub['status_display'] = 'completed'
        elif sub['meal_date'] > today:
            sub['status_display'] = 'upcoming'
        else:
            sub['status_display'] = 'active'

    cursor.close()
    conn.close()

    return render_template('history.html', subscriptions=subscriptions)
# ===========================User_skipped_meal...Table=====================
@app.route('/user_skipped_meals')
@login_required

def user_skipped_meals():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # conn = mysql.connection.cursor()
    cursor.execute("""
        SELECT sm.skip_id, sm.subscription_id, sm.skip_date, sm.meal_time, sm.refund_amount, sm.refund_status,
               p.plan_type
        FROM skipped_meals sm
        LEFT JOIN plans p ON sm.subscription_id = p.id
        WHERE sm.user_id = %s
        ORDER BY sm.created_at DESC
    """, (current_user.id,))
    skipped_meals = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('user_skipped_meals.html', skipped_meals=skipped_meals)

# ===============================================
@app.route('/skip', methods=['POST'])
def skip():
    try:
        if 'user_id' not in session:
            return jsonify({"success": False, "error": "User not logged in!"}), 401
        user_id = session['user_id']

        # Accept JSON or form data (works for either frontend approach)
        data = request.get_json(silent=True)
        if data:
            skip_date_str = data.get('skip_date')
            meal_time = data.get('skip_meal_time')
            subscription_id = data.get('subscription_id')
        else:
            skip_date_str = request.form.get('skip_date')
            meal_time = request.form.get('skip_meal_time')
            subscription_id = request.form.get('subscription_id')

        # Basic presence check
        if not skip_date_str or not meal_time:
            return jsonify({"success": False, "error": "All fields are required!"}), 400

        skip_date_str = str(skip_date_str).strip()
        # Debug log: helps you see what was actually received
        print("DEBUG: Received skip_date_str =", repr(skip_date_str))

        # Try common date formats
        parsed_date = None
        tried = []
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            tried.append(fmt)
            try:
                parsed_date = datetime.strptime(skip_date_str, fmt).date()
                break
            except Exception:
                pass

        # Fallback: datetime.fromisoformat (handles some ISO variants)
        if parsed_date is None:
            try:
                parsed_date = datetime.fromisoformat(skip_date_str).date()
            except Exception:
                parsed_date = None

        if parsed_date is None:
            # return helpful message showing what we tried
            return jsonify({
                "success": False,
                "error": f"Invalid date format! Received: {skip_date_str!r}. Expected formats: YYYY-MM-DD or DD/MM/YYYY."
            }), 400

        skip_date = parsed_date

        # DB connection
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Find active subscription covering skip_date for this user
        cursor.execute("""
            SELECT * FROM subscriptions 
            WHERE user_id=%s AND status='active'
              AND meal_date <= %s AND end_date >= %s
            ORDER BY id DESC LIMIT 1
        """, (user_id, skip_date, skip_date))
        subscription = cursor.fetchone()

        if not subscription:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "No active subscription covers this date."}), 404

        subscription_id_db = subscription['id']

                # Validate that the subscription covers this meal_time
       # After fetching subscription
        plan_meal_type = subscription['meal_type']  # fetch from DB

        # Check if user is trying to skip a meal not covered by their plan
        if plan_meal_type != 'both' and meal_time != plan_meal_type:
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": f"Your plan only covers {plan_meal_type.capitalize()} meals. You cannot skip {meal_time.capitalize()}."
            }), 400

        # Prevent duplicate skip (unique constraint also helps)
        cursor.execute("""
            SELECT 1 FROM skipped_meals
            WHERE user_id=%s AND subscription_id=%s AND skip_date=%s AND meal_time=%s
        """, (user_id, subscription_id_db, skip_date, meal_time))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "You have already skipped this meal."}), 409

        # Calculate refund (use your existing rules)
        refund_amount = 0
        food_type = (subscription.get('food_type') or '').lower()

        if meal_time in ['lunch', 'dinner']:
            if food_type == 'veg':
                refund_amount = 50
            else:  # nonveg
                # If non-veg allowed only Sunday at 70, else fallback to 50
                if skip_date.weekday() == 6:
                    refund_amount = 70
                else:
                    refund_amount = 50
        elif meal_time == 'both':
            if food_type == 'veg':
                refund_amount = 50 * 2
            else:
                if skip_date.weekday() == 6:
                    refund_amount = 70 + 50   # adjust if you treat both specially
                else:
                    refund_amount = 50 * 2

        # Insert record (unique key on (user_id, subscription_id, skip_date, meal_time) recommended)
        try:
            cursor.execute("""
                INSERT INTO skipped_meals (user_id, subscription_id, skip_date, meal_time, refund_amount, refund_status)
                VALUES (%s, %s, %s, %s, %s,'Pending')
            """, (user_id, subscription_id_db, skip_date, meal_time, refund_amount))
            conn.commit()
        except Exception as db_e:
            # possible duplicate or constraint error — handle gracefully
            conn.rollback()
            cursor.close()
            conn.close()
            print("DB Insert Error:", db_e)
            return jsonify({"success": False, "error": "Failed to save skip. Try again."}), 500

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "refund_amount": refund_amount,
            "message": f"Meal skipped successfully! Refund: ₹{refund_amount} will be refunded."
        })

    except Exception as e:
        print("Unhandled error in /skip:", e)
        return jsonify({"success": False, "error": "Server error"}), 500
# =============================================================


@app.route('/admin/extra_orders')
# @login_required
def admin_extra_orders():
    # try:
        # Only allow admins
        # if not current_user.is_admin:
        #     return "Unauthorized", 403


        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        # Join extra_orders with users table to get user names
        cursor.execute("""
            SELECT eo.extra_id, u.name AS user_name, eo.subscription_id, eo.extra_date,
                   eo.meal_type, eo.meal_time, eo.quantity, eo.total_amount,
                   eo.status, eo.created_at
            FROM extra_orders eo
            JOIN users u ON eo.user_id = u.id
            ORDER BY eo.extra_id DESC
        """)
        extra_orders = cursor.fetchall()
        cursor.close()

        # Render template and pass orders
        return render_template('admin_extra_orders.html', extra_orders=extra_orders)

    # except Exception as e:
    #     return f"Error: {str(e)}", 500


# =============================================================

@app.route('/admin/skipped_meals')
def admin_skipped_meals():
    # if 'admin_id' not in session:  # only admin can see
    #     return redirect(url_for('admin_login'))
    # session['admin_id'] = admin['id']


    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT sm.skip_id, sm.user_id, sm.skip_date, sm.meal_time, sm.refund_amount, sm.refund_status
        FROM skipped_meals sm
        ORDER BY sm.created_at DESC
    """)
    skipped_meals = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_skipped_meals.html", skipped_meals=skipped_meals)

# ===============================================

@app.route("/process_refund/<int:skip_id>", methods=["POST"])
def process_refund(skip_id):
    # if not session.get("is_admin"):  # ensure only admins can refund
    #     return redirect(url_for("admin_login"))

    try:
        cur = mysql.connection.cursor()

        # Example: mark refund as processed in skippedmeal table
        cur.execute("""
            UPDATE skipped_meals
            SET refund_status = 'Refunded'
            WHERE skip_id = %s
        """, (skip_id,))
        mysql.connection.commit()
        cur.close()

        flash("Refund processed successfully!", "success")
    except Exception as e:
        flash(f"Error processing refund: {str(e)}", "danger")

    return redirect(url_for("admin_skipped_meals"))

# ==================================================================

@app.route('/payment')
@login_required
def payment():
    plan_type = request.args.get('plan_type')
    meal_date = request.args.get('meal_date')
    end_date = request.args.get('end_date')

    meal_type = request.args.get('meal_type')
    food_type = request.args.get('food_type')
    total_cost = request.args.get('total_cost')


# Fix back_url based on plan_type
    if plan_type.lower() == 'trial':
        back_url = url_for('trial')
    elif plan_type.lower() == 'weekly':
        back_url = url_for('weekly')
    elif plan_type.lower() == 'monthly':
        back_url = url_for('monthly')
    elif plan_type.lower() == 'quarterly':
        back_url = url_for('quarterly')
    else:
        back_url = url_for('user_dashboard')

    return render_template(
        'payment.html',
        plan_type=plan_type,
        meal_date=meal_date,
            end_date=end_date,       # <-- add this

        meal_type=meal_type,
        food_type=food_type,
        total_cost=total_cost,
        back_url=back_url,
        user_address=getattr(current_user, 'address', 'Not Provided')

    )

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            return User(user['id'], user['name'], user['email'], user.get('address'))
        return None
    except Exception as e:
        print("Error loading user:", e)
        return None


@app.route('/save_subscription', methods=['POST'])
@login_required
def save_subscription():
    try:
        data = request.get_json()
        plan_type = data.get('plan_type')
        meal_date = data.get('meal_date')
        meal_type = data.get('meal_type')
        food_type = data.get('food_type')
        total_cost = data.get('total_cost')

        if not all([plan_type, meal_date, meal_type, food_type, total_cost]):
            return jsonify({"success": False, "message": "Missing data!"})

        # Convert date
        meal_date_obj = datetime.strptime(meal_date, "%Y-%m-%d").date()

        # Calculate end_date
        if plan_type.lower() == "trial":
            end_date = meal_date_obj
        elif plan_type.lower() == "weekly":
            end_date = meal_date_obj + timedelta(days=6)
        elif plan_type.lower() == "monthly":
            end_date = meal_date_obj + timedelta(days=29)
        elif plan_type.lower() == "quarterly":
            end_date = meal_date_obj + timedelta(days=89)
        else:
            end_date = meal_date_obj

        # Save to DB
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subscriptions
            (user_id, plan_type, meal_date, end_date, meal_type, food_type, amount_paid, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'active')
        """, (current_user.id, plan_type, meal_date_obj, end_date, meal_type, food_type, total_cost))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("Error saving subscription:", e)
        return jsonify({"success": False, "message": str(e)})
    
# =========================Extra ==================================
@app.route('/extra_order', methods=['POST'])
@login_required
def extra_order():
    try:
        # Parse JSON
        data = request.get_json(force=True)
        extra_date = data.get('extra_date')
        meal_type = data.get('meal_type')   # veg / nonveg
        meal_time = data.get('meal_time')   # lunch / dinner
        quantity = data.get('quantity')
        # subscription_id = data.get('subscription_id')  # or request.form['subscription_id']

        # Validate required fields
        if not all([extra_date, meal_type, meal_time, quantity]):
            return jsonify({"success": False, "error": "All fields are required!"})

        extra_date_obj = datetime.strptime(extra_date, "%Y-%m-%d").date()
        today = datetime.today().date()
        now = datetime.now()

        # Extra order allowed: 1 day before or before 10 AM same day
        # if extra_date_obj < today or (extra_date_obj == today and now.hour >= 10):
        #     return jsonify({"success": False, "error": "Extra orders must be placed 1 day before or before 10 AM today."})

# Extra order cutoff depending on meal_time
        if meal_time == "lunch":
            if extra_date_obj < today or (extra_date_obj == today and now.hour >= 10):
                return jsonify({"success": False, "error": "Lunch extra orders must be placed 1 day before or before 10 AM today."})
        elif meal_time == "dinner":
            if extra_date_obj < today or (extra_date_obj == today and now.hour >= 17):
                return jsonify({"success": False, "error": "Dinner extra orders must be placed 1 day before or before 5 PM today."})


        # Non-veg only on Sundays
        if meal_type == "nonveg" and extra_date_obj.weekday() != 6:
            return jsonify({"success": False, "error": "Non-veg is only allowed on Sundays."})
        
       # ---------------- Active subscription check ----------------
        # Active subscription check
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT id FROM subscriptions
            WHERE user_id = %s
            AND meal_date <= %s
            AND end_date >= %s
            AND status = 'active'
        """, (current_user.id, extra_date, extra_date))
        active_sub = cur.fetchone()

        if not active_sub:
            cur.close()
            return jsonify({"success": False, "error": "No active subscription found for this date."})

        subscription_id = active_sub[0]  # use index 0
        cur.close()


# 4️ Check for duplicate order BEFORE payment
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT * FROM extra_orders
            WHERE user_id=%s AND extra_date=%s AND meal_time=%s
        """, (current_user.id, extra_date, meal_time))
        existing_order = cur.fetchone()
        if existing_order:
            cur.close()
            return jsonify({"success": False, "error": f"You already placed an extra order for {meal_time} on {extra_date}."})
        # Calculate cost
        price = 50 if meal_type == "veg" else 70
        total_amount = price * int(quantity)

        payment_success = True  # Replace with actual payment check


        if payment_success:

        # Insert into extra_orders
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO extra_orders
                (user_id, subscription_id,extra_date, meal_type, meal_time, quantity, total_amount, status)
                VALUES (%s, %s,%s, %s, %s, %s, %s, %s)
            """, (current_user.id, subscription_id,extra_date, meal_type, meal_time, quantity, total_amount, 'paid'))
            mysql.connection.commit()
            cur.close()

            return jsonify({"success": True, "message": f"Extra order placed! Total: ₹{total_amount}"})
        else:
            return jsonify({"success": False, "error": "Payment failed. Order not placed."})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
    # ===============User...Extra order Table ===============================
@app.route('/user/extra_orders')
# @login_required
def user_extra_orders():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch all extra orders for the logged-in user
        cursor.execute("""
            SELECT extra_id, extra_date, meal_time, meal_type, quantity, total_amount
            FROM extra_orders
            WHERE user_id = %s
            ORDER BY extra_id DESC
        """, (current_user.id,))

        extra_orders = cursor.fetchall()
        cursor.close()

        return render_template('user_extra_orders.html', extra_orders=extra_orders)

    except Exception as e:
        return f"Error fetching extra orders: {str(e)}", 500
    
@app.route('/cancel_subscription/<int:subscription_id>', methods=['POST'])
@login_required
def cancel_subscription(subscription_id):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get subscription details
        cursor.execute("SELECT meal_date, plan_type, status FROM subscriptions WHERE id=%s AND user_id=%s",
                       (subscription_id, current_user.id))
        sub = cursor.fetchone()
        if not sub:
            return jsonify({"success": False, "message": "Subscription not found!"})

        today = datetime.today().date()
        start_date = sub['meal_date']

        # Determine refund message
        if sub['status'].lower() == 'active':
            message = "Your subscription is active. Amount will not be refunded."
        else:  # upcoming
            message = "Subscription cancelled. Refund will be processed."

        # Update status in DB
        cursor.execute("UPDATE subscriptions SET status='cancelled' WHERE id=%s", (subscription_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": message})

    except Exception as e:
        print("Error cancelling subscription:", e)
        return jsonify({"success": False, "message": "Something went wrong!"})


# if __name__ == "__main__":
#     app.run(debug=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)




# ==================================Payment success
# @app.route('/payment_success')
# @login_required
# def payment_success():
#     plan_type = request.args.get('plan_type')   # <-- match param name
#     meal_date = request.args.get('meal_date')
#     meal_type = request.args.get('meal_type')
#     food_type = request.args.get('food_type')
#     amount_paid = request.args.get('total_cost')

#     if not all([plan_type, meal_date, meal_type, food_type, amount_paid]):
#         flash("Payment info missing! Try again.", "danger")
#         return redirect(url_for('user_dashboard'))

#     # Convert date
#     try:
#         meal_date_obj = datetime.strptime(meal_date, "%Y-%m-%d").date()
#     except:
#         flash("Invalid date format!", "danger")
#         return redirect(url_for('user_dashboard'))
#     # Calculate end_date
#     if plan_type.lower() == "trial":
#         end_date = meal_date_obj
#     elif plan_type.lower() == "weekly":
#         end_date = meal_date_obj + timedelta(days=6)
#     elif plan_type.lower() == "monthly":
#         end_date = meal_date_obj + timedelta(days=29)
#     elif plan_type.lower() == "quaterly":
#         end_date = meal_date_obj + timedelta(days=89)
#     else:
#         end_date = meal_date_obj

#     # Insert subscription
#     try:
#         conn = get_connection()
#         cursor = conn.cursor()
#         cursor.execute("""
#             INSERT INTO subscriptions 
#             (user_id, plan_type, meal_date, end_date, meal_type, food_type, amount_paid, status)
#             VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
#         """, (current_user.id, plan_type, meal_date_obj, end_date, meal_type, food_type, amount_paid))
#         conn.commit()
#         cursor.close()
#         conn.close()
#     except Exception as e:
#         print("DB Insert Error:", e)
#         flash("Failed to save subscription!", "danger")
#         return redirect(url_for('user_dashboard'))

#     flash("Subscription successful!", "success")
#     return redirect(url_for('user_dashboard'))



# conn = get_connection()
# cursor = conn.cursor()
