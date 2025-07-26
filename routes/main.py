from flask import Blueprint, render_template, redirect, url_for, send_from_directory, current_app
from flask_login import login_required, current_user
from models import Session
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/hbbtv')
def hbbtv():
    return render_template('hbbtv_index.html')

@main_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static/images'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@main_bp.route('/', methods=['GET'])
def home():
    return redirect(url_for('main.index'))

@main_bp.route('/index')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin.admin_dashboard'))
    
    sessions = Session.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', sessions=sessions)