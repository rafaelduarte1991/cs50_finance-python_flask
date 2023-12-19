import os
import re
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        cashAdded = request.form.get("cash")
        if not cashAdded.isdigit():
            return apology("must provide a number", 400)
        if not cashAdded or int(cashAdded) <= 0:
            return apology("must provide a positive integer", 400)

        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            cashAdded,
            session["user_id"],
        )

    """Show portfolio of stocks"""
    anyUser = db.execute("SELECT * FROM users")
    if anyUser is None:
        return redirect("/login")
    else:
        stocks = db.execute(
            "SELECT symbol, SUM(shares) as shares_quantity FROM history WHERE user_id = ? GROUP BY symbol HAVING shares_quantity > 0",
            session["user_id"],
        )

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0][
            "cash"
        ]

        total_assets = cash

        for stock in stocks:
            quote = lookup(stock["symbol"])
            stock["price"] = quote["price"]
            stock["name"] = quote["name"]
            stock["value"] = stock["price"] * stock["shares_quantity"]
            total_assets += stock["value"]

        return render_template(
            "index.html", stocks=stocks, cash=cash, total_assets=total_assets
        )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    transaction_type = "Buy"
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("must provide a symbol", 400)
        if not shares.isdigit():
            return apology("must provide a positive integer", 400)
        if not shares or int(shares) <= 0:
            return apology("must provide a positive integer", 400)

        quote = lookup(symbol)
        if quote is None:
            return apology("symbol was not found")

        price = quote["price"]
        cost = int(shares) * price
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0][
            "cash"
        ]

        if cash < cost:
            return apology("Sorry, you do not have enough cash for this transaction")

        db.execute(
            "UPDATE users SET cash = cash - ? WHERE id = ?", cost, session["user_id"]
        )

        db.execute(
            "INSERT INTO history (user_id, type, symbol, shares, price) VALUES(?,?,?,?,?)",
            session["user_id"],
            transaction_type,
            symbol,
            shares,
            price,
        )

        flash(f"{shares} shares of {symbol} was bought!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute(
        "SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC",
        session["user_id"],
    )
    return render_template("history.html", transactions=transactions)


# rafael 12345
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        elif not request.form.get("password"):
            return apology("must provide password", 400)

        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 400)

        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("Stock symbol does not exist", 400)
        else:
            return render_template("quote.html", quote=quote)
    else:
        return render_template("quote.html")


def is_valid_registration(username, password, password_confirm):
    if not username:
        return "Must provide username"
    if not password:
        return "Must provide password"
    if not password_confirm:
        return "Must confirm your password"
    if password != password_confirm:
        return "The password and password confirmation are different"
    # if len(password) < 5 or not re.match(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{5,}$', password):
    #     return "Password must contain at least 5 characters, including letters and numbers"
    return None


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password_confirm = request.form.get("confirmation")

        error_message = is_valid_registration(username, password, password_confirm)

        if error_message:
            return apology(error_message, 400)

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        if len(rows) != 0:
            return apology(
                "The username is already taken. Choose another username", 400
            )

        hashed_password = generate_password_hash(password)

        db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)",
            username,
            hashed_password,
        )

        registered_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = registered_user[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    transaction_type = "Sell"
    stocks = db.execute(
        "SELECT symbol, SUM(shares) as shares_quantity FROM history WHERE user_id = ? GROUP BY symbol HAVING shares_quantity > 0",
        session["user_id"],
    )

    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares_to_sell = request.form.get("shares")
        if not symbol:
            return apology("must provide a symbol")
        elif (
            not shares_to_sell
            or int(shares_to_sell) <= 0
            or not shares_to_sell.isdigit()
        ):
            return apology("must provide a positive integer")
        else:
            shares_to_sell = int(shares_to_sell)

        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["shares_quantity"] < shares_to_sell:
                    return apology("You do not have enough shares")
                else:
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("symbol was not found")
                    price = quote["price"]
                    sale_total = price * shares_to_sell

                    db.execute(
                        "UPDATE users SET cash = cash + ? WHERE id = ?",
                        sale_total,
                        session["user_id"],
                    )

                    deduct_shares = shares_to_sell * (-1)
                    # add to history
                    db.execute(
                        "INSERT INTO history (user_id, type, symbol, shares, price) VALUES(?,?,?,?,?)",
                        session["user_id"],
                        transaction_type,
                        symbol,
                        deduct_shares,
                        price,
                    )

                    flash(
                        f"The {shares_to_sell} {symbol} shares was successfully sold!"
                    )
                    return redirect("/")
        return apology("Symbol not found")
    else:
        return render_template("sell.html", stocks=stocks)
