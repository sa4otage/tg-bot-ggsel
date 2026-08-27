import sqlite3
db = sqlite3.connect('bot.db')
db.execute('DELETE FROM request_logs')
db.execute('DELETE FROM pending_codes')
db.commit()
print('Лимиты сброшены')
