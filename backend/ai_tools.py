from memory import set_last_patient, get_last_patient

from langchain.tools import tool

from tools.db_tool import (
    add_patient,
    search_patient,
    create_bill,
    get_bill
)


# =====================================================
# Register Patient
# =====================================================

@tool
def register_patient(name: str):
    """
    Register a new patient.
    """

    patient = search_patient(name)

    if patient:
        set_last_patient(name)
        return f"✅ Patient '{name}' already exists."

    result = add_patient(
        name=name,
        age=30,
        gender="Male",
        doctor="Dr. Smith"
    )

    set_last_patient(name)

    return result


# =====================================================
# Find Patient
# =====================================================

@tool
def find_patient(name: str):
    """
    Search patient by name.
    """

    patient = search_patient(name)

    if patient is None:
        return f"❌ Patient '{name}' not found."

    set_last_patient(name)

    return f"""
✅ Patient Found

Patient ID : {patient[0]}
Name       : {patient[1]}
Age        : {patient[2]}
Gender     : {patient[3]}
Doctor     : {patient[4]}
"""


# =====================================================
# Generate Bill
# =====================================================

@tool
def generate_bill(
    consultation: float,
    medicine: float,
    lab: float,
    patient_name: str = ""
):
    """
    Generate a bill.

    If patient_name is not provided,
    automatically use the last registered patient.
    """

    # Automatically use last patient
    if not patient_name:
        patient_name = get_last_patient()

    if not patient_name:
        return "❌ No patient selected. Please register a patient first."

    patient = search_patient(patient_name)

    if patient is None:
        return f"❌ Patient '{patient_name}' not found."

    result = create_bill(
        patient_name,
        consultation,
        medicine,
        lab
    )

    return f"""
✅ Bill Generated Successfully

Patient : {patient_name}

Consultation : ₹{consultation:.2f}
Medicine     : ₹{medicine:.2f}
Lab          : ₹{lab:.2f}

{result}
"""


# =====================================================
# Fetch Bill
# =====================================================

@tool
def fetch_bill(patient_name: str = ""):
    """
    Fetch latest bill.
    """

    if not patient_name:
        patient_name = get_last_patient()

    if not patient_name:
        return "❌ No patient selected."

    bill = get_bill(patient_name)

    if bill is None:
        return f"❌ No bill found for '{patient_name}'."

    return f"""
🧾 Latest Bill

Bill ID      : {bill[0]}
Patient Name : {bill[1]}

Consultation : ₹{bill[2]:.2f}
Medicine     : ₹{bill[3]:.2f}
Lab          : ₹{bill[4]:.2f}

GST          : ₹{bill[5]:.2f}

Total        : ₹{bill[6]:.2f}
"""


# =====================================================
# Tools List
# =====================================================

tools = [
    register_patient,
    find_patient,
    generate_bill,
    fetch_bill,
]