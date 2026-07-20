from flask import Flask,render_template,request,url_for,redirect,session,jsonify
import mysql.connector
from mysql.connector import Error
import random
import smtplib
from email.mime.text import MIMEText
import time
from mysql.connector import pooling
from dotenv import load_dotenv
import os
from werkzeug.security import generate_password_hash,check_password_hash
import resend

load_dotenv()



app=Flask(__name__)
app.secret_key=os.getenv("app_secret_key")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,   # Set to False only while developing locally with http://localhost
    SESSION_COOKIE_SAMESITE="Lax"
)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")



pool = pooling.MySQLConnectionPool(
    pool_name="ecommerce_pool",
    pool_size=10,
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME
)

def connection():
    return pool.get_connection()



@app.route('/')
def home():
    username=session.get("user_name")
    return render_template('index.html',username=username)

@app.route('/category/<category_name>')
def category(category_name):
    connect=connection()
    cursor=connect.cursor()
    cursor.execute(
        '''SELECT * FROM products WHERE category_name=%s''',(category_name,)
    )

    products=cursor.fetchall()
    cursor.close()
    connect.close()

    return render_template("category.html",products=products)

@app.route('/logino')
def logino():
    return render_template('login.html')





@app.route('/login_details',methods=['post'])
def login_details():
    
    connect=connection()
    cursor=connect.cursor(dictionary=True)
    
    
    username=request.form["email_id"]
    password=request.form["password"]
    cursor.execute(''' SELECT id,user_name,email_id,password_hash FROM account_details WHERE email_id=%s ''',(username,))

    user_details=cursor.fetchone()
   
    original_name=user_details["email_id"]
    original_password=check_password_hash(user_details["password_hash"],password)
    
    
    if (username== original_name) and (original_password):

        session["user_id"]=user_details["id"]
        session['user_name']=user_details["user_name"]
       

        cursor.close()
        connect.close()


        return redirect(url_for('/'))
    elif original_password:
        return render_template('login.html',error_username="You Username is Wrong Please check!!!")
    elif (username== original_name):
        return render_template('login.html',error_username="You password is Wrong Please check!!!")

    else:
        return render_template('login.html',error_username="You Do Not Have Account With this Credentials!!!")






@app.route('/register_details',methods=['post'])
def register_details():
    connect=connection()
    cursor=connect.cursor()

    user_name=request.form['user_name']
    email_id=request.form['email_id']
    mobile_no=request.form['mobile_no']
    password=request.form['password_hash']
    password_hash=generate_password_hash(password)

    cursor.execute(''' INSERT INTO account_details(user_name,email_id,mobile_no,password_hash) VALUES(%s,%s,%s,%s)
''',(user_name,email_id,mobile_no,password_hash))

    connect.commit()

    cursor.close()
    connect.close()

    return redirect(url_for("logino"))
    

@app.route('/add_to_cart',methods=['post'])
def add_to_cart():
    data=request.get_json()
    product_id=data['product_id']
    connect=connection()
    cursor=connect.cursor()
    user_id=session.get('user_id')

    cursor.execute(''' Select * from cart where user_id=%s AND product_id=%s''',(user_id,product_id,))
    cart_details=cursor.fetchone()

    if cart_details:
        quantity=cart_details[3] + 1

        cursor.execute(''' UPDATE cart SET quantity=%s WHERE user_id=%s AND product_id=%s''',(quantity,user_id,product_id))
        connect.commit()
    else:
        cursor.execute(''' INSERT INTO cart(user_id,product_id) VALUES(%s,%s)''',(user_id,product_id))
        connect.commit()

    cursor.execute(
    "SELECT SUM(quantity) FROM cart WHERE user_id=%s",
    (user_id,))

    cart_count = cursor.fetchone()[0]


    cursor.close()
    connect.close()
    return jsonify({
        "success": True,
        "message": "Product added to cart",
        "quantity":cart_count
    }), 201

  

@app.route('/cart')
def cart():
    user_id=session.get('user_id')
    total=0
    discount=10
    connect=connection()
    cursor=connect.cursor()

    cursor.execute(''' SELECT p.id,p.name,p.price,p.image,c.id,c.quantity FROM cart c INNER JOIN products p ON c.product_id= p.id WHERE c.user_id=%s''',(user_id,))
    products=cursor.fetchall()
    total=0
    for item in products:
        price=item[2]
        quantity=item[5]

        total+=(price * quantity)
    discounted=((total * discount) / 100)
    after_discount=total-discounted

    cursor.close()
    connect.close()
    
    return render_template('cart.html',products=products,actual_total=total,total=after_discount,discount=discounted)


@app.route('/update_quantity',methods=['post'])
def update_quantity():
    data=request.get_json()
    new_qty=data['updated_quantity']
    produt_id=data['productid']
    connect=connection()
    cursor=connect.cursor()
    user_id=session.get('user_id')

    cursor.execute(''' UPDATE cart SET quantity=%s WHERE user_id=%s AND product_id=%s''',(new_qty,user_id,produt_id))
    connect.commit()

    cursor.execute(''' SELECT p.id,p.name,p.price,p.image,c.id,c.quantity FROM cart c INNER JOIN products p ON c.product_id= p.id WHERE c.user_id=%s''',(user_id,))
    products=cursor.fetchall()
    updated_total=0
    
    discount=10
    for item in products:
        price=item[2]
        quantity=item[5]

        updated_total+=(price * quantity)
    discounted=(updated_total * discount) / 100
    after_discount=updated_total-discounted
    cursor.close()
    connect.close()
    return jsonify( {
        "success": True,
        "updated_total":updated_total,
        "updated_discount":discounted,
        "updated_after_discount":after_discount
        })

@app.route('/delete_product_details',methods=['post'])
def delete_product_details():
    data=request.get_json()
    product_id=data['productid']

    connect=connection()
    cursor=connect.cursor()

    user_id=session.get('user_id')
    cursor.execute(" SELECT c.quantity,p.price FROM products p INNER JOIN cart c ON p.id=c.product_id WHERE (c.user_id=%s AND c.product_id=%s) ",(user_id,product_id))
    products=cursor.fetchall()
    updated_total=0
    
    discount=10
    for item in products:
        quantity=item[0]
        price=item[1]

        updated_total+=(quantity * price)
    discounted=(updated_total * discount) / 100
    after_discount=updated_total-discounted
    cursor.execute(''' DELETE FROM cart WHERE user_id=%s AND product_id=%s''',(user_id,product_id))
    connect.commit()


    cursor.close()
    connect.close()
    return jsonify( {
        "success": True,
        "updated_total":updated_total,
        "updated_discount":discounted,
        "updated_after_discount":after_discount
        })


@app.route('/save_address',methods=['post'])
def save_address():
    data=request.get_json()
    fullname=data["fullname"]
    phone=data['phone']
    street=data['street']
    city=data['city']
    state=data['state']
    pincode=data['pincode']  
    country=data['country']

    connect=connection()
    cursor=connect.cursor()
    user_id=session.get("user_id")
    cursor.execute(''' INSERT INTO address(user_id,fullname,phone,street,city,state,pincode,country) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',(user_id,fullname,phone,street,city,state,pincode,country))
    connect.commit()
    cursor.close()
    connect.close()
    return jsonify({'success':True})


@app.route("/about_us")
def about_us():
    return render_template("about.html")
@app.route("/selltous")
def selltous():
    return render_template("selltous.html")

@app.route('/buynow',methods=['post'])
def buynow():
    connect=connection()
    cursor=connect.cursor()
    data=request.get_json()
    user_id=session.get('user_id')
    cursor.execute("SELECT fullname,phone,street,city,state,pincode,country FROM address WHERE user_id=%s",(user_id,))
    address=cursor.fetchall()
    
    product_id=data['product_id']
    cursor.execute("SELECT name,price,image FROM products WHERE id=%s",(product_id,))
    product_details=cursor.fetchone()
    updated_total=0
    product_name=product_details[0]
    product_image=url_for('static',filename= product_details[2])
   
    discount=10
    
    quantity=1
    price=product_details[1]

    updated_total+=(quantity * price)
    discounted=(updated_total * discount) / 100
    after_discount=updated_total-discounted
    cursor.close()
    connect.close()
    
    return jsonify({
        "success":True,
        "product_name":product_name,
        "product_image":product_image,
        "product_price":price,
        "updated_total":updated_total,
        "updated_discount":discounted,
        "updated_after_discount":after_discount,
        "address":address
    })

@app.route('/address_details')
def address_details():
    connect=connection()
    cursor=connect.cursor()
    
    user_id=session.get('user_id')
    cursor.execute("SELECT fullname,phone,street,city,state,pincode,country FROM address WHERE user_id=%s",(user_id,))
    address=cursor.fetchall()
    cursor.close()
    connect.close()
    
    return jsonify({
        "success":True,
        "address":address
    })

if __name__=='__main__':
    app.run()










