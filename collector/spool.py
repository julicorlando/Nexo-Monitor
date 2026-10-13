"""Persistent FIFO, cached config and idempotent batch IDs. Single collector process."""
import sqlite3,json,uuid,time
from datetime import datetime,timezone
class Spool:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, created REAL, payload TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, payload TEXT)")
    def cache(self,devices):
        self.db.execute("INSERT OR REPLACE INTO config VALUES (1,?)",(json.dumps(devices),));self.db.commit()
    def devices(self):
        row=self.db.execute("SELECT payload FROM config WHERE id=1").fetchone()
        return json.loads(row[0]) if row else []
    def enqueue(self,results):
        payload={"batch_id":str(uuid.uuid4()),"observed_at":datetime.now(timezone.utc).isoformat(),"results":results}
        self.db.execute("DELETE FROM batches WHERE created<?",(time.time()-6*86400,))
        self.db.execute("INSERT INTO batches VALUES (?,?,?)",(payload["batch_id"],time.time(),json.dumps(payload)))
        # Bounded disk use, retains latest 10,000 batches. Evictions logged by caller.
        excess=self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]-10000
        if excess>0:self.db.execute("DELETE FROM batches WHERE id IN (SELECT id FROM batches ORDER BY created LIMIT ?)",(excess,))
        self.db.commit()
        return max(0,excess)
    def flush(self,send,limit=100):
        for identifier,payload in self.db.execute("SELECT id,payload FROM batches ORDER BY created LIMIT ?",(limit,)).fetchall():
            send(json.loads(payload))
            self.db.execute("DELETE FROM batches WHERE id=?",(identifier,));self.db.commit()
