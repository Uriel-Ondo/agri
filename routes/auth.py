from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Connexion réussie !', 'success')
            next_page = url_for('admin.admin_dashboard') if user.role == 'admin' else url_for('main.dashboard')
            return redirect(next_page)
        else:
            flash('Email ou mot de passe incorrect', 'danger')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas', 'danger')
            return redirect(url_for('auth.register'))
        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            flash('Ce nom d\'utilisateur est déjà pris', 'danger')
            return redirect(url_for('auth.register'))
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Cet email est déjà utilisé', 'danger')
            return redirect(url_for('auth.register'))
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role='expert'
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Compte créé avec succès ! Vous pouvez vous connecter', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.email = request.form['email']
        current_password = request.form['current_password']
        
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Mot de passe actuel incorrect', 'danger')
            return redirect(url_for('auth.profile'))
        
        if request.form['new_password']:
            if request.form['new_password'] != request.form['confirm_password']:
                flash('Les nouveaux mots de passe ne correspondent pas', 'danger')
                return redirect(url_for('auth.profile'))
            
            current_user.password_hash = generate_password_hash(request.form['new_password'])
        
        db.session.commit()
        flash('Profil mis à jour avec succès', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('profile.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('auth.login'))