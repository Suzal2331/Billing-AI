from datetime import datetime

from tools.db_tool import add_patient, search_patient
from tools.response import card


def _patient_row(patient):
    """
    Converts a raw (id, name, age, gender, doctor) DB row into the
    PatientRow shape the frontend expects (see src/lib/types.ts).

    The patients table doesn't store phone/status/lastVisit — those
    columns don't exist anywhere in this schema. Filling in honest
    placeholders rather than omitting the fields, since the
    frontend's PatientRow type requires them to render. If real
    columns for these get added later, swap the placeholders here.
    """
    return {
        "id": patient[0],
        "name": patient[1],
        "age": patient[2],
        "gender": patient[3],
        "phone": "N/A",
        "doctor": patient[4],
        "status": "Active",
        "lastVisit": datetime.now().strftime("%Y-%m-%d"),
    }


def patient_agent(task, data):
    """
    Patient Agent

    Tasks:
        register
        search
    """

    if task == "register":

        print("\n========== PATIENT AGENT ==========")
        print("Received Data :", data)

        existing_patient = search_patient(data["name"])

        print("Search Result :", existing_patient)

        # ===========================================
        # PATIENT ALREADY EXISTS
        # ===========================================

        if existing_patient is not None:

            print("Duplicate Found")

            text = f"""
============================================================
               PATIENT ALREADY EXISTS
============================================================

👤 Name      : {existing_patient[1]}
🎂 Age       : {existing_patient[2]}
⚧ Gender    : {existing_patient[3]}
👨‍⚕ Doctor   : {existing_patient[4]}

⚠ This patient is already registered.

============================================================
"""
            # No structured card here — this is a warning, not a
            # successful registration, so it shouldn't render as
            # the same "success" card a fresh registration gets.
            return card(text)

        # ===========================================
        # REGISTER NEW PATIENT
        # ===========================================

        print("No Duplicate Found")
        print("Registering Patient...")

        add_patient(
            data["name"],
            data["age"],
            data["gender"],
            data["doctor"]
        )

        print("Registration Completed")

        # Fetch newly inserted patient
        patient = search_patient(data["name"])

        text = f"""
============================================================
            PATIENT REGISTERED SUCCESSFULLY
============================================================

🆔 Patient ID : {patient[0]}
👤 Name       : {patient[1]}
🎂 Age        : {patient[2]}
⚧ Gender      : {patient[3]}
👨‍⚕ Doctor     : {patient[4]}

✔ Registration Completed Successfully

============================================================
"""

        return card(text, {
            "kind": "patient_registered",
            "title": "Patient Registered",
            "patient": _patient_row(patient),
        })

    # ===========================================
    # SEARCH PATIENT
    # ===========================================

    elif task == "search":

        patient = search_patient(data["name"])

        if patient:

            text = f"""
============================================================
                 PATIENT DETAILS
============================================================

🆔 Patient ID : {patient[0]}
👤 Name       : {patient[1]}
🎂 Age        : {patient[2]}
⚧ Gender      : {patient[3]}
👨‍⚕ Doctor     : {patient[4]}

============================================================
"""
            return card(text, {
                "kind": "patient_list",
                "title": "Patient Details",
                "patients": [_patient_row(patient)],
            })

        text = """
============================================================
                 PATIENT NOT FOUND
============================================================

❌ No patient exists with that name.

============================================================
"""
        return card(text)

    return card("❌ Invalid Patient Task.")