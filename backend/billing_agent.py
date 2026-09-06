from tools.db_tool import create_bill
from tools.response import card
from memory import (
    set_last_bill,
    set_last_patient
)


def billing_agent(task, data):

    if task == "create_bill":

        patient_name = data["patient_name"]

        consultation = float(data["consultation"])
        medicine = float(data["medicine"])
        lab = float(data["lab"])

        # Fixed Doctor Fee
        doctor_fee = 450.00

        subtotal = consultation + medicine + lab + doctor_fee

        # GST 18%
        gst = round(subtotal * 0.18, 2)

        total = round(subtotal + gst, 2)

        bill_id, bill_date = create_bill(
            patient_name,
            consultation,
            medicine,
            lab,
            gst,
            total
        )

        # Save Memory
        set_last_patient(patient_name)

        set_last_bill({
            "patient_name": patient_name,
            "consultation": consultation,
            "medicine": medicine,
            "lab": lab,
            "doctor_fee": doctor_fee,
            "gst": gst,
            "total": total
        })

        text = f"""
============================================================
                 MEDICAL INVOICE
============================================================

🧾 Invoice Status : GENERATED

👤 Patient Name   : {patient_name}

------------------------------------------------------------

👨‍⚕ Consultation  : ₹{consultation:,.2f}
💊 Medicine       : ₹{medicine:,.2f}
🧪 Lab Charges    : ₹{lab:,.2f}
👨‍⚕ Doctor Fee    : ₹{doctor_fee:,.2f}

------------------------------------------------------------

Subtotal         : ₹{subtotal:,.2f}
GST (18%)        : ₹{gst:,.2f}

============================================================
💰 TOTAL AMOUNT  : ₹{total:,.2f}
============================================================

💳 Payment Status : PAID ✅

Thank you for choosing our hospital.
Get Well Soon ❤️

============================================================
"""

        structured = {
            "kind": "bill_generated",
            "title": "Medical Invoice",
            "bill": {
                "patient": patient_name,
                "billNo": str(bill_id),
                "date": bill_date,
                "items": [
                    {"name": "Consultation", "qty": 1, "price": consultation},
                    {"name": "Medicine", "qty": 1, "price": medicine},
                    {"name": "Lab Charges", "qty": 1, "price": lab},
                    {"name": "Doctor Fee", "qty": 1, "price": doctor_fee},
                ],
                "subtotal": subtotal,
                "gst": gst,
                "total": total,
                "paymentStatus": "Paid",
            },
        }

        return card(text, structured)

    return card("❌ Invalid Billing Task.")