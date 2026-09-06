"""
cleanup_db.py

Run this against your REAL database (the one main.py actually uses,
at database/medical.db), not a copy. It:

  1. Shows you what it's about to delete FIRST (dry run).
  2. Only deletes after you confirm.

Usage:
    python cleanup_db.py
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "medical.db")

# If your db isn't in a "database" subfolder, edit DB_PATH above,
# e.g. DB_PATH = os.path.join(BASE_DIR, "medical.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()


def find_junk_bills():
    cur.execute("""
        SELECT bill_id, patient_name, total, created_at
        FROM bills
        WHERE patient_name IS NULL OR TRIM(patient_name) = ''
    """)
    return cur.fetchall()


def find_junk_patients():
    cur.execute("SELECT id, name, age, gender, doctor FROM patients")
    rows = cur.fetchall()

    junk = []

    for row in rows:
        id_, name, age, gender, doctor = row

        is_junk = False

        # Missing critical fields
        if age is None or gender is None or doctor is None:
            is_junk = True

        # Doctor field contains a shell command / path (corrupted insert)
        if doctor and any(marker in str(doctor) for marker in
                           ["python.exe", "C:/", "C:\\", "&", ".py"]):
            is_junk = True

        # Name field looks like a sentence/instruction, not a person's name
        if name and len(name.split()) > 4:
            is_junk = True

        # Non-numeric "age" that slipped through as text (e.g. "yes")
        if isinstance(age, str) and not age.strip().lstrip("-").isdigit():
            is_junk = True

        # Age of 0 with blank gender/doctor (clearly a bad test insert)
        if age == 0 and (not gender or not doctor):
            is_junk = True

        if is_junk:
            junk.append(row)

    return junk


def find_duplicate_patients():
    """
    Finds patient rows that are exact duplicates of each other
    (same name, age, gender, doctor — case-insensitive on the text
    fields). Keeps the oldest (lowest id) row in each group and
    flags the rest for deletion.

    These don't look like "junk" individually — every field is
    valid — so find_junk_patients() above won't catch them. But a
    duplicate patient row multiplies every JOIN result against
    that patient (e.g. "what medicines has X taken" returning the
    same purchase N times, once per duplicate row), so they need
    their own detection pass.
    """
    cur.execute("SELECT id, name, age, gender, doctor FROM patients ORDER BY id")
    rows = cur.fetchall()

    groups = {}

    for row in rows:
        id_, name, age, gender, doctor = row
        key = (
            (name or "").strip().lower(),
            age,
            (gender or "").strip().lower(),
            (doctor or "").strip().lower(),
        )
        groups.setdefault(key, []).append(row)

    duplicates = []

    for key, group_rows in groups.items():
        if len(group_rows) > 1:
            # Keep the first (lowest id, since rows are ORDER BY id),
            # flag the rest.
            duplicates.extend(group_rows[1:])

    return duplicates


def main():
    print(f"Connected to: {DB_PATH}\n")

    junk_bills = find_junk_bills()
    junk_patients = find_junk_patients()
    duplicate_patients = find_duplicate_patients()

    print("=" * 60)
    print(f"BILLS with empty patient_name ({len(junk_bills)} found)")
    print("=" * 60)
    for row in junk_bills:
        print(row)

    print()
    print("=" * 60)
    print(f"JUNK / CORRUPTED PATIENT ROWS ({len(junk_patients)} found)")
    print("=" * 60)
    for row in junk_patients:
        print(row)

    print()
    print("=" * 60)
    print(f"DUPLICATE PATIENT ROWS ({len(duplicate_patients)} found)")
    print("=" * 60)
    print("(same name+age+gender+doctor as an earlier row — the")
    print(" earlier/lowest-id row in each group is kept)")
    for row in duplicate_patients:
        print(row)

    # Merge junk + duplicate patient ids, avoiding double-deletion
    # if a row happens to be flagged by both passes.
    patient_ids_to_delete = {row[0] for row in junk_patients}
    patient_ids_to_delete.update(row[0] for row in duplicate_patients)

    if not junk_bills and not patient_ids_to_delete:
        print("\nNothing to clean. Database looks fine.")
        conn.close()
        return

    print()
    answer = input(
        f"\nDelete {len(junk_bills)} bill(s) and "
        f"{len(patient_ids_to_delete)} patient row(s) shown above? [y/N]: "
    )

    if answer.strip().lower() != "y":
        print("Cancelled. Nothing was deleted.")
        conn.close()
        return

    for bill_id, *_ in junk_bills:
        cur.execute("DELETE FROM bills WHERE bill_id = ?", (bill_id,))

    for patient_id in patient_ids_to_delete:
        cur.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

    conn.commit()
    conn.close()

    print("\n✅ Cleanup complete.")


if __name__ == "__main__":
    main()