# memory.py

conversation_memory = {
    "last_patient": None,
    "last_doctor": None,
    "last_medicine": None,
    "last_bill": None
}


def set_last_patient(name):
    conversation_memory["last_patient"] = name


def get_last_patient():
    return conversation_memory["last_patient"]


def set_last_doctor(name):
    conversation_memory["last_doctor"] = name


def get_last_doctor():
    return conversation_memory["last_doctor"]


def set_last_medicine(name):
    conversation_memory["last_medicine"] = name


def get_last_medicine():
    return conversation_memory["last_medicine"]


def set_last_bill(bill):
    conversation_memory["last_bill"] = bill


def get_last_bill():
    return conversation_memory["last_bill"]