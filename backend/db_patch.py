import sqlite3
try:
    conn = sqlite3.connect('backend_data.db')
    conn.execute("ALTER TABLE forwarding_config ADD COLUMN post_link VARCHAR DEFAULT ''")
    conn.commit()
    print("Column added")
except Exception as e:
    print(e)
finally:
    conn.close()
