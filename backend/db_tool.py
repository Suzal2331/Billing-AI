import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "medical.db")
print("DATABASE:", DB_PATH)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def connect_db():
    return sqlite3.connect(DB_PATH)


# ==========================================
# PATIENT FUNCTIONS
# ==========================================

def search_patient(name):

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM patients
    WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))
    LIMIT 1
    """, (name.strip(),))

    patient = cursor.fetchone()

    conn.close()

    return patient


def patient_exists(name):
    return search_patient(name) is not None


def add_patient(name, age, gender, doctor):

    if patient_exists(name):
        return f"⚠️ Patient '{name}' already exists."

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO patients
    (
        name,
        age,
        gender,
        doctor
    )
    VALUES
    (
        ?,?,?,?
    )
    """,
    (
        name.strip(),
        age,
        gender,
        doctor
    ))

    conn.commit()
    conn.close()

    return f"✅ Patient '{name}' registered successfully."


# ==========================================
# BILL FUNCTIONS
# ==========================================

def create_bill(patient_name, consultation, medicine, lab, gst, total):

    conn = connect_db()
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO bills
    (
        patient_name,
        consultation,
        medicine,
        lab,
        gst,
        total,
        created_at
    )
    VALUES
    (
        ?,?,?,?,?,?,?
    )
    """,
    (
        patient_name,
        consultation,
        medicine,
        lab,
        gst,
        total,
        today
    ))

    conn.commit()

    bill_id = cursor.lastrowid

    conn.close()

    # CHANGED: previously returned bare `True`. billing_agent.py's
    # only call site never checked/used the return value, so this
    # is safe to change — now returns (bill_id, date) so
    # billing_agent.py can build a structured bill card (bill number
    # + date) without a second round-trip query. Still truthy (a
    # non-empty tuple), so nothing relying on "was this truthy?"
    # breaks either.
    return (bill_id, today)


def get_bill(patient_name):

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM bills
    WHERE TRIM(LOWER(patient_name)) = TRIM(LOWER(?))
    ORDER BY bill_id DESC
    LIMIT 1
    """, (patient_name.strip(),))

    bill = cursor.fetchone()

    conn.close()

    return bill


# ==========================================
# MEDICINE SALES FUNCTIONS
# ==========================================

def sell_medicine(medicine_name, quantity):

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT stock, price
    FROM medicines
    WHERE TRIM(LOWER(medicine_name)) = TRIM(LOWER(?))
    """, (medicine_name.strip(),))

    medicine = cursor.fetchone()

    if medicine is None:
        conn.close()
        return {
            "success": False,
            "message": "❌ Medicine not found."
        }

    stock = medicine[0]
    price = medicine[1]

    if stock < quantity:
        conn.close()
        return {
            "success": False,
            "message": f"❌ Only {stock} units available."
        }

    remaining_stock = stock - quantity
    amount = price * quantity

    cursor.execute("""
    UPDATE medicines
    SET stock=?
    WHERE TRIM(LOWER(medicine_name)) = TRIM(LOWER(?))
    """, (remaining_stock, medicine_name.strip()))

    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO medicine_sales
    (
        medicine_name,
        quantity,
        amount,
        sale_date
    )
    VALUES
    (
        ?,?,?,?
    )
    """,
    (
        medicine_name.strip(),
        quantity,
        amount,
        today
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "medicine": medicine_name,
        "quantity": quantity,
        "amount": amount,
        "remaining_stock": remaining_stock
    }