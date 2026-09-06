"""
migrate_medicine_sales.py

Adds a `patient_name` column to the medicine_sales table. Without
this, questions like "what medicines has Sujal taken" are
fundamentally unanswerable — there was no way to connect a sale
to a patient at all.

Run this ONCE against your real database:
    python migrate_medicine_sales.py

Safe to run more than once — it checks whether the column already
exists before trying to add it.
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "medical.db")

# If your db isn't in a "database" subfolder, edit DB_PATH above,
# e.g. DB_PATH = os.path.join(BASE_DIR, "medical.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA table_info(medicine_sales)")
existing_columns = [row[1] for row in cur.fetchall()]

if "patient_name" in existing_columns:
    print("✅ patient_name column already exists. Nothing to do.")
else:
    cur.execute("ALTER TABLE medicine_sales ADD COLUMN patient_name TEXT")
    conn.commit()
    print("✅ patient_name column added to medicine_sales.")
    print("   Existing rows will have patient_name = NULL — they")
    print("   were recorded before this fix and can't be")
    print("   retroactively linked to a patient. New sales made")
    print("   through sales_agent.py will be linked going forward.")

conn.close()