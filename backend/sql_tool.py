import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "medical.db")


def execute_sql(query: str):
    """
    Executes SELECT, INSERT, UPDATE and DELETE queries.
    """

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:

        cursor.execute(query)

        sql_type = query.strip().split()[0].upper()

        # ==========================
        # SELECT
        # ==========================
        if sql_type == "SELECT":

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            conn.close()

            return {
                "type": "SELECT",
                "columns": columns,
                "rows": rows
            }

        # ==========================
        # INSERT
        # ==========================
        elif sql_type == "INSERT":

            conn.commit()

            inserted_id = cursor.lastrowid

            conn.close()

            return {
                "type": "INSERT",
                "message": "Record inserted successfully.",
                "last_id": inserted_id
            }

        # ==========================
        # UPDATE
        # ==========================
        elif sql_type == "UPDATE":

            conn.commit()

            updated = cursor.rowcount

            conn.close()

            return {
                "type": "UPDATE",
                "message": f"{updated} row(s) updated successfully."
            }

        # ==========================
        # DELETE
        # ==========================
        elif sql_type == "DELETE":

            conn.commit()

            deleted = cursor.rowcount

            conn.close()

            return {
                "type": "DELETE",
                "message": f"{deleted} row(s) deleted successfully."
            }

        # ==========================
        # OTHER
        # ==========================
        else:

            conn.commit()

            conn.close()

            return {
                "type": sql_type,
                "message": "Query executed successfully."
            }

    except Exception as e:

        conn.close()

        return {
            "error": str(e)
        }