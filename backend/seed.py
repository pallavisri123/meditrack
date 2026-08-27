"""Seeds departments, doctors and availability slots (idempotent)."""
from datetime import date, timedelta
from database import SessionLocal
import models as M

DEPARTMENTS = [
    ("General Medicine", "Primary care, fever, infections and routine check-ups"),
    ("Cardiology", "Heart, blood pressure and vascular care"),
    ("Orthopaedics", "Bones, joints, spine and sports injuries"),
    ("Paediatrics", "Child health, growth and immunisation"),
    ("Dermatology", "Skin, hair and nail treatments"),
    ("Neurology", "Brain, nerves, headache and epilepsy care"),
    ("ENT", "Ear, nose and throat specialists"),
    ("Gynaecology", "Women's health and maternity care"),
]

DOCTORS = [
    ("Dr. Ananya Rao", "General Medicine", "Internal Medicine", 12, 400),
    ("Dr. Vikram Menon", "General Medicine", "Diabetology", 9, 450),
    ("Dr. Sathish Kumar", "Cardiology", "Interventional Cardiology", 18, 900),
    ("Dr. Meera Iyer", "Cardiology", "Electrophysiology", 11, 850),
    ("Dr. Rahul Deshpande", "Orthopaedics", "Joint Replacement", 15, 700),
    ("Dr. Nisha Verma", "Orthopaedics", "Sports Injury", 8, 600),
    ("Dr. Kavya Nair", "Paediatrics", "Neonatology", 10, 500),
    ("Dr. Arjun Pillai", "Dermatology", "Cosmetic Dermatology", 7, 550),
    ("Dr. Sneha Kulkarni", "Neurology", "Epilepsy & Headache", 14, 950),
    ("Dr. Imran Sheikh", "ENT", "Head & Neck Surgery", 13, 600),
    ("Dr. Priya Sundaram", "Gynaecology", "High-risk Pregnancy", 16, 800),
]

TIMES = ["09:00", "09:30", "10:00", "10:30", "11:00", "12:00", "16:00", "16:30", "17:00", "18:00"]
BLOOD = {"A+": 14, "A-": 4, "B+": 21, "B-": 3, "AB+": 8, "AB-": 0, "O+": 26, "O-": 5}


def run_seed():
    db = SessionLocal()
    try:
        if not db.query(M.Department).count():
            for name, desc in DEPARTMENTS:
                db.add(M.Department(name=name, description=desc))
            db.commit()
        dept_map = {d.name: d.id for d in db.query(M.Department).all()}

        if not db.query(M.Doctor).count():
            for i, (name, dept, spec, exp, fee) in enumerate(DOCTORS, start=1):
                db.add(M.Doctor(doctor_code=f"DR{i:04d}", name=name, department_id=dept_map[dept],
                                specialization=spec, experience_years=exp, consultation_fee=fee,
                                rating=round(4.2 + (i % 6) * 0.12, 1),
                                bio=f"{spec} consultant with {exp} years of clinical experience at MediTrack Hospital."))
            db.commit()

        today = date.today()
        for doc in db.query(M.Doctor).all():
            existing = {(s.slot_date, s.slot_time) for s in doc.slots}
            for offset in range(0, 10):
                d = today + timedelta(days=offset)
                if d.weekday() == 6:  # Sunday off
                    continue
                for t in TIMES[(doc.id % 3):(doc.id % 3) + 7]:
                    if (d, t) not in existing:
                        db.add(M.DoctorAvailability(doctor_id=doc.id, day_name=d.strftime("%A"),
                                                    slot_date=d, slot_time=t))
        db.commit()

        if not db.query(M.BloodStock).count():
            for g, u in BLOOD.items():
                db.add(M.BloodStock(blood_group=g, units=u))
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
    print("Seeded.")
