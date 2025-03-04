from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timezone
import os

app = Flask(__name__)
# Configure the MongoDB connection using environment variables (as set in docker-compose.yml :contentReference[oaicite:3]{index=3})
app.config["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb://admin:secret@localhost:27017/lfg_app?authSource=admin")
app.secret_key = os.environ.get("SECRET_KEY", "your_secret_key")

mongo = PyMongo(app)
db = mongo.db

def is_admin():
    return 'user' in session and session['user'].get('role') == 'admin'



@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Retrieve all LFG posts from the database (displayed in index.html :contentReference[oaicite:4]{index=4})
    search_query=request.args.get('search', '')
    if search_query:
        posts=list(db.lfg.find({
            '$or':[
                {'game':{'$regex':search_query,'$options':'i'}},
                {'description':{'$regex':search_query,'$options':'i'}}
            ]
        }))
    else: 
        posts=list(db.lfg.find())
    for post in posts:
        post['_id_str'] = str(post['_id'])
    current_user = session['user']
    
    return render_template('index.html', lfg_posts=posts, current_user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = db.users.find_one({'username': username})
        # In a real application, use hashed passwords.
        if user and user['password'] == password:
            session['user'] = {
                'id': str(user['_id']), 
                'username': user['username'], 
                'email': user.get('email', ''), 
                'role': user.get('role', 'user')
            }
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password')
            return redirect(url_for('login'))
    # Render the login page (login.html :contentReference[oaicite:5]{index=5})
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('signup'))
        existing_user = db.users.find_one({'username': username})
        if existing_user:
            flash('Username already exists')
            return redirect(url_for('signup'))
        user_id = db.users.insert_one({
            'username': username, 
            'email': email,
            'password': password,
            'role': 'user'
        }).inserted_id
        session['user'] = {'id': str(user_id), 'username': username, 'email': email, 'role': 'user'}
        return redirect(url_for('home'))
    # Render the signup page (signup.html :contentReference[oaicite:6]{index=6})
    return render_template('signup.html', signup=True)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/create_lfg', methods=['GET', 'POST'])
def create_lfg():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        game = request.form.get('game')
        description = request.form.get('description')
        level_required = request.form.get('level_required')
        availability = request.form.get('availability')
        region = request.form.get('region')
        # Add a new LFG post to the database (create_lfg.html :contentReference[oaicite:7]{index=7})
        db.lfg.insert_one({
            'game': game,
            'description': description,
            'level_required': level_required,
            'created_by': session['user']['id'],
            'created_at': datetime.now(timezone.utc),
            'contact': session['user'].get('email', ''),
            'role': session['user']['role']  # the basement of access
        })
        return redirect(url_for('home'))
    return render_template('create_lfg.html')

@app.route('/edit_lfg/<id>', methods=['GET', 'POST'])
def edit_lfg(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    lfg_post = db.lfg.find_one({'_id': ObjectId(id)})
    if not lfg_post:
        return render_template('error.html', error="Post not found.")  # (error.html :contentReference[oaicite:8]{index=8})

    # Only allow the owner to edit the post
    post_owner = lfg_post.get('created_by') or lfg_post.get('user_id')

    if not is_admin() and post_owner != session['user']['id']:
        return render_template('error.html', error="You are not authorized to edit this post.")

    if request.method == 'POST':
        game = request.form.get('game')
        description = request.form.get('description')
        level_required = request.form.get('level_required')
        availability = request.form.get('availability')
        region = request.form.get('region')
        db.lfg.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'game': game,
                'description': description,
                'level_required': level_required,
                'availability': availability,
                'region': region
            }}
        )
        return redirect(url_for('home'))

    # Render the edit page (edit_lfg.html :contentReference[oaicite:9]{index=9})
    return render_template('admin_edit_lfg.html' if is_admin() else 'edit_lfg.html', lfg=lfg_post)


@app.route('/delete_lfg/<id>', methods=['POST'])
def delete_lfg(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    lfg_post = db.lfg.find_one({'_id': ObjectId(id)})
    if not lfg_post:
        return render_template('error.html', error="Post not found.")

    post_owner = lfg_post.get('created_by') or lfg_post.get('user_id')
    if is_admin():
        db.lfg.delete_one({'_id': ObjectId(id)})
        return redirect(url_for('admin_reports'))

    # Only allow the owner to delete their own post
    if not is_admin() and post_owner != session['user']['id']:
        return render_template('error.html', error="You are not authorized to delete this post.")

    db.lfg.delete_one({'_id': ObjectId(id)})

    return redirect(url_for('home') if not is_admin() else url_for('admin_reports'))
### Delete Confirmation

@app.route('/delete_confirm/<id>')
def delete_confirm(id):
    """Show delete confirmation page."""
    if 'user' not in session:
        return redirect(url_for('login'))

    lfg_post = db.lfg.find_one({'_id': ObjectId(id)})
    if not lfg_post:
        flash("Post not found.")
        return redirect(url_for('home'))
    
    # Convert ObjectId to string for template usage
    lfg_post['_id_str'] = str(lfg_post['_id'])

    return render_template('delete_confirm.html', post=lfg_post)


@app.route('/confirm_delete_lfg/<id>', methods=['POST'])
def confirm_delete_lfg(id):
    """Perform actual delete after confirmation."""
    if 'user' not in session:
        return redirect(url_for('login'))

    lfg_post = db.lfg.find_one({'_id': ObjectId(id)})
    if not lfg_post:
        flash("Post not found.")
        return redirect(url_for('home'))

    db.lfg.delete_one({'_id': ObjectId(id)})
    flash("Post deleted successfully.")
    return redirect(url_for('home'))

#Detail posting
@app.route('/post/<id>')
def post_detail(id):
    """Display detailed view of a single LFG post."""
    if 'user' not in session:
        return redirect(url_for('login'))

    lfg_post = db.lfg.find_one({'_id': ObjectId(id)})
    if not lfg_post:
        return render_template('error.html', error="Post not found.")

    # Fetch the username of the post creator
    user = db.users.find_one({'_id': ObjectId(lfg_post.get('created_by'))})

    return render_template('post_detail.html', post=lfg_post, posted_by=user['username'] if user else "Unknown")




@app.route('/admin_reports')
def admin_reports():
    if not is_admin():
        return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    if search_query:
        posts = list(db.lfg.find({
            'description': {'$regex': search_query, '$options': 'i'}
        }))
    else:
        posts = list(db.lfg.find())

    for post in posts:
        post['_id_str'] = str(post['_id'])
    
    return render_template('admin_reports.html', posts=posts)

@app.route('/admin_dashboard', methods=["GET"])
def admin_dashboard():
    if not is_admin():
        return redirect(url_for('login'))
    try:
        users = list(db.users.find({}))
        posts = list(db.lfg.find({}).sort("created_at", -1))
        return render_template("admin_dashboard.html", users=users, posts=posts)
    except Exception as e:
        logging.error(f"⚠️ Error fetching admin data: {e}", exc_info=True)
        return render_template("error.html", error="Could not load admin data")



@app.route('/admin_delete_lfg/<id>', methods=['POST'])
def admin_delete_lfg(id):
    if not is_admin():
        return redirect(url_for('login'))
    
    db.lfg.delete_one({'_id': ObjectId(id)})
    return redirect(url_for('admin_reports'))


@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'user' not in session:
        return redirect(url_for('login'))
    results = []
    query = ""
    if request.method == 'POST':
        query = request.form.get('query')
        # Search for posts by game or description (satisfies the search requirement)
        results = list(db.lfg.find({
            '$or': [
                {'game': {'$regex': query, '$options': 'i'}},
                {'description': {'$regex': query, '$options': 'i'}}
            ]
        }))
        for post in results:
            post['_id_str'] = str(post['_id'])
    # Note: You'll need to create a corresponding search.html template to display these results.
    return render_template('search.html', results=results, query=query)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Fixed admin credentials
        if username == "admin" and password == "admin123":
            session['user'] = {
                'id': 'admin', 
                'username': 'admin', 
                'role': 'admin', 
                'email': ''
                }
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

# Custom error handlers to render error.html for common errors (error.html :contentReference[oaicite:11]{index=11})
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error="An internal server error occurred."), 500

if __name__ == '__main__':
    # Run the application on the port specified in the environment variable (or default to 5000)
    app.run(host='0.0.0.0', port=int(os.environ.get("FLASK_PORT", 5000)))