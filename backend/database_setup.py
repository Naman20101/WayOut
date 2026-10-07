"""Create tables in an EXISTING database; never reset other databases."""
from pathlib import Path
from backend.db import connection

def setup():
    with connection() as conn:
        cur=conn.cursor()
        for statement in (Path(__file__).parent/'database/schema.sql').read_text().split(';'):
            if statement.strip():cur.execute(statement)
        cur.close()
    print('WAYOUT tables ready.')
if __name__=='__main__':setup()
