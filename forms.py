    from flask_wtf import FlaskForm
    from wtforms import StringField, PasswordField, SubmitField
    from wtforms.validators import DataRequired, Length, Optional


    class LoginForm(FlaskForm):
        username = StringField("Username", validators=[DataRequired()])
        password = PasswordField("Password", validators=[DataRequired()])
        captcha = StringField("CAPTCHA", validators=[Optional(), Length(min=5, max=5)])
        submit = SubmitField("Login")


    class MFAForm(FlaskForm):
        code = StringField("6-digit code", validators=[DataRequired(), Length(min=6, max=6)])
        submit = SubmitField("Verify")
