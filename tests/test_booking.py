from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from booking import BookingStore

@pytest.fixture
def store(tmp_path):
    s=BookingStore(tmp_path/'test.sqlite3')
    s.now=lambda:datetime(2026,9,21,8,tzinfo=s.tz)
    return s

def test_weekends_hours_and_past(store):
    assert store.availability('2026-09-26')['slots']==[]
    assert len(store.availability('2026-09-21')['slots'])==16
    for slot in ['2026-09-26T10:00:00+06:00','2026-09-21T17:00:00+06:00','2026-09-21T09:15:00+06:00','2026-09-20T09:00:00+06:00','2026-09-21T09:00:00']:
        with pytest.raises(ValueError):store.hold('a',slot)

def test_confirmation_and_persistence(store):
    slot=store.availability('2026-09-21')['slots'][0]
    with pytest.raises(ValueError):store.confirm('a',slot,'Headache','+8801712345678', patient_name='John Smith')
    store.hold('a',slot)
    with pytest.raises(ValueError):store.confirm('b',slot,'Headache','+8801712345678', patient_name='John Smith')
    with pytest.raises(ValueError):store.confirm('a',slot,'Headache','123', patient_name='John Smith')
    assert store.confirm('a',slot,'Headache','+8801712345678', patient_name='John Smith')['status']=='booked'
    store.release('a')
    assert slot not in store.availability('2026-09-21')['slots']
    assert store.confirm('a',slot,'Headache','+8801712345678', patient_name='John Smith')['status']=='booked'

def test_race_and_release(store):
    slot=store.availability('2026-09-21')['slots'][0]
    def attempt(owner):
        try:store.hold(owner,slot);return owner
        except ValueError:return None
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,['a','b']))
    assert len([x for x in results if x])==1
    store.release(next(x for x in results if x))
    assert slot in store.availability('2026-09-21')['slots']

def test_expired_hold_and_change(store):
    a,b=store.availability('2026-09-21')['slots'][:2]
    store.hold('a',a);store.hold('a',b)
    assert a in store.availability('2026-09-21')['slots']
    old=store.now();store.now=lambda:old+timedelta(minutes=16)
    with pytest.raises(ValueError):store.confirm('a',b,'declined','01234567890', patient_name='John Smith')
    store.hold('b',b)

def test_name_reference_and_retry(store):
    slot=store.availability('2026-09-21')['slots'][0]
    store.hold('a',slot)
    with pytest.raises(ValueError):
        store.confirm('a',slot,'declined','01234567890',' ')
    result=store.confirm('a',slot,'declined','01234567890','John Smith')
    assert result['patient_name']=='John Smith'
    assert result['reference'].startswith('LB-')
    assert store.confirm('a',slot,'declined','01234567890','John Smith')==result
    with store.connect() as db:
        assert db.execute('SELECT patient_name,reference FROM appointments WHERE slot=?',(slot,)).fetchone()==('John Smith',result['reference'])

def test_migration_preserves_existing_booking(tmp_path):
    import sqlite3
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE appointments(slot TEXT PRIMARY KEY,owner TEXT,state TEXT,expires REAL,reason TEXT,phone TEXT)')
        db.execute("INSERT INTO appointments VALUES('2026-09-28T09:00:00+06:00','old','booked',NULL,'declined','01234567890')")
    migrated=BookingStore(path)
    with migrated.connect() as db:
        assert db.execute('SELECT state,reason FROM appointments').fetchone()==('booked','declined')
        assert {'patient_name','reference'} <= {row[1] for row in db.execute('PRAGMA table_info(appointments)')}
