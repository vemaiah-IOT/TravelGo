# Updated app.py for AWS EC2 + DynamoDB + SNS (No SQLite)

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
import os
import boto3
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'mydefaultsecret')

# AWS Resources
region = 'us-east-1'  # Update with your region

dynamodb = boto3.resource('dynamodb', region_name=region)
sns = boto3.client('sns', region_name=region)

users_table = dynamodb.Table('Users')
bookings_table = dynamodb.Table('Bookings')

SNS_TOPIC_ARN = 'arn:aws:sns:your-region:your-account-id:BookingAlerts'  # Replace with your actual topic ARN

# Helper Functions
def get_user_by_email(email):
    response = users_table.get_item(Key={'email': email})
    return response.get('Item')

def add_user(name, email, password, phone=None, preferences=None):
    hashed_pw = generate_password_hash(password)
    users_table.put_item(Item={
        'email': email,
        'name': name,
        'password': hashed_pw,
        'phone': phone or '',
        'preferences': preferences or ''
    })

def add_booking(user_email, service, time, price, status='Confirmed', date=None):
    booking_id = str(uuid.uuid4())
    bookings_table.put_item(Item={
        'id': booking_id,
        'user_email': user_email,
        'service': service,
        'time': time,
        'price': price,
        'status': status,
        'date': date or time
    })
    notify_booking(service, user_email)
    return {
        'id': booking_id, 'service': service, 'time': time, 'price': price, 'status': status
    }

def get_user_bookings(user_email):
    response = bookings_table.scan(FilterExpression=boto3.dynamodb.conditions.Attr('user_email').eq(user_email))
    return response.get('Items', [])

def cancel_user_booking(user_email, service, date):
    response = bookings_table.scan(FilterExpression=(
        boto3.dynamodb.conditions.Attr('user_email').eq(user_email) &
        boto3.dynamodb.conditions.Attr('service').eq(service) &
        boto3.dynamodb.conditions.Attr('date').eq(date)
    ))
    items = response.get('Items', [])
    if items:
        booking = items[0]
        bookings_table.update_item(
            Key={'id': booking['id']},
            UpdateExpression='SET #s = :val1',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':val1': 'Cancelled'}
        )
        return True
    return False

def notify_booking(service, user_email):
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject='TravelGo Booking Confirmation',
        Message=f'Booking for {service} has been confirmed for user {user_email}.'
    )

# Routes
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
            if user and check_password_hash(user['password'], password):
                session['user'] = {'name': user['name'], 'email': email, 'phone': user.get('phone')}
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid credentials', 'error')
        elif action == 'signup':
            name = request.form.get('name')
            if get_user_by_email(email):
                flash('Email already registered.', 'error')
            else:
                add_user(name, email, password)
                session['user'] = {'name': name, 'email': email}
                flash('Account created!', 'success')
                return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('auth'))
    return render_template('dashboard.html', name=session['user']['name'], filter_type=request.args.get('type', 'all'))

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
        item_type = request.form.get('item_type')
        service = request.form.get('name')
        time = request.form.get('departure') if item_type == 'bus' else 'Check-in: 12:00 PM'
        price = request.form.get('price')
        return redirect(url_for('confirm', service=service, time=time, price=price))

@app.route('/confirm', methods=['GET', 'POST'])
def confirm():
    if 'user' not in session:
        return redirect(url_for('auth'))
    if request.method == 'POST':
        service = request.form.get('service')
        time = request.form.get('time')
        price = request.form.get('price')
        email = session['user']['email']
        booking_data = add_booking(email, service, time, price, status='Confirmed', date=time)
        return render_template('confirm.html', booking=booking_data, name=session['user']['name'])
    return render_template('confirm.html', booking=None, name=session['user']['name'])

@app.route('/bookingshistory')
def bookingshistory():
    if 'user' not in session:
        return redirect(url_for('auth'))
    email = session['user']['email']
    bookings = get_user_bookings(email)
    num_bookings = len([b for b in bookings if b.get('status', '').lower() != 'cancelled'])
    num_cancellations = len([b for b in bookings if b.get('status', '').lower() == 'cancelled'])
    display_bookings = [
        {
            'service': b['service'],
            'details': b['time'],
            'date': b.get('date', b['time']),
            'status': b.get('status', 'Confirmed')
        }
        for b in reversed(bookings)
    ]
    return render_template('bookingshistory.html', num_bookings=num_bookings, num_cancellations=num_cancellations, bookings=display_bookings)

@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('auth'))
    email = session['user']['email']
    user = get_user_by_email(email)
    bookings = get_user_bookings(email)
    num_bookings = len([b for b in bookings if b.get('status', '').lower() != 'cancelled'])
    num_cancellations = len([b for b in bookings if b.get('status', '').lower() == 'cancelled'])
    display_bookings = [
        {
            'service': b['service'],
            'details': b['time'],
            'date': b.get('date', b['time']),
            'status': b.get('status', 'Confirmed')
        }
        for b in reversed(bookings) if b.get('status', '').lower() != 'cancelled'
    ]
    return render_template('user_profile.html', user=user, num_bookings=num_bookings, num_cancellations=num_cancellations, bookings=display_bookings)

@app.route('/edit_profile', methods=['POST'])
def edit_profile():
    if 'user' not in session:
        return redirect(url_for('auth'))
    email = session['user']['email']
    name = request.form.get('name')
    phone = request.form.get('phone')
    users_table.update_item(
        Key={'email': email},
        UpdateExpression='SET #n = :name, phone = :phone',
        ExpressionAttributeNames={'#n': 'name'},
        ExpressionAttributeValues={':name': name, ':phone': phone}
    )
    session['user']['name'] = name
    session['user']['phone'] = phone
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'user' not in session:
        return redirect(url_for('auth'))
    service = request.form.get('service')
    date = request.form.get('date')
    email = session['user']['email']
    if cancel_user_booking(email, service, date):
        flash('Booking cancelled successfully.', 'success')
    else:
        flash('Booking not found.', 'error')
    return redirect(url_for('profile'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
