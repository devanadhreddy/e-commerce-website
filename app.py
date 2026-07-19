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
from werkzeug.security import generate_password_hash

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
    return render_template('index.html')

@app.route('/category/<category_name>')
def category(category_name):
    connect=connection()
    cursor=connect.cursor()
    cursor.execute(
        '''SELECT * FROM ecommerce.products WHERE category_name=%s''',(category_name,)
    )

    products=cursor.fetchall()
    cursor.close()
    connect.close()

    return render_template("category.html",products=products)

@app.route('/logino')
def logino():
    return render_template('login.html',login=True)



def send_otp_email(username, otp):
    sender_email = os.getenv("SENDER_EMAIL")
    app_password =  os.getenv("GOOGLE_APP_PASSWORD")

    msg = MIMEText(f"Your OTP is: {otp}")
    msg["Subject"] = "Email Verification OTP"
    msg["From"] = sender_email
    msg["To"] = username

    with smtplib.SMTP_SSL("smtp.gmail.com", 485,timeout=10) as server:
        
        server.login(sender_email, app_password)
        server.send_message(msg)

@app.route('/login_details',methods=['post'])
def login_details():
    
    connect=connection()
    cursor=connect.cursor()
    
    
    username=request.form["username"]
    cursor.execute(''' SELECT id,user_name FROM ecommerce.account_details WHERE email_id=%s''',(username,))

    user_details=cursor.fetchall()
    
    if user_details:

        session["pending_login"]=username
        otp=str(random.randint(100000,999999))
        query='''INSERT  INTO login_details (email_mobile,otp) VALUES(%s,%s)'''
        cursor.execute(query,(username,otp))
        connect.commit()

        send_otp_email(username,otp)

        cursor.close()
        connect.close()


        return render_template('login.html',verify=True)
    else:
        return render_template('login.html',login=True,error_username="You Do Not Have An Account With This username--Register One")

@app.route('/verify_otp',methods=['post'])
def verify_otp():
    username=session.get("pending_login")
   

    entered_otp=request.form['otp']
    
    connect=connection()
    cursor=connect.cursor()

    query=''' SELECT otp FROM ecommerce.login_details WHERE email_mobile=%s ORDER BY id DESC LIMIT 1'''

    cursor.execute(query,(username,))
    stored_otp=cursor.fetchone()
    stored_otp_2=str(stored_otp[0]).strip()
    

    if entered_otp==stored_otp_2:
        cursor.execute(''' SELECT id FROM ecommerce.account_details WHERE email_id=%s''',(username,))
        user_id=cursor.fetchone()
        
        session['user_id']=user_id[0]
        session['email_id']=username    ## otp should be deleted make sure tgis to remainder
        cursor.execute(''' DELETE FROM ecommerce.login_details WHERE email_mobile=%s''',(username,))
        connect.commit()

        cursor.close()
        connect.close()
        session.pop('pending_login', None)
        return redirect('/')

    else: 
        return render_template("login.html",invalid_otp="Invalid OTP Try Again",verify=True)



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

    return render_template('login.html',error_username="Registered Succesfully Now Sign In")
    

@app.route('/add_to_cart',methods=['post'])
def add_to_cart():
    data=request.get_json()
    product_id=data['product_id']
    connect=connection()
    cursor=connect.cursor()
    user_id=session.get('user_id')

    cursor.execute(''' Select * from ecommerce.cart where user_id=%s AND product_id=%s''',(user_id,product_id,))
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

    cursor.execute(''' UPDATE ecommerce.cart SET quantity=%s WHERE user_id=%s AND product_id=%s''',(new_qty,user_id,produt_id))
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
    cursor.execute(" SELECT c.quantity,p.price FROM ecommerce.products p INNER JOIN cart c ON p.id=c.product_id WHERE (c.user_id=%s AND c.product_id=%s) ",(user_id,product_id))
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
    cursor.execute(''' INSERT INTO ecommerce.address(user_id,fullname,phone,street,city,state,pincode,country) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',(user_id,fullname,phone,street,city,state,pincode,country))
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
    cursor.execute("SELECT fullname,phone,street,city,state,pincode,country FROM ecommerce.address WHERE user_id=%s",(user_id,))
    address=cursor.fetchall()
    
    product_id=data['product_id']
    cursor.execute("SELECT name,price,image FROM ecommerce.products WHERE id=%s",(product_id,))
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
    cursor.execute("SELECT fullname,phone,street,city,state,pincode,country FROM ecommerce.address WHERE user_id=%s",(user_id,))
    address=cursor.fetchall()
    cursor.close()
    connect.close()
    
    return jsonify({
        "success":True,
        "address":address
    })

if __name__=='__main__':
    app.run()










