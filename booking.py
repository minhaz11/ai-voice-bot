"""Transactional appointment holds and bookings; no patient data in logs."""
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class BookingStore:
    def __init__(self, path, timezone='Asia/Dhaka', open_hour=9, close_hour=17,
                 slot_minutes=30, weekends=(5, 6)):
        self.path, self.tz = str(path), ZoneInfo(timezone)
        self.open_hour, self.close_hour = open_hour, close_hour
        self.slot_minutes, self.weekends = slot_minutes, weekends
        if not (0 <= open_hour < close_hour <= 24 and 5 <= slot_minutes <= 120):
            raise ValueError('Invalid clinic hours or slot duration')
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS appointments (
                slot TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL,
                expires REAL, reason TEXT, phone TEXT)''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(appointments)')}
            for column in ('patient_name', 'reference'):
                if column not in columns:
                    db.execute(f'ALTER TABLE appointments ADD COLUMN {column} TEXT')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS booking_reference ON appointments(reference)')
        os.chmod(self.path, 0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def now(self):
        return datetime.now(self.tz)

    def validate_slot(self, slot):
        dt = datetime.fromisoformat(slot)
        if dt.tzinfo is None:
            raise ValueError('Use a datetime with the clinic timezone offset')
        dt = dt.astimezone(self.tz)
        minutes = dt.hour * 60 + dt.minute
        if (dt <= self.now() or dt.date() > (self.now() + timedelta(days=30)).date()
                or dt.weekday() in self.weekends or dt.second or dt.microsecond
                or minutes < self.open_hour * 60
                or minutes + self.slot_minutes > self.close_hour * 60
                or (minutes - self.open_hour * 60) % self.slot_minutes):
            raise ValueError('Choose a future available weekday slot within the next 30 days')
        return dt.isoformat()

    def availability(self, date):
        day = datetime.strptime(date, '%Y-%m-%d').date()
        if day < self.now().date() or day > (self.now() + timedelta(days=30)).date():
            raise ValueError('Choose a date within the next 30 days')
        with self.connect() as db:
            taken = {r[0] for r in db.execute(
                "SELECT slot FROM appointments WHERE state='booked' OR expires > ?",
                (self.now().timestamp(),))}
        slots = []
        if day.weekday() not in self.weekends:
            for minute in range(self.open_hour * 60, self.close_hour * 60 - self.slot_minutes + 1, self.slot_minutes):
                dt = datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=self.tz)
                if dt > self.now() and dt.isoformat() not in taken:
                    slots.append(dt.isoformat())
        return {'date': date, 'timezone': str(self.tz), 'slots': slots}

    def hold(self, owner, slot):
        slot = self.validate_slot(slot)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("DELETE FROM appointments WHERE state='held' AND expires <= ?", (self.now().timestamp(),))
            existing = db.execute('SELECT owner,state FROM appointments WHERE slot=?', (slot,)).fetchone()
            if existing and existing != (owner, 'held'):
                raise ValueError('That time was just taken. Offer another available slot.')
            db.execute("DELETE FROM appointments WHERE owner=? AND state='held'", (owner,))
            db.execute("INSERT INTO appointments(slot,owner,state,expires) VALUES (?,?,'held',?)",
                       (slot, owner, (self.now() + timedelta(minutes=15)).timestamp()))
        return {'status': 'reserved', 'slot': slot, 'expires_in_minutes': 15}

    def confirm(self, owner, slot, reason, phone, patient_name):
        slot = self.validate_slot(slot)
        if not isinstance(patient_name, str) or not 1 <= len(patient_name.strip()) <= 120:
            raise ValueError('Ask for the patient name')
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError('Ask for a brief visit reason; declined is acceptable')
        if not isinstance(phone, str) or not re.fullmatch(r'\+?[\d ()-]{7,30}', phone) or not 7 <= len(re.sub(r'\D', '', phone)) <= 15:
            raise ValueError('Ask the caller to repeat a valid phone number including area/country code')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT owner,state,expires,reason,phone,patient_name,reference FROM appointments WHERE slot=?', (slot,)).fetchone()
            if row and row[0] == owner and row[1] == 'booked':
                return {'status': 'booked', 'slot': slot, 'reason': row[3], 'phone': row[4], 'patient_name': row[5], 'reference': row[6]}
            if not row or row[0] != owner or row[1] != 'held' or row[2] <= self.now().timestamp():
                raise ValueError('Reservation expired. Check and reserve the time again, then reconfirm.')
            reference = 'LB-' + uuid.uuid4().hex[:10].upper()
            db.execute("UPDATE appointments SET state='booked',expires=NULL,reason=?,phone=?,patient_name=?,reference=? WHERE slot=?",
                       (reason.strip(), phone, patient_name.strip(), reference, slot))
        return {'status': 'booked', 'slot': slot, 'reason': reason.strip(), 'phone': phone, 'patient_name': patient_name.strip(), 'reference': reference}

    def release(self, owner):
        with self.connect() as db:
            db.execute("DELETE FROM appointments WHERE owner=? AND state='held'", (owner,))
