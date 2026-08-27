from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
import os

from database import Base, engine, get_db
import models as M
import auth as A
import notification_service as NS
import push_service as PS

app = FastAPI(title="MediTrack API", version="1.0.0",
              description="Integrated Patient Care Management System - patient facing API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class PatientIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    dob: date
    age: int = Field(ge=0, le=120)
    gender: str
    blood_group: str
    phone: str = Field(min_length=10, max_length=15)
    email: EmailStr
    address: str = ""
    emergency_contact_name: str
    emergency_contact_number: str = Field(min_length=10, max_length=15)
    allergies: str = ""
    conditions: str = ""
    previous_history: str = ""
    current_medications: str = ""
    photo: str = ""

    @field_validator("phone", "emergency_contact_number")
    @classmethod
    def digits(cls, v):
        cleaned = v.replace(" ", "").replace("-", "").replace("+", "")
        if not cleaned.isdigit():
            raise ValueError("Phone number must contain digits only")
        return v


class MedicineIn(BaseModel):
    medicine: str
    dosage: str = ""
    frequency: str = ""
    duration: str = ""
    notes: str = ""


class ConsultationIn(BaseModel):
    appointment_id: int
    symptoms: str
    diagnosis: str
    treatment: str
    notes: str = ""
    followup_date: Optional[date] = None
    instructions: str = ""
    medicines: List[MedicineIn] = []


class AppointmentIn(BaseModel):
    patient_id: int
    doctor_id: int
    slot_date: date
    slot_time: str
    reason: str = ""


class AmbulanceIn(BaseModel):
    patient_id: int
    pickup_address: str
    contact_number: str
    emergency_type: str = "General"


class LabTestIn(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None
    consultation_id: Optional[int] = None
    test_name: str
    status: str = "Pending"


class LabTestStatusIn(BaseModel):
    status: str
    result_summary: str = ""


class BillItemIn(BaseModel):
    description: str
    category: str = "Other"
    quantity: int = 1
    unit_price: float = 0.0


class BillIn(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None
    appointment_id: Optional[int] = None
    consultation_id: Optional[int] = None
    items: List[BillItemIn]
    discount: float = 0.0
    tax_percent: float = 0.0
    notes: str = ""


class PaymentIn(BaseModel):
    bill_id: int
    amount: float
    method: str = "Cash"  # UPI / Card / NetBanking / Cash / Online


class PushSubscribeIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushUnsubscribeIn(BaseModel):
    endpoint: str


# --------------------------------------------------------------------------
# Auth schemas
# --------------------------------------------------------------------------
class SignupIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    mobile: str = Field(min_length=10, max_length=15)
    dob: date
    gender: str
    password: str
    confirm_password: str
    accept_terms: bool = True

    @field_validator("mobile")
    @classmethod
    def digits(cls, v):
        cleaned = v.replace(" ", "").replace("-", "").replace("+", "")
        if not cleaned.isdigit():
            raise ValueError("Mobile number must contain digits only")
        return v

    @field_validator("gender")
    @classmethod
    def gender_ok(cls, v):
        if v not in ("Male", "Female", "Other"):
            raise ValueError("Select a valid gender")
        return v

    @field_validator("accept_terms")
    @classmethod
    def terms_ok(cls, v):
        if not v:
            raise ValueError("You must accept the Terms & Conditions to create an account")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str
    confirm_password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def next_code(db: Session, model, field: str, prefix: str, width: int = 4) -> str:
    count = db.query(func.count(model.id)).scalar() or 0
    while True:
        count += 1
        code = f"{prefix}{count:0{width}d}"
        if not db.query(model).filter(getattr(model, field) == code).first():
            return code


def log_history(db: Session, patient_id: int, event_type: str, title: str, detail: str = ""):
    db.add(M.MedicalHistory(patient_id=patient_id, event_type=event_type, title=title, detail=detail))


def notify(db: Session, patient_id: int, message: str, category: str = "info",
          priority: str = "normal", email: bool = False, sms: bool = False, subject: str = None,
          push: bool = True):
    channel = "in_app"
    if email or sms:
        patient = db.get(M.Patient, patient_id)
        if patient:
            channel = NS.dispatch(patient, message, subject or "MediTrack Notification", email, sms)
    if push:
        sent = PS.send_push_to_patient(db, patient_id, subject or "MediTrack", message)
        if sent:
            channel += "+push"
    db.add(M.Notification(patient_id=patient_id, message=message, category=category,
                          priority=priority, channel=channel))


def completion(p: M.Patient) -> int:
    fields = [p.full_name, p.dob, p.gender, p.blood_group, p.phone, p.email, p.address,
              p.emergency_contact_name, p.emergency_contact_number, p.allergies,
              p.conditions, p.previous_history, p.current_medications, p.photo]
    filled = sum(1 for f in fields if f not in (None, "", []))
    return round(filled / len(fields) * 100)


def patient_json(p: M.Patient) -> dict:
    return {
        "id": p.id, "patient_code": p.patient_code, "full_name": p.full_name,
        "dob": str(p.dob), "age": p.age, "gender": p.gender, "blood_group": p.blood_group,
        "phone": p.phone, "email": p.email, "address": p.address,
        "emergency_contact_name": p.emergency_contact_name,
        "emergency_contact_number": p.emergency_contact_number,
        "allergies": p.allergies, "conditions": p.conditions,
        "previous_history": p.previous_history, "current_medications": p.current_medications,
        "photo": p.photo, "registered_on": p.registered_on.strftime("%d %b %Y"),
        "completion": completion(p),
    }


def doctor_json(d: M.Doctor) -> dict:
    return {
        "id": d.id, "doctor_code": d.doctor_code, "name": d.name,
        "department": d.department.name if d.department else "",
        "department_id": d.department_id, "specialization": d.specialization,
        "qualification": d.qualification, "experience_years": d.experience_years,
        "consultation_fee": d.consultation_fee, "rating": d.rating,
        "available": d.available, "photo": d.photo, "bio": d.bio,
    }


def appointment_json(a: M.Appointment) -> dict:
    return {
        "id": a.id, "appointment_code": a.appointment_code,
        "patient_id": a.patient_id, "patient_name": a.patient.full_name,
        "doctor_id": a.doctor_id, "doctor_name": a.doctor.name,
        "department": a.doctor.department.name if a.doctor.department else "",
        "slot_date": str(a.slot_date), "slot_time": a.slot_time,
        "reason": a.reason, "status": a.status,
        "has_consultation": a.consultation is not None,
        "fee": a.doctor.consultation_fee,
    }


def consultation_json(c: M.Consultation) -> dict:
    return {
        "id": c.id, "appointment_id": c.appointment_id,
        "appointment_code": c.appointment.appointment_code if c.appointment else "",
        "patient_id": c.patient_id, "patient_name": c.patient.full_name,
        "doctor_id": c.doctor_id, "doctor_name": c.doctor.name,
        "department": c.doctor.department.name if c.doctor.department else "",
        "symptoms": c.symptoms, "diagnosis": c.diagnosis, "treatment": c.treatment,
        "notes": c.notes, "consultation_date": str(c.consultation_date),
        "followup_date": str(c.followup_date) if c.followup_date else None,
        "prescription_id": c.prescription.id if c.prescription else None,
    }


def prescription_json(p: M.Prescription, db: Optional[Session] = None) -> dict:
    # Look up the invoice tied to the same consultation this prescription came
    # from (if one has been generated yet), so the patient can see what this
    # visit cost and jump straight to paying it without leaving the page.
    bill_summary = None
    if db is not None and p.consultation_id:
        bill = (db.query(M.Bill)
                  .filter(M.Bill.consultation_id == p.consultation_id)
                  .order_by(M.Bill.id.desc()).first())
        if bill:
            bill_summary = {
                "id": bill.id, "invoice_number": bill.invoice_number,
                "total_amount": bill.total_amount, "amount_paid": bill.amount_paid,
                "balance": round(bill.total_amount - bill.amount_paid, 2),
                "status": bill.status,
            }
    return {
        "id": p.id, "prescription_code": p.prescription_code,
        "consultation_id": p.consultation_id,
        "patient_id": p.patient_id, "patient_name": p.patient.full_name,
        "patient_code": p.patient.patient_code, "patient_age": p.patient.age,
        "patient_gender": p.patient.gender,
        "doctor_name": p.doctor.name, "doctor_id": p.doctor_id,
        "department": p.doctor.department.name if p.doctor.department else "",
        "diagnosis": p.consultation.diagnosis if p.consultation else "",
        "instructions": p.instructions,
        "followup_date": str(p.followup_date) if p.followup_date else None,
        "active": p.active, "created_at": p.created_at.strftime("%d %b %Y"),
        "medicines": [{"id": m.id, "medicine": m.medicine, "dosage": m.dosage,
                       "frequency": m.frequency, "duration": m.duration, "notes": m.notes}
                      for m in p.medicines],
        "bill": bill_summary,
    }


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
@app.post("/api/auth/signup", status_code=201)
def signup(data: SignupIn, db: Session = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    pw_errors = A.password_strength_errors(data.password)
    if pw_errors:
        raise HTTPException(400, pw_errors[0])
    if db.query(M.User).filter(M.User.email == data.email).first():
        raise HTTPException(400, "An account with this email already exists")
    if db.query(M.Patient).filter(M.Patient.email == data.email).first():
        raise HTTPException(400, "A patient record with this email already exists. Try logging in instead.")
    if db.query(M.Patient).filter(M.Patient.phone == data.mobile).first():
        raise HTTPException(400, "This mobile number is already registered")

    dob = data.dob
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    patient = M.Patient(
        patient_code=next_code(db, M.Patient, "patient_code", "PT"),
        full_name=data.full_name, dob=dob, age=max(age, 0), gender=data.gender,
        blood_group="", phone=data.mobile, email=data.email,
        emergency_contact_name="", emergency_contact_number="",
    )
    db.add(patient)
    db.flush()

    user = M.User(patient_id=patient.id, email=data.email,
                  password_hash=A.hash_password(data.password), role="patient")
    db.add(user)
    db.flush()

    log_history(db, patient.id, "Registration", "Account created with MediTrack",
                f"Patient ID {patient.patient_code}")
    notify(db, patient.id, "Welcome to MediTrack! Your account has been created. Please complete your profile.",
           "success")
    db.commit()
    return {"message": "Account created successfully. Please log in.",
            "patient_code": patient.patient_code, "email": user.email}


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(M.User).filter(M.User.email == data.email).first()
    if not user or not A.verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled. Contact support.")
    user.last_login = datetime.utcnow()
    db.commit()
    token = A.create_access_token(user.id, user.patient_id, user.email, data.remember_me)
    return {
        "access_token": token, "token_type": "bearer",
        "user": user_json(user),
        "patient": patient_json(user.patient) if user.patient else None,
    }


@app.get("/api/auth/me")
def me(current: A.CurrentUser = Depends(A.get_current_user), db: Session = Depends(get_db)):
    user = db.get(M.User, current.user_id)
    if not user:
        raise HTTPException(404, "Account not found")
    return {"user": user_json(user), "patient": patient_json(user.patient) if user.patient else None}


@app.post("/api/auth/logout")
def logout(current: A.CurrentUser = Depends(A.get_current_user)):
    # JWTs are stateless; the client discards the token. This endpoint exists
    # so the frontend has a clean, explicit call to confirm the session ended.
    return {"message": "Logged out successfully"}


@app.post("/api/auth/forgot-password")
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_db)):
    user = db.query(M.User).filter(M.User.email == data.email).first()
    # Always return a generic success message so we never reveal whether an
    # email exists in the system (prevents account enumeration).
    generic = {"message": "If an account exists for that email, a password reset link has been sent."}
    if not user:
        return generic
    raw_token, hashed = A.make_reset_token()
    user.reset_token_hash = hashed
    user.reset_token_expires = datetime.utcnow() + timedelta(minutes=A.RESET_TOKEN_TTL_MINUTES)
    db.commit()
    reset_link = f"/reset-password.html?token={raw_token}&email={data.email}"
    # No SMTP provider is configured in this environment, so instead of
    # silently discarding the reset link (a "fake" flow) we log it
    # server-side and return it in dev responses so the flow is testable
    # end-to-end. Wire up a real email provider (SendGrid/SES/SMTP) in
    # production and remove `reset_link` from the response below.
    print(f"[MediTrack] Password reset link for {data.email}: {reset_link}")
    generic["dev_reset_link"] = reset_link
    return generic


@app.post("/api/auth/reset-password")
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_db)):
    if data.new_password != data.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    pw_errors = A.password_strength_errors(data.new_password)
    if pw_errors:
        raise HTTPException(400, pw_errors[0])
    hashed = A.hash_reset_token(data.token)
    user = db.query(M.User).filter(M.User.reset_token_hash == hashed).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    user.password_hash = A.hash_password(data.new_password)
    user.reset_token_hash = None
    user.reset_token_expires = None
    db.commit()
    notify(db, user.patient_id, "Your password was changed successfully.", "success")
    db.commit()
    return {"message": "Password updated successfully. You can now log in."}


@app.put("/api/auth/change-password")
def change_password(data: ChangePasswordIn, current: A.CurrentUser = Depends(A.get_current_user),
                    db: Session = Depends(get_db)):
    user = db.get(M.User, current.user_id)
    if not user or not A.verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if data.new_password != data.confirm_password:
        raise HTTPException(400, "New passwords do not match")
    pw_errors = A.password_strength_errors(data.new_password)
    if pw_errors:
        raise HTTPException(400, pw_errors[0])
    user.password_hash = A.hash_password(data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


# --------------------------------------------------------------------------
# Patients
# --------------------------------------------------------------------------
@app.post("/api/patients", status_code=201)
def create_patient(data: PatientIn, db: Session = Depends(get_db)):
    if db.query(M.Patient).filter(M.Patient.email == data.email).first():
        raise HTTPException(400, "A patient with this email already exists")
    if db.query(M.Patient).filter(M.Patient.phone == data.phone).first():
        raise HTTPException(400, "A patient with this phone number already exists")
    p = M.Patient(patient_code=next_code(db, M.Patient, "patient_code", "PT"), **data.model_dump())
    db.add(p)
    db.flush()
    db.add(M.EmergencyContact(patient_id=p.id, name=data.emergency_contact_name,
                              relation="Primary", phone=data.emergency_contact_number))
    log_history(db, p.id, "Registration", "Patient registered with MediTrack",
                f"Patient ID {p.patient_code}")
    notify(db, p.id, "Welcome to MediTrack! Your patient profile has been created.", "success")
    db.commit()
    db.refresh(p)
    return patient_json(p)


@app.get("/api/patients")
def list_patients(q: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(M.Patient)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(M.Patient.patient_code.like(like), M.Patient.full_name.like(like),
                                 M.Patient.phone.like(like), M.Patient.email.like(like)))
    return [patient_json(p) for p in query.order_by(M.Patient.id.desc()).all()]


@app.get("/api/patients/{pid}")
def get_patient(pid: int, db: Session = Depends(get_db)):
    p = db.get(M.Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    return patient_json(p)


@app.put("/api/patients/{pid}")
def update_patient(pid: int, data: PatientIn, db: Session = Depends(get_db)):
    p = db.get(M.Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    dup = db.query(M.Patient).filter(M.Patient.email == data.email, M.Patient.id != pid).first()
    if dup:
        raise HTTPException(400, "Email already used by another patient")
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    log_history(db, p.id, "Registration", "Profile updated", "Patient details were updated")
    notify(db, p.id, "Your profile details were updated successfully.", "info")
    db.commit()
    db.refresh(p)
    return patient_json(p)


@app.delete("/api/patients/{pid}")
def delete_patient(pid: int, db: Session = Depends(get_db)):
    p = db.get(M.Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    for a in p.appointments:
        slot = db.query(M.DoctorAvailability).filter_by(
            doctor_id=a.doctor_id, slot_date=a.slot_date, slot_time=a.slot_time).first()
        if slot:
            slot.is_booked = False
    db.delete(p)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------
# Departments & Doctors
# --------------------------------------------------------------------------
@app.get("/api/departments")
def departments(db: Session = Depends(get_db)):
    out = []
    for d in db.query(M.Department).order_by(M.Department.name).all():
        out.append({"id": d.id, "name": d.name, "description": d.description,
                    "doctor_count": len(d.doctors)})
    return out


@app.get("/api/doctors")
def doctors(department_id: Optional[int] = None, q: Optional[str] = None,
            db: Session = Depends(get_db)):
    query = db.query(M.Doctor)
    if department_id:
        query = query.filter(M.Doctor.department_id == department_id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(M.Doctor.name.like(like), M.Doctor.specialization.like(like)))
    return [doctor_json(d) for d in query.order_by(M.Doctor.name).all()]


@app.get("/api/doctors/{did}")
def doctor(did: int, db: Session = Depends(get_db)):
    d = db.get(M.Doctor, did)
    if not d:
        raise HTTPException(404, "Doctor not found")
    return doctor_json(d)


@app.get("/api/doctors/{did}/availability")
def availability(did: int, db: Session = Depends(get_db)):
    d = db.get(M.Doctor, did)
    if not d:
        raise HTTPException(404, "Doctor not found")
    today = date.today()
    rows = [s for s in d.slots if s.slot_date >= today]
    rows.sort(key=lambda s: (s.slot_date, s.slot_time))
    grouped: dict = {}
    for s in rows:
        key = str(s.slot_date)
        grouped.setdefault(key, {"date": key, "day": s.day_name, "slots": []})
        grouped[key]["slots"].append({"id": s.id, "time": s.slot_time, "booked": s.is_booked})
    return list(grouped.values())


@app.get("/api/availability")
def all_availability(db: Session = Depends(get_db)):
    today = date.today()
    rows = (db.query(M.DoctorAvailability)
            .filter(M.DoctorAvailability.slot_date >= today)
            .order_by(M.DoctorAvailability.slot_date, M.DoctorAvailability.slot_time).all())
    return [{"doctor_id": r.doctor_id, "doctor": r.doctor.name,
             "department": r.doctor.department.name, "day": r.day_name,
             "date": str(r.slot_date), "time": r.slot_time,
             "status": "Booked" if r.is_booked else "Available"} for r in rows]


# --------------------------------------------------------------------------
# Appointments
# --------------------------------------------------------------------------
@app.post("/api/appointments", status_code=201)
def book(data: AppointmentIn, current: A.CurrentUser = Depends(A.get_current_user), db: Session = Depends(get_db)):
    if current.patient_id != data.patient_id:
        raise HTTPException(403, "You are not authorized to book on behalf of this patient.")
    patient = db.get(M.Patient, data.patient_id)
    doctor_ = db.get(M.Doctor, data.doctor_id)
    if not patient or not doctor_:
        raise HTTPException(404, "Patient or doctor not found")
    slot = db.query(M.DoctorAvailability).filter_by(
        doctor_id=data.doctor_id, slot_date=data.slot_date, slot_time=data.slot_time).first()
    if not slot:
        raise HTTPException(400, "Selected slot does not exist")
    if slot.is_booked:
        raise HTTPException(409, "This slot is already booked. Please choose another time.")
    slot.is_booked = True
    a = M.Appointment(appointment_code=next_code(db, M.Appointment, "appointment_code", "AP"),
                      **data.model_dump())
    db.add(a)
    db.flush()
    log_history(db, patient.id, "Appointment",
                f"Appointment booked with Dr. {doctor_.name}",
                f"{data.slot_date} at {data.slot_time} - {doctor_.department.name}")
    notify(db, patient.id,
           f"Appointment {a.appointment_code} confirmed with Dr. {doctor_.name} on {data.slot_date} at {data.slot_time}.",
           "success", priority="high", email=True, sms=True, subject="Appointment Confirmed - MediTrack")
    db.commit()
    db.refresh(a)
    return appointment_json(a)


@app.get("/api/appointments")
def appointments(patient_id: Optional[int] = None, q: Optional[str] = None,
                 status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(M.Appointment)
    if patient_id:
        query = query.filter(M.Appointment.patient_id == patient_id)
    if status:
        query = query.filter(M.Appointment.status == status)
    rows = query.order_by(M.Appointment.slot_date.desc(), M.Appointment.slot_time).all()
    data = [appointment_json(a) for a in rows]
    if q:
        ql = q.lower()
        data = [d for d in data if ql in d["appointment_code"].lower()
                or ql in d["doctor_name"].lower() or ql in d["department"].lower()
                or ql in d["slot_date"]]
    return data


@app.put("/api/appointments/{aid}/reschedule")
def reschedule(aid: int, slot_date: date = Query(...), slot_time: str = Query(...),
               db: Session = Depends(get_db)):
    a = db.get(M.Appointment, aid)
    if not a:
        raise HTTPException(404, "Appointment not found")
    if a.status != "Booked":
        raise HTTPException(400, "Only booked appointments can be rescheduled")
    new_slot = db.query(M.DoctorAvailability).filter_by(
        doctor_id=a.doctor_id, slot_date=slot_date, slot_time=slot_time).first()
    if not new_slot:
        raise HTTPException(400, "Slot not available")
    if new_slot.is_booked:
        raise HTTPException(409, "That slot is already booked")
    old = db.query(M.DoctorAvailability).filter_by(
        doctor_id=a.doctor_id, slot_date=a.slot_date, slot_time=a.slot_time).first()
    if old:
        old.is_booked = False
    new_slot.is_booked = True
    a.slot_date, a.slot_time = slot_date, slot_time
    log_history(db, a.patient_id, "Appointment", f"Appointment {a.appointment_code} rescheduled",
                f"New schedule: {slot_date} at {slot_time}")
    notify(db, a.patient_id, f"Appointment {a.appointment_code} rescheduled to {slot_date} {slot_time}.", "info")
    db.commit()
    db.refresh(a)
    return appointment_json(a)


@app.put("/api/appointments/{aid}/cancel")
def cancel(aid: int, db: Session = Depends(get_db)):
    a = db.get(M.Appointment, aid)
    if not a:
        raise HTTPException(404, "Appointment not found")
    a.status = "Cancelled"
    slot = db.query(M.DoctorAvailability).filter_by(
        doctor_id=a.doctor_id, slot_date=a.slot_date, slot_time=a.slot_time).first()
    if slot:
        slot.is_booked = False
    log_history(db, a.patient_id, "Appointment", f"Appointment {a.appointment_code} cancelled", "")
    notify(db, a.patient_id, f"Appointment {a.appointment_code} was cancelled.", "warning")
    db.commit()
    return appointment_json(a)


@app.delete("/api/appointments/{aid}")
def delete_appointment(aid: int, db: Session = Depends(get_db)):
    a = db.get(M.Appointment, aid)
    if not a:
        raise HTTPException(404, "Appointment not found")
    slot = db.query(M.DoctorAvailability).filter_by(
        doctor_id=a.doctor_id, slot_date=a.slot_date, slot_time=a.slot_time).first()
    if slot:
        slot.is_booked = False
    db.delete(a)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------
# Consultations + Prescriptions
# --------------------------------------------------------------------------
@app.post("/api/consultations", status_code=201)
def create_consultation(data: ConsultationIn, db: Session = Depends(get_db)):
    a = db.get(M.Appointment, data.appointment_id)
    if not a:
        raise HTTPException(404, "Appointment not found")
    if a.status == "Cancelled":
        raise HTTPException(400, "Cannot create a consultation for a cancelled appointment")
    if a.consultation:
        raise HTTPException(400, "Consultation already recorded for this appointment")
    c = M.Consultation(appointment_id=a.id, patient_id=a.patient_id, doctor_id=a.doctor_id,
                       symptoms=data.symptoms, diagnosis=data.diagnosis, treatment=data.treatment,
                       notes=data.notes, consultation_date=date.today(),
                       followup_date=data.followup_date)
    db.add(c)
    a.status = "Completed"
    db.flush()
    log_history(db, a.patient_id, "Consultation", f"Consultation with Dr. {a.doctor.name}",
                f"Diagnosis: {data.diagnosis}")
    if data.medicines:
        p = M.Prescription(prescription_code=next_code(db, M.Prescription, "prescription_code", "RX"),
                           consultation_id=c.id, patient_id=a.patient_id, doctor_id=a.doctor_id,
                           instructions=data.instructions, followup_date=data.followup_date)
        db.add(p)
        db.flush()
        for m in data.medicines:
            db.add(M.PrescriptionMedicine(prescription_id=p.id, **m.model_dump()))
        log_history(db, a.patient_id, "Prescription", f"Prescription {p.prescription_code} issued",
                    ", ".join(m.medicine for m in data.medicines))
        notify(db, a.patient_id, f"New prescription {p.prescription_code} is available.", "success")
    if data.followup_date:
        notify(db, a.patient_id, f"Follow-up scheduled on {data.followup_date}.", "info")
    db.commit()
    db.refresh(c)
    return consultation_json(c)


@app.get("/api/consultations")
def consultations(patient_id: Optional[int] = None, q: Optional[str] = None,
                  db: Session = Depends(get_db)):
    query = db.query(M.Consultation)
    if patient_id:
        query = query.filter(M.Consultation.patient_id == patient_id)
    rows = [consultation_json(c) for c in query.order_by(M.Consultation.id.desc()).all()]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["diagnosis"].lower() or ql in r["doctor_name"].lower()
                or ql in r["symptoms"].lower()]
    return rows


@app.put("/api/consultations/{cid}")
def update_consultation(cid: int, data: ConsultationIn, db: Session = Depends(get_db)):
    c = db.get(M.Consultation, cid)
    if not c:
        raise HTTPException(404, "Consultation not found")
    c.symptoms, c.diagnosis = data.symptoms, data.diagnosis
    c.treatment, c.notes = data.treatment, data.notes
    c.followup_date = data.followup_date
    if c.prescription:
        c.prescription.instructions = data.instructions
        c.prescription.followup_date = data.followup_date
        for m in list(c.prescription.medicines):
            db.delete(m)
        db.flush()
        for m in data.medicines:
            db.add(M.PrescriptionMedicine(prescription_id=c.prescription.id, **m.model_dump()))
    elif data.medicines:
        p = M.Prescription(prescription_code=next_code(db, M.Prescription, "prescription_code", "RX"),
                           consultation_id=c.id, patient_id=c.patient_id, doctor_id=c.doctor_id,
                           instructions=data.instructions, followup_date=data.followup_date)
        db.add(p)
        db.flush()
        for m in data.medicines:
            db.add(M.PrescriptionMedicine(prescription_id=p.id, **m.model_dump()))
    db.commit()
    db.refresh(c)
    return consultation_json(c)


@app.delete("/api/consultations/{cid}")
def delete_consultation(cid: int, db: Session = Depends(get_db)):
    c = db.get(M.Consultation, cid)
    if not c:
        raise HTTPException(404, "Consultation not found")
    if c.appointment:
        c.appointment.status = "Booked"
    db.delete(c)
    db.commit()
    return {"deleted": True}


@app.get("/api/prescriptions")
def prescriptions(patient_id: Optional[int] = None, q: Optional[str] = None,
                  db: Session = Depends(get_db)):
    query = db.query(M.Prescription)
    if patient_id:
        query = query.filter(M.Prescription.patient_id == patient_id)
    rows = [prescription_json(p, db) for p in query.order_by(M.Prescription.id.desc()).all()]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["prescription_code"].lower()
                or ql in r["doctor_name"].lower()
                or any(ql in m["medicine"].lower() for m in r["medicines"])]
    return rows


@app.get("/api/prescriptions/{pid}")
def prescription(pid: int, db: Session = Depends(get_db)):
    p = db.get(M.Prescription, pid)
    if not p:
        raise HTTPException(404, "Prescription not found")
    return prescription_json(p, db)


@app.delete("/api/prescriptions/{pid}")
def delete_prescription(pid: int, db: Session = Depends(get_db)):
    p = db.get(M.Prescription, pid)
    if not p:
        raise HTTPException(404, "Prescription not found")
    db.delete(p)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------
# Medical history / notifications / dashboard
# --------------------------------------------------------------------------
@app.get("/api/patients/{pid}/history")
def history(pid: int, current: A.CurrentUser = Depends(A.require_own_patient), db: Session = Depends(get_db)):
    rows = (db.query(M.MedicalHistory).filter_by(patient_id=pid)
            .order_by(M.MedicalHistory.event_date.desc(), M.MedicalHistory.id.desc()).all())
    return [{"id": r.id, "event_type": r.event_type, "title": r.title, "detail": r.detail,
             "event_date": r.event_date.strftime("%d %b %Y, %I:%M %p")} for r in rows]


@app.get("/api/patients/{pid}/notifications")
def notifications(pid: int, current: A.CurrentUser = Depends(A.require_own_patient), db: Session = Depends(get_db)):
    rows = (db.query(M.Notification).filter_by(patient_id=pid)
            .order_by(M.Notification.id.desc()).limit(25).all())
    return [{"id": r.id, "message": r.message, "category": r.category, "is_read": r.is_read,
             "created_at": r.created_at.strftime("%d %b %Y, %I:%M %p")} for r in rows]


@app.put("/api/notifications/{nid}/read")
def read_notification(nid: int, db: Session = Depends(get_db)):
    n = db.get(M.Notification, nid)
    if not n:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}


@app.get("/api/patients/{pid}/dashboard")
def dashboard(pid: int, current: A.CurrentUser = Depends(A.require_own_patient), db: Session = Depends(get_db)):
    p = db.get(M.Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    today = date.today()
    appts = db.query(M.Appointment).filter_by(patient_id=pid).all()
    upcoming = [a for a in appts if a.status == "Booked" and a.slot_date >= today]
    upcoming.sort(key=lambda a: (a.slot_date, a.slot_time))
    completed = [a for a in appts if a.status == "Completed"]
    cons = db.query(M.Consultation).filter_by(patient_id=pid).all()
    active_rx = db.query(M.Prescription).filter_by(patient_id=pid, active=True).count()
    records_count = db.query(M.MedicalHistory).filter_by(patient_id=pid).count()
    pending_labs = db.query(M.LabTest).filter_by(patient_id=pid).filter(
        M.LabTest.status.in_(["Pending", "In Progress"])).count()
    followups = sorted([c.followup_date for c in cons if c.followup_date and c.followup_date >= today])
    recent = (db.query(M.MedicalHistory).filter_by(patient_id=pid)
              .order_by(M.MedicalHistory.id.desc()).limit(5).all())
    unread = db.query(M.Notification).filter_by(patient_id=pid, is_read=False).count()
    patient_bills = db.query(M.Bill).filter_by(patient_id=pid).all()
    pending_bills = [b for b in patient_bills if b.status in ("Pending", "Partially Paid")]
    total_due = sum(b.total_amount - b.amount_paid for b in pending_bills)
    active_doctors = db.query(M.Doctor).filter_by(available=True).count()
    return {
        "patient": patient_json(p),
        "total_appointments": len(appts),
        "upcoming_appointments": [appointment_json(a) for a in upcoming[:5]],
        "upcoming_count": len(upcoming),
        "completed_count": len(completed),
        "consultation_count": len(cons),
        "active_prescriptions": active_rx,
        "medical_records_count": records_count,
        "pending_lab_tests": pending_labs,
        "pending_bills_count": len(pending_bills),
        "total_amount_due": round(total_due, 2),
        "next_followup": str(followups[0]) if followups else None,
        "unread_notifications": unread,
        "active_doctors": active_doctors,
        "recent_activity": [{"title": r.title, "event_type": r.event_type,
                             "event_date": r.event_date.strftime("%d %b %Y")} for r in recent],
        "summary": smart_summary(p, appts, cons, active_rx),
    }


def lab_test_json(t: M.LabTest) -> dict:
    return {
        "id": t.id, "test_code": t.test_code, "patient_id": t.patient_id,
        "doctor_id": t.doctor_id, "doctor_name": t.doctor.name if t.doctor else None,
        "consultation_id": t.consultation_id, "test_name": t.test_name,
        "status": t.status, "ordered_date": str(t.ordered_date),
        "result_date": str(t.result_date) if t.result_date else None,
        "result_summary": t.result_summary,
    }


def user_json(u: M.User) -> dict:
    return {
        "id": u.id, "email": u.email, "role": u.role,
        "patient_id": u.patient_id,
        "patient_name": u.patient.full_name if u.patient else None,
        "patient_code": u.patient.patient_code if u.patient else None,
    }


def smart_summary(p, appts, cons, active_rx) -> str:
    last_dx = cons[-1].diagnosis if cons else "no recorded diagnosis yet"
    allergies = p.allergies or "none reported"
    return (f"{p.full_name}, {p.age}y {p.gender}, blood group {p.blood_group}. "
            f"{len(appts)} appointment(s) and {len(cons)} consultation(s) on record. "
            f"Most recent diagnosis: {last_dx}. Active prescriptions: {active_rx}. "
            f"Known allergies: {allergies}.")


# --------------------------------------------------------------------------
# Emergency
# --------------------------------------------------------------------------
@app.get("/api/blood-stock")
def blood_stock(db: Session = Depends(get_db)):
    return [{"blood_group": b.blood_group, "units": b.units,
             "status": "Available" if b.units > 5 else ("Low" if b.units else "Out of stock")}
            for b in db.query(M.BloodStock).order_by(M.BloodStock.blood_group).all()]


@app.post("/api/ambulance", status_code=201)
def ambulance(data: AmbulanceIn, db: Session = Depends(get_db)):
    if not db.get(M.Patient, data.patient_id):
        raise HTTPException(404, "Patient not found")
    r = M.AmbulanceRequest(**data.model_dump())
    db.add(r)
    db.flush()
    log_history(db, data.patient_id, "Emergency", "Ambulance requested", data.pickup_address)
    notify(db, data.patient_id, "Ambulance dispatched. ETA 12 minutes.", "danger")
    db.commit()
    return {"id": r.id, "status": r.status, "eta_minutes": 12}


@app.get("/api/ambulance")
def ambulance_list(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                   db: Session = Depends(get_db)):
    if current.patient_id != patient_id:
        raise HTTPException(403, "You are not authorized to access these records.")
    rows = (db.query(M.AmbulanceRequest).filter_by(patient_id=patient_id)
            .order_by(M.AmbulanceRequest.id.desc()).all())
    return [{"id": r.id, "pickup_address": r.pickup_address, "contact_number": r.contact_number,
             "emergency_type": r.emergency_type, "status": r.status,
             "created_at": r.created_at.strftime("%d %b %Y, %I:%M %p")} for r in rows]


@app.get("/api/patients/{pid}/emergency-card")
def emergency_card(pid: int, current: A.CurrentUser = Depends(A.require_own_patient), db: Session = Depends(get_db)):
    p = db.get(M.Patient, pid)
    if not p:
        raise HTTPException(404, "Patient not found")
    return {"patient_code": p.patient_code, "full_name": p.full_name, "age": p.age,
            "blood_group": p.blood_group, "allergies": p.allergies or "None reported",
            "conditions": p.conditions or "None reported",
            "current_medications": p.current_medications or "None",
            "emergency_contact_name": p.emergency_contact_name,
            "emergency_contact_number": p.emergency_contact_number}


# --------------------------------------------------------------------------
# Lab tests
# --------------------------------------------------------------------------
@app.get("/api/patients/{pid}/lab-tests")
def lab_tests_for_patient(pid: int, current: A.CurrentUser = Depends(A.require_own_patient),
                          db: Session = Depends(get_db)):
    rows = (db.query(M.LabTest).filter_by(patient_id=pid)
            .order_by(M.LabTest.ordered_date.desc(), M.LabTest.id.desc()).all())
    return [lab_test_json(t) for t in rows]


@app.post("/api/lab-tests", status_code=201)
def create_lab_test(data: LabTestIn, current: A.CurrentUser = Depends(A.get_current_user),
                    db: Session = Depends(get_db)):
    if current.patient_id != data.patient_id:
        raise HTTPException(403, "You are not authorized to create records for this patient.")
    if not db.get(M.Patient, data.patient_id):
        raise HTTPException(404, "Patient not found")
    t = M.LabTest(test_code=next_code(db, M.LabTest, "test_code", "LT"), **data.model_dump())
    db.add(t)
    db.flush()
    log_history(db, data.patient_id, "LabTest", f"Lab test ordered: {data.test_name}", "")
    notify(db, data.patient_id, f"Lab test '{data.test_name}' has been ordered.", "info")
    db.commit()
    db.refresh(t)
    return lab_test_json(t)


@app.put("/api/lab-tests/{tid}")
def update_lab_test(tid: int, data: LabTestStatusIn, current: A.CurrentUser = Depends(A.get_current_user),
                    db: Session = Depends(get_db)):
    t = db.get(M.LabTest, tid)
    if not t:
        raise HTTPException(404, "Lab test not found")
    if current.patient_id != t.patient_id:
        raise HTTPException(403, "You are not authorized to update this record.")
    t.status = data.status
    t.result_summary = data.result_summary
    if data.status == "Completed" and not t.result_date:
        t.result_date = date.today()
    db.commit()
    if data.status == "Completed":
        notify(db, t.patient_id, f"Results for '{t.test_name}' are now available.", "success")
        db.commit()
    db.refresh(t)
    return lab_test_json(t)


def bill_json(b: M.Bill) -> dict:
    return {
        "id": b.id, "invoice_number": b.invoice_number, "patient_id": b.patient_id,
        "patient_name": b.patient.full_name if b.patient else None,
        "doctor_id": b.doctor_id, "doctor_name": b.doctor.name if b.doctor else None,
        "appointment_id": b.appointment_id, "consultation_id": b.consultation_id,
        "invoice_date": str(b.invoice_date), "subtotal": round(b.subtotal, 2),
        "discount": round(b.discount, 2), "tax": round(b.tax, 2),
        "total_amount": round(b.total_amount, 2), "amount_paid": round(b.amount_paid, 2),
        "balance": round(b.total_amount - b.amount_paid, 2), "status": b.status, "notes": b.notes,
        "created_at": b.created_at.strftime("%d %b %Y, %I:%M %p"),
        "items": [{"id": i.id, "description": i.description, "category": i.category,
                   "quantity": i.quantity, "unit_price": round(i.unit_price, 2),
                   "amount": round(i.amount, 2)} for i in b.items],
        "payments": [payment_json(p) for p in b.payments],
    }


def payment_json(p: M.Payment) -> dict:
    return {
        "id": p.id, "transaction_id": p.transaction_id, "bill_id": p.bill_id,
        "patient_id": p.patient_id, "amount": round(p.amount, 2), "method": p.method,
        "status": p.status, "created_at": p.created_at.strftime("%d %b %Y, %I:%M %p"),
    }


# --------------------------------------------------------------------------
# Billing & Payments
# --------------------------------------------------------------------------
@app.post("/api/bills", status_code=201)
def create_bill(data: BillIn, current: A.CurrentUser = Depends(A.get_current_user), db: Session = Depends(get_db)):
    if current.patient_id != data.patient_id:
        raise HTTPException(403, "You are not authorized to create a bill for this patient.")
    if not db.get(M.Patient, data.patient_id):
        raise HTTPException(404, "Patient not found")
    if not data.items:
        raise HTTPException(400, "A bill must include at least one line item")

    subtotal = sum(i.quantity * i.unit_price for i in data.items)
    taxable = max(subtotal - data.discount, 0)
    tax = round(taxable * (data.tax_percent / 100), 2)
    total = round(taxable + tax, 2)

    bill = M.Bill(invoice_number=next_code(db, M.Bill, "invoice_number", "INV"),
                  patient_id=data.patient_id, doctor_id=data.doctor_id,
                  appointment_id=data.appointment_id, consultation_id=data.consultation_id,
                  subtotal=round(subtotal, 2), discount=round(data.discount, 2), tax=tax,
                  total_amount=total, amount_paid=0.0, status="Pending", notes=data.notes)
    db.add(bill)
    db.flush()
    for i in data.items:
        db.add(M.BillItem(bill_id=bill.id, description=i.description, category=i.category,
                          quantity=i.quantity, unit_price=i.unit_price, amount=round(i.quantity * i.unit_price, 2)))
    log_history(db, data.patient_id, "Billing", f"Invoice {bill.invoice_number} generated",
               f"Total amount: ₹{total:,.2f}")
    notify(db, data.patient_id, f"Invoice {bill.invoice_number} generated — ₹{total:,.2f} due.",
          "warning", priority="high", email=True, subject="New Invoice - MediTrack")
    db.commit()
    db.refresh(bill)
    return bill_json(bill)


@app.get("/api/patients/{pid}/bills")
def bills_for_patient(pid: int, current: A.CurrentUser = Depends(A.require_own_patient), db: Session = Depends(get_db)):
    rows = db.query(M.Bill).filter_by(patient_id=pid).order_by(M.Bill.created_at.desc()).all()
    return [bill_json(b) for b in rows]


@app.get("/api/bills/{bid}")
def get_bill(bid: int, current: A.CurrentUser = Depends(A.get_current_user), db: Session = Depends(get_db)):
    b = db.get(M.Bill, bid)
    if not b:
        raise HTTPException(404, "Bill not found")
    if current.patient_id != b.patient_id:
        raise HTTPException(403, "You are not authorized to view this invoice.")
    return bill_json(b)


@app.post("/api/payments", status_code=201)
def make_payment(data: PaymentIn, current: A.CurrentUser = Depends(A.get_current_user), db: Session = Depends(get_db)):
    bill = db.get(M.Bill, data.bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    if current.patient_id != bill.patient_id:
        raise HTTPException(403, "You are not authorized to pay this invoice.")
    if bill.status == "Paid":
        raise HTTPException(400, "This invoice is already fully paid.")
    if data.amount <= 0:
        raise HTTPException(400, "Payment amount must be greater than zero.")
    balance = bill.total_amount - bill.amount_paid
    if data.amount > balance + 0.01:
        raise HTTPException(400, f"Payment exceeds the balance due (₹{balance:,.2f}).")

    # NOTE: this simulates backend-side payment verification. Wire up a real
    # gateway (Razorpay/Stripe/PayU) here using credentials from environment
    # variables — never store raw card details, only the gateway's
    # transaction reference and status.
    txn_id = "TXN" + secrets_hex()
    payment = M.Payment(transaction_id=txn_id, bill_id=bill.id, patient_id=bill.patient_id,
                        amount=data.amount, method=data.method, status="Success")
    db.add(payment)
    bill.amount_paid = round(bill.amount_paid + data.amount, 2)
    bill.status = "Paid" if bill.amount_paid >= bill.total_amount - 0.01 else "Partially Paid"
    log_history(db, bill.patient_id, "Payment", f"Payment of ₹{data.amount:,.2f} received for {bill.invoice_number}",
               f"Method: {data.method}, Status: {bill.status}")
    notify(db, bill.patient_id,
          f"Payment of ₹{data.amount:,.2f} for {bill.invoice_number} was successful.",
          "success", priority="high", email=True, sms=True, subject="Payment Successful - MediTrack")
    db.commit()
    db.refresh(payment)
    db.refresh(bill)
    return {"payment": payment_json(payment), "bill": bill_json(bill)}


def secrets_hex() -> str:
    import secrets
    return secrets.token_hex(5).upper()


# --------------------------------------------------------------------------
# Web Push (real phone/browser notifications)
# --------------------------------------------------------------------------
@app.get("/api/push/vapid-public-key")
def vapid_public_key():
    return {"enabled": PS.PUSH_ENABLED, "public_key": PS.VAPID_PUBLIC_KEY if PS.PUSH_ENABLED else None}


@app.post("/api/push/subscribe", status_code=201)
def push_subscribe(data: PushSubscribeIn, current: A.CurrentUser = Depends(A.get_current_user),
                   db: Session = Depends(get_db)):
    existing = db.query(M.PushSubscription).filter_by(endpoint=data.endpoint).first()
    if existing:
        existing.patient_id = current.patient_id
        existing.p256dh = data.p256dh
        existing.auth = data.auth
    else:
        db.add(M.PushSubscription(patient_id=current.patient_id, endpoint=data.endpoint,
                                  p256dh=data.p256dh, auth=data.auth))
    db.commit()
    return {"message": "Phone notifications enabled for this device."}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(data: PushUnsubscribeIn, current: A.CurrentUser = Depends(A.get_current_user),
                     db: Session = Depends(get_db)):
    sub = db.query(M.PushSubscription).filter_by(endpoint=data.endpoint, patient_id=current.patient_id).first()
    if sub:
        db.delete(sub)
        db.commit()
    return {"message": "Phone notifications disabled for this device."}


@app.post("/api/push/test")
def push_test(current: A.CurrentUser = Depends(A.get_current_user), db: Session = Depends(get_db)):
    if not PS.PUSH_ENABLED:
        raise HTTPException(400, "Push notifications aren't configured on this server yet "
                             "(VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY environment variables are not set).")
    sent = PS.send_push_to_patient(db, current.patient_id, "MediTrack",
                                   "🔔 This is a test notification from MediTrack.")
    db.commit()
    if not sent:
        raise HTTPException(400, "No active devices found. Try enabling notifications again on this device.")
    return {"message": f"Test notification sent to {sent} device(s)."}


# --------------------------------------------------------------------------
# Dashboard analytics (charts)
# --------------------------------------------------------------------------
def _check_owns(current: A.CurrentUser, patient_id: int):
    if current.patient_id != patient_id:
        raise HTTPException(403, "You are not authorized to access this patient's analytics.")


@app.get("/api/dashboard/summary")
def dashboard_summary(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                      db: Session = Depends(get_db)):
    _check_owns(current, patient_id)
    return dashboard(patient_id, current, db)


@app.get("/api/dashboard/appointments-trend")
def appointments_trend(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                       db: Session = Depends(get_db)):
    """Appointment count per month for the last 8 months (real DB data)."""
    _check_owns(current, patient_id)
    today = date.today()
    months = []
    y, m = today.year, today.month
    for i in range(7, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))
    appts = db.query(M.Appointment).filter_by(patient_id=patient_id).all()
    counts = {ym: 0 for ym in months}
    for a in appts:
        key = (a.slot_date.year, a.slot_date.month)
        if key in counts:
            counts[key] += 1
    labels = [date(yy, mm, 1).strftime("%b") for yy, mm in months]
    return {"labels": labels, "values": [counts[ym] for ym in months]}


@app.get("/api/dashboard/appointment-status")
def appointment_status(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                       db: Session = Depends(get_db)):
    """Breakdown of appointments by status (real DB data)."""
    _check_owns(current, patient_id)
    today = date.today()
    appts = db.query(M.Appointment).filter_by(patient_id=patient_id).all()
    upcoming = sum(1 for a in appts if a.status == "Booked" and a.slot_date >= today)
    pending = sum(1 for a in appts if a.status == "Booked" and a.slot_date < today)
    completed = sum(1 for a in appts if a.status == "Completed")
    cancelled = sum(1 for a in appts if a.status == "Cancelled")
    return {"labels": ["Upcoming", "Completed", "Cancelled", "Pending"],
            "values": [upcoming, completed, cancelled, pending]}


@app.get("/api/dashboard/medical-activity")
def medical_activity(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                     db: Session = Depends(get_db)):
    """Monthly consultations / lab tests / prescriptions / appointments for the last 6 months."""
    _check_owns(current, patient_id)
    today = date.today()
    months = []
    y, m = today.year, today.month
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))
    labels = [date(yy, mm, 1).strftime("%b") for yy, mm in months]

    def bucket(dates):
        counts = {ym: 0 for ym in months}
        for d in dates:
            key = (d.year, d.month)
            if key in counts:
                counts[key] += 1
        return [counts[ym] for ym in months]

    cons_dates = [c.consultation_date for c in db.query(M.Consultation).filter_by(patient_id=patient_id).all()]
    lab_dates = [t.ordered_date for t in db.query(M.LabTest).filter_by(patient_id=patient_id).all()]
    rx_dates = [p.created_at.date() for p in db.query(M.Prescription).filter_by(patient_id=patient_id).all()]
    appt_dates = [a.slot_date for a in db.query(M.Appointment).filter_by(patient_id=patient_id).all()]

    return {
        "labels": labels,
        "series": [
            {"name": "Consultations", "values": bucket(cons_dates)},
            {"name": "Lab Tests", "values": bucket(lab_dates)},
            {"name": "Prescriptions", "values": bucket(rx_dates)},
            {"name": "Appointments", "values": bucket(appt_dates)},
        ],
    }


@app.get("/api/dashboard/prescriptions")
def prescriptions_overview(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                           db: Session = Depends(get_db)):
    """Active vs completed prescriptions over the last 6 months (real DB data)."""
    _check_owns(current, patient_id)
    today = date.today()
    months = []
    y, m = today.year, today.month
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))
    labels = [date(yy, mm, 1).strftime("%b") for yy, mm in months]
    rx = db.query(M.Prescription).filter_by(patient_id=patient_id).all()
    active_counts = {ym: 0 for ym in months}
    completed_counts = {ym: 0 for ym in months}
    for p in rx:
        key = (p.created_at.year, p.created_at.month)
        if key in active_counts:
            if p.active:
                active_counts[key] += 1
            else:
                completed_counts[key] += 1
    return {
        "labels": labels,
        "series": [
            {"name": "Active", "values": [active_counts[ym] for ym in months]},
            {"name": "Completed", "values": [completed_counts[ym] for ym in months]},
        ],
    }


@app.get("/api/dashboard/lab-tests")
def lab_tests_status(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                     db: Session = Depends(get_db)):
    """Lab test status breakdown (real DB data)."""
    _check_owns(current, patient_id)
    rows = db.query(M.LabTest).filter_by(patient_id=patient_id).all()
    pending = sum(1 for t in rows if t.status == "Pending")
    in_progress = sum(1 for t in rows if t.status == "In Progress")
    completed = sum(1 for t in rows if t.status == "Completed")
    return {"labels": ["Pending", "Completed", "In Progress"],
            "values": [pending, completed, in_progress]}


@app.get("/api/dashboard/billing")
def billing_overview(patient_id: int, current: A.CurrentUser = Depends(A.get_current_user),
                     db: Session = Depends(get_db)):
    """Payments made per month over the last 6 months, plus a payment-status breakdown
    (real DB data, scoped to the logged-in patient's own bills)."""
    _check_owns(current, patient_id)
    today = date.today()
    months = []
    y, m = today.year, today.month
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))
    labels = [date(yy, mm, 1).strftime("%b") for yy, mm in months]
    payments = db.query(M.Payment).filter_by(patient_id=patient_id, status="Success").all()
    totals = {ym: 0.0 for ym in months}
    for p in payments:
        key = (p.created_at.year, p.created_at.month)
        if key in totals:
            totals[key] += p.amount
    bills = db.query(M.Bill).filter_by(patient_id=patient_id).all()
    status_counts = {"Paid": 0, "Pending": 0, "Partially Paid": 0, "Failed": 0, "Refunded": 0}
    for b in bills:
        status_counts[b.status] = status_counts.get(b.status, 0) + 1
    return {
        "labels": labels, "values": [round(totals[ym], 2) for ym in months],
        "status_labels": list(status_counts.keys()), "status_values": list(status_counts.values()),
    }


@app.post("/api/patients/{pid}/generate-sample-data")
def generate_sample_data(pid: int, current: A.CurrentUser = Depends(A.require_own_patient),
                         db: Session = Depends(get_db)):
    """Creates a handful of REAL appointment/consultation/prescription/lab-test/bill
    rows for the logged-in patient, using existing doctors, so a brand-new account can
    immediately see the dashboard charts populated with genuine (if illustrative) data.
    This does not fabricate chart values directly — it creates real records that the
    normal chart endpoints then compute from, same as any other activity would."""
    patient = db.get(M.Patient, pid)
    if not patient:
        raise HTTPException(404, "Patient not found")
    doctors = db.query(M.Doctor).limit(3).all()
    if not doctors:
        raise HTTPException(400, "No doctors exist in the system yet to attach sample records to.")

    today = date.today()
    created = {"appointments": 0, "consultations": 0, "prescriptions": 0, "lab_tests": 0, "bills": 0}

    # A few past + upcoming appointments across recent months
    offsets = [-75, -50, -20, -5, 4, 12]
    statuses = ["Completed", "Completed", "Completed", "Completed", "Booked", "Booked"]
    for i, off in enumerate(offsets):
        d = today + timedelta(days=off)
        doc = doctors[i % len(doctors)]
        appt = M.Appointment(
            appointment_code=next_code(db, M.Appointment, "appointment_code", "AP"),
            patient_id=pid, doctor_id=doc.id, slot_date=d, slot_time="10:00 AM",
            status=statuses[i], reason="Sample record",
        )
        db.add(appt)
        db.flush()
        created["appointments"] += 1
        if statuses[i] == "Completed":
            cons = M.Consultation(
                patient_id=pid, doctor_id=doc.id, appointment_id=appt.id, consultation_date=d,
                symptoms="Sample symptoms", diagnosis="Sample diagnosis", treatment="Sample treatment plan",
            )
            db.add(cons)
            db.flush()
            created["consultations"] += 1
            rx = M.Prescription(prescription_code=next_code(db, M.Prescription, "prescription_code", "RX"),
                                patient_id=pid, doctor_id=doc.id, consultation_id=cons.id,
                                active=(i >= 3), instructions="Sample prescription instructions")
            db.add(rx)
            db.flush()
            db.add(M.PrescriptionMedicine(prescription_id=rx.id, medicine="Paracetamol 500mg",
                                          dosage="500mg", frequency="1-0-1", duration="5 days",
                                          notes="After food"))
            created["prescriptions"] += 1
            lab = M.LabTest(test_code=next_code(db, M.LabTest, "test_code", "LT"), patient_id=pid,
                            doctor_id=doc.id, consultation_id=cons.id, test_name="Complete Blood Count",
                            status="Completed" if i < 3 else "Pending", ordered_date=d,
                            result_date=d if i < 3 else None,
                            result_summary="Within normal range" if i < 3 else "")
            db.add(lab)
            created["lab_tests"] += 1

            subtotal = 700.0
            bill = M.Bill(invoice_number=next_code(db, M.Bill, "invoice_number", "INV"),
                          patient_id=pid, doctor_id=doc.id, appointment_id=appt.id, consultation_id=cons.id,
                          invoice_date=d, subtotal=subtotal, discount=0, tax=round(subtotal * 0.05, 2),
                          total_amount=round(subtotal * 1.05, 2), amount_paid=0, status="Pending",
                          notes="Sample invoice")
            db.add(bill)
            db.flush()
            db.add(M.BillItem(bill_id=bill.id, description="Consultation Fee", category="Consultation",
                              quantity=1, unit_price=500, amount=500))
            db.add(M.BillItem(bill_id=bill.id, description="Lab Test - CBC", category="Lab",
                              quantity=1, unit_price=200, amount=200))
            created["bills"] += 1
            if i < 2:  # mark the two oldest bills as paid via a real payment record
                pay = M.Payment(transaction_id="TXN" + secrets_hex(), bill_id=bill.id, patient_id=pid,
                                amount=bill.total_amount, method="UPI", status="Success")
                db.add(pay)
                bill.amount_paid = bill.total_amount
                bill.status = "Paid"

    log_history(db, pid, "Sample Data", "Sample dashboard data generated", str(created))
    notify(db, pid, "Sample data added — your dashboard charts are now populated.", "info")
    db.commit()
    return {"message": "Sample data created successfully.", "created": created}


# --------------------------------------------------------------------------
# Seed + static frontend
# --------------------------------------------------------------------------
from seed import run_seed

run_seed()  # idempotent: seeds departments, doctors, slots and blood stock


FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(FRONTEND):
    from fastapi.responses import FileResponse, RedirectResponse

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/login.html")

    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
