from datetime import date
import datetime as dt
from flask import Flask, abort, render_template, redirect, url_for, flash, request
import smtplib
import os

from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from functools import wraps

from database import db
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

login_manager = LoginManager()
ckeditor = CKEditor()
bootstrap = Bootstrap5()
gravatar = Gravatar(
    app=None,  
    size=100,
    rating='g',
    default='retro',
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['CKEDITOR_PKG_TYPE'] = 'basic'

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'
ckeditor.init_app(app)
bootstrap.init_app(app)
gravatar.init_app(app)

with app.app_context():
    from models import User, BlogPost, Comment
    db.create_all()

# TODO: Configure Flask-Login
@login_manager.user_loader
def load_user(user_id):
    from models import User
    try:
        return db.session.execute(db.select(User).where(User.id == int(user_id))).scalar()
    except:
        return db.get_or_404(User, int(user_id))

# make current_year available to all templates
@app.context_processor
def inject_current_year():
    return {"current_year": dt.datetime.now().year}

# Creating an @admin_only decorator
def admin_only(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        # If the user is not authenticated or id is not 1 then abort with 403 error
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        # Otherwise continue with the route function
        return func(*args, **kwargs)
    return decorated_function

# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    from models import User
    form = RegisterForm()
    if form.validate_on_submit():
        from werkzeug.security import generate_password_hash
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if user:
            flash_message = flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login', message=flash_message))
        new_user = User(
            name=form.name.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=8)
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template("register.html", form=form, logged_in=current_user.is_authenticated)

# TODO: Retrieve a user from the database based on their email.
@app.route('/login', methods=["GET", "POST"])
def login():
    from models import User
    form = LoginForm()
    if form.validate_on_submit():
        from werkzeug.security import check_password_hash
        email = form.email.data
        password = form.password.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('get_all_posts'))
    return render_template("login.html", form=form, logged_in=current_user.is_authenticated)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))

@app.route('/')
def get_all_posts():
    from models import BlogPost
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, logged_in=current_user.is_authenticated)

# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    from models import BlogPost, Comment
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash_message = flash("You need to login or register to comment.")
            return redirect(url_for("login", message=flash_message, next=url_for("show_post", post_id=post_id)))
        new_comment = Comment(
            text=form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for("show_post", post_id=post_id))
    return render_template("post.html", post=requested_post, form=form, logged_in=current_user.is_authenticated)

# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    from models import BlogPost
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, logged_in=current_user.is_authenticated)

# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    from models import BlogPost
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, logged_in=current_user.is_authenticated)

# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    from models import BlogPost
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))

@app.route("/about")
def about():
    return render_template("about.html", logged_in=current_user.is_authenticated)

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        message = request.form["message"]
        email = request.form["email"]
        with smtplib.SMTP(os.environ.get('SMTP_SERVER'), int(os.environ.get('SMTP_PORT'))) as connection:
            connection.starttls()
            connection.login(user=os.environ.get('EMAIL'), password=os.environ.get('PASSWORD'))
            connection.sendmail(
                from_addr=os.environ.get('EMAIL'),
                to_addrs=os.environ.get('ADMIN_EMAIL'),
                msg=(f"Subject: New Message!\n\n"
                     f"Name: {name}\nPhone: {phone}\nMessage: {message}\nEmail: {email}"
                     ).encode("utf-8")
            )
        return render_template("contact.html", msg_sent=True, logged_in=current_user.is_authenticated)
    return render_template("contact.html", logged_in=current_user.is_authenticated, msg_sent=False)

if __name__ == "__main__":
    app.run(debug=True, port=5002)
