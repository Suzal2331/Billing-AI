conversation = {
    "task": "",
    "data": {}
}


def start_task(task):
    conversation["task"] = task
    conversation["data"] = {}


def save(key, value):
    conversation["data"][key] = value


def get():
    return conversation


def clear():
    conversation["task"] = ""
    conversation["data"] = {}