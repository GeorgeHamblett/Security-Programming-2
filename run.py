from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    db.create_all()
    if User.query.count() == 0:
        admin = User(username="admin"); admin.set_password("Admin123!Admin123!")
        user1 = User(username="user1"); user1.set_password("LetMeIn123!AAA")
        user2 = User(username="user2"); user2.set_password("Welcome123!BBB")
        db.session.add_all([admin, user1, user2]); db.session.commit()
        print("Example users: admin, user1, user2")
if __name__ == "__main__":
    print("http://127.0.0.1:5000/")
    app.run()