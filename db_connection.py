import mysql.connector

def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Mrudul@1234567",
        database="mess_db"
    )
    return conn
