
from flask import abort

from flask import Flask, render_template, request, redirect, url_for, session, flash

import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///travelgo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20))
    preferences = db.Column(db.String(200))
    bookings = db.relationship('Booking', backref='user', lazy=True)

# Booking model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(100), nullable=False)
    time = db.Column(db.String(100))
    price = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Confirmed')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.String(100))

# Create tables if not exist
with app.app_context():
    db.create_all()

# Helper functions for user and booking management
def get_user_by_email(email):
    return User.query.filter_by(email=email).first()

def add_user(name, email, password, phone=None, preferences=None):
    hashed_pw = generate_password_hash(password)
    user = User(name=name, email=email, password=hashed_pw, phone=phone, preferences=preferences)
    db.session.add(user)
    db.session.commit()
    return user

def add_booking(user, service, time, price, status='Confirmed', date=None):
    booking = Booking(service=service, time=time, price=price, status=status, user=user, date=date)
    db.session.add(booking)
    db.session.commit()
    return booking

def get_user_bookings(user):
    return Booking.query.filter_by(user_id=user.id).all()

def cancel_user_booking(user, service, date):
    booking = Booking.query.filter_by(user_id=user.id, service=service, date=date).first()
    if booking:
        booking.status = 'Cancelled'
        db.session.commit()
        return True
    return False

# Bookings History page
@app.route('/bookingshistory')
def bookingshistory():
    if 'user' not in session:
        return redirect(url_for('auth'))
    user = session['user']
    db_user = get_user_by_email(user['email'])
    user_bookings = get_user_bookings(db_user)
    num_bookings = len([b for b in user_bookings if (b.status or '').lower() != 'cancelled'])
    num_cancellations = len([b for b in user_bookings if (b.status or '').lower() == 'cancelled'])
    bookings = [
        {
            'service': b.service,
            'details': b.time,
            'date': b.date or b.time,
            'status': b.status or 'Confirmed'
        }
        for b in reversed(user_bookings)
    ]
    return render_template('bookingshistory.html', num_bookings=num_bookings, num_cancellations=num_cancellations, bookings=bookings)

# Route to handle profile edit (name, phone)
@app.route('/edit_profile', methods=['POST'])
def edit_profile():
    if 'user' not in session:
        return redirect(url_for('auth'))
    email = session['user']['email']
    name = request.form.get('name')
    phone = request.form.get('phone')
    db_user = get_user_by_email(email)
    if db_user:
        db_user.name = name
        db_user.phone = phone
        db.session.commit()
        session['user']['name'] = name
        session['user']['phone'] = phone
        flash('Profile updated successfully!', 'success')
    else:
        flash('User not found.', 'error')
    return redirect(url_for('profile'))

@app.route('/')
def home():
    name = session['user']['name'] if 'user' in session else 'Guest'
    return render_template('index.html', name=name)

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email')
        password = request.form.get('password')

        if action == 'login':
            user = get_user_by_email(email)
            if user and check_password_hash(user.password, password):
                session['user'] = {'name': user.name, 'email': email}
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid credentials', 'error')
        elif action == 'signup':
            name = request.form.get('name')
            if get_user_by_email(email):
                flash('Email already registered.', 'error')
            else:
                add_user(name, email, password)
                flash('Account created! Please log in.', 'success')
                session['user'] = {'name': name, 'email': email}
                return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('auth'))
    return render_template('index.html', name=session['user']['name'])

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('auth'))
    filter_type = request.args.get('type', 'all')

    return render_template('dashboard.html', name=session['user']['name'], filter_type=filter_type)

# Booking page route
from flask import abort

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'user' not in session:
        return redirect(url_for('auth'))
    if request.method == 'GET':
        item_type = request.args.get('item_type')
        if item_type == 'bus':
            item = {
                'name': request.args.get('name'),
                'origin': request.args.get('origin'),
                'destination': request.args.get('destination'),
                'departure': request.args.get('departure'),
                'price': request.args.get('price')
            }
        elif item_type == 'hotel':
            item = {
                'name': request.args.get('name'),
                'location': request.args.get('location'),
                'available_rooms': request.args.get('available_rooms'),
                'price': request.args.get('price')
            }
        else:
            abort(400)
        return render_template('booking.html', item_type=item_type, item=item)
    else:
        # On POST, redirect to confirm page with booking details
        item_type = request.form.get('item_type')
        if item_type == 'bus':
            service = request.form.get('name')
            time = request.form.get('departure')
            price = request.form.get('price')
        else:
            service = request.form.get('name')
            time = 'Check-in: 12:00 PM'
            price = request.form.get('price')
        return redirect(url_for('confirm', service=service, time=time, price=price))



# Profile page now uses user_profile.html
@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('auth'))
    user = session['user']
    db_user = get_user_by_email(user['email'])
    user_bookings = get_user_bookings(db_user)
    num_bookings = len([b for b in user_bookings if (b.status or '').lower() != 'cancelled'])
    num_cancellations = len([b for b in user_bookings if (b.status or '').lower() == 'cancelled'])
    user_details = {
        'name': db_user.name,
        'email': db_user.email,
        'phone': db_user.phone or '+91 9876543210',
        'preferences': db_user.preferences or 'Sleeper Bus, Budget Hotels'
    }
    bookings = [
        {
            'service': b.service,
            'details': b.time,
            'date': b.date or b.time,
            'status': b.status or 'Confirmed'
        }
        for b in reversed(user_bookings) if (b.status or '').lower() != 'cancelled'
    ]
    return render_template('user_profile.html', user=user_details, num_bookings=num_bookings, num_cancellations=num_cancellations, bookings=bookings)


# Cancel booking route
@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'user' not in session:
        return redirect(url_for('auth'))
    service = request.form.get('service')
    date = request.form.get('date')
    email = session['user']['email']
    db_user = get_user_by_email(email)
    if cancel_user_booking(db_user, service, date):
        flash('Booking cancelled successfully.', 'success')
    else:
        flash('Booking not found.', 'error')
    return redirect(url_for('profile'))

@app.route('/confirm', methods=['GET', 'POST'])
def confirm():
    if 'user' not in session:
        return redirect(url_for('auth'))
    if request.method == 'POST':
        service = request.form.get('service')
        time = request.form.get('time')
        price = request.form.get('price')
        email = session['user']['email']
        db_user = get_user_by_email(email)
        if not db_user:
            flash('User not found. Please log in again.', 'error')
            return redirect(url_for('auth'))
        booking = add_booking(db_user, service, time, price, status='Confirmed', date=time)
        booking_data = {
            'service': booking.service,
            'time': booking.time,
            'price': booking.price,
            'status': booking.status
        }
        return render_template('confirm.html', booking=booking_data, name=session['user']['name'])
    return render_template('confirm.html', booking=None, name=session['user']['name'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
