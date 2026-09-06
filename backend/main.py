import agents.sql_agent as m
print(m.__file__)
print("################################")
print("NEW AGENTIC AI MAIN IS RUNNING")
print("################################")
from orchestrator import orchestrator

print("=" * 60)
print("🏥 Medical Billing Agentic AI")
print("=" * 60)

while True:

    query = input("\n👤 You : ")

    if query.lower() == "exit":
        break

    try:

        answer = orchestrator(query)

        # CHANGED: orchestrator() now returns {"text": ..., "structured": ...}
        # instead of a bare string, so the API layer (app.py) can also
        # get structured card data. The terminal only ever wanted the
        # text, so this is the only line that needed to change.
        print("\n🤖 AI :")
        print(answer["text"])

    except Exception as e:

        print(e)