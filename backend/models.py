from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Float, Boolean, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), default="")
    doctors = relationship("Doctor", back_populates="department")


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_code = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    dob = Column(Date, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(20), nullable=False)
    blood_group = Column(String(5), nullable=True, default="")
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    address = Column(Text, default="")
    emergency_contact_name = Column(String(120), nullable=True, default="")
    emergency_contact_number = Column(String(20), nullable=True, default="")
    allergies = Column(Text, default="")
    conditions = Column(Text, default="")
    previous_history = Column(Text, default="")
    current_medications = Column(Text, default="")
    photo = Column(Text, default="")  # base64 data URL
    registered_on = Column(DateTime, default=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    consultations = relationship("Consultation", back_populates="patient", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription", back_populates="patient", cascade="all, delete-orphan")
    history = relationship("MedicalHistory", back_populates="patient", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="patient", cascade="all, delete-orphan")
    emergency_contacts = relationship("EmergencyContact", back_populates="patient", cascade="all, delete-orphan")
    lab_tests = relationship("LabTest", back_populates="patient", cascade="all, delete-orphan")
    user = relationship("User", back_populates="patient", uselist=False, cascade="all, delete-orphan")


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    relation = Column(String(60), default="")
    phone = Column(String(20), nullable=False)
    patient = relationship("Patient", back_populates="emergency_contacts")


class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_code = Column(String(20), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    specialization = Column(String(120), nullable=False)
    qualification = Column(String(120), default="MBBS, MD")
    experience_years = Column(Integer, default=0)
    consultation_fee = Column(Float, default=0)
    rating = Column(Float, default=4.5)
    available = Column(Boolean, default=True)
    photo = Column(Text, default="")
    bio = Column(Text, default="")

    department = relationship("Department", back_populates="doctors")
    slots = relationship("DoctorAvailability", back_populates="doctor", cascade="all, delete-orphan")


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (UniqueConstraint("doctor_id", "slot_date", "slot_time", name="uq_doctor_slot"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    day_name = Column(String(15), nullable=False)
    slot_date = Column(Date, nullable=False)
    slot_time = Column(String(10), nullable=False)
    is_booked = Column(Boolean, default=False)
    doctor = relationship("Doctor", back_populates="slots")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("doctor_id", "slot_date", "slot_time", name="uq_appt_slot"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    appointment_code = Column(String(20), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    slot_date = Column(Date, nullable=False)
    slot_time = Column(String(10), nullable=False)
    reason = Column(Text, default="")
    status = Column(String(20), default="Booked")  # Booked / Completed / Cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor")
    consultation = relationship("Consultation", back_populates="appointment", uselist=False)


class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    symptoms = Column(Text, default="")
    diagnosis = Column(Text, default="")
    treatment = Column(Text, default="")
    notes = Column(Text, default="")
    consultation_date = Column(Date, default=date.today)
    followup_date = Column(Date, nullable=True)

    patient = relationship("Patient", back_populates="consultations")
    doctor = relationship("Doctor")
    appointment = relationship("Appointment", back_populates="consultation")
    prescription = relationship("Prescription", back_populates="consultation", uselist=False,
                                cascade="all, delete-orphan")


class Prescription(Base):
    __tablename__ = "prescriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    prescription_code = Column(String(20), unique=True, nullable=False)
    consultation_id = Column(Integer, ForeignKey("consultations.id", ondelete="CASCADE"), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    instructions = Column(Text, default="")
    followup_date = Column(Date, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    consultation = relationship("Consultation", back_populates="prescription")
    patient = relationship("Patient", back_populates="prescriptions")
    doctor = relationship("Doctor")
    medicines = relationship("PrescriptionMedicine", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionMedicine(Base):
    __tablename__ = "prescription_medicines"
    id = Column(Integer, primary_key=True, autoincrement=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False)
    medicine = Column(String(120), nullable=False)
    dosage = Column(String(60), default="")
    frequency = Column(String(60), default="")
    duration = Column(String(60), default="")
    notes = Column(String(255), default="")
    prescription = relationship("Prescription", back_populates="medicines")


class MedicalHistory(Base):
    __tablename__ = "medical_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(40), nullable=False)  # Registration/Appointment/Consultation/Prescription/Emergency
    title = Column(String(160), nullable=False)
    detail = Column(Text, default="")
    event_date = Column(DateTime, default=datetime.utcnow)
    patient = relationship("Patient", back_populates="history")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    message = Column(String(255), nullable=False)
    category = Column(String(30), default="info")
    priority = Column(String(10), default="normal")  # low / normal / high
    channel = Column(String(40), default="in_app")   # in_app, in_app+email, in_app+sms, in_app+email+sms
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    patient = relationship("Patient", back_populates="notifications")


class BloodStock(Base):
    __tablename__ = "blood_stock"
    id = Column(Integer, primary_key=True, autoincrement=True)
    blood_group = Column(String(5), unique=True, nullable=False)
    units = Column(Integer, default=0)


class AmbulanceRequest(Base):
    __tablename__ = "ambulance_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    pickup_address = Column(Text, nullable=False)
    contact_number = Column(String(20), nullable=False)
    emergency_type = Column(String(80), default="General")
    status = Column(String(20), default="Dispatched")
    created_at = Column(DateTime, default=datetime.utcnow)


class LabTest(Base):
    """Lab tests ordered for a patient (from a consultation or standalone)."""
    __tablename__ = "lab_tests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_code = Column(String(20), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True)
    test_name = Column(String(160), nullable=False)
    status = Column(String(20), default="Pending")  # Pending / In Progress / Completed
    ordered_date = Column(Date, default=date.today)
    result_date = Column(Date, nullable=True)
    result_summary = Column(Text, default="")

    patient = relationship("Patient", back_populates="lab_tests")
    doctor = relationship("Doctor")


class User(Base):
    """Authentication account, linked 1:1 to a patient profile."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="patient")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    reset_token_hash = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="user")


class Bill(Base):
    """A hospital invoice for a patient, made up of one or more line items."""
    __tablename__ = "bills"
    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String(20), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True)
    invoice_date = Column(Date, default=date.today)
    subtotal = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    amount_paid = Column(Float, default=0.0)
    status = Column(String(20), default="Pending")  # Paid / Pending / Partially Paid / Failed / Refunded
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")
    doctor = relationship("Doctor")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bill", cascade="all, delete-orphan")


class BillItem(Base):
    __tablename__ = "bill_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(200), nullable=False)
    category = Column(String(40), default="Other")  # Consultation/Lab/Medicine/Bed/Emergency/Ambulance/Other
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)

    bill = relationship("Bill", back_populates="items")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(40), unique=True, nullable=False)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(20), default="Cash")  # UPI/Card/NetBanking/Cash/Online
    status = Column(String(20), default="Pending")  # Success/Pending/Failed/Refunded
    created_at = Column(DateTime, default=datetime.utcnow)

    bill = relationship("Bill", back_populates="payments")
    patient = relationship("Patient")


class PushSubscription(Base):
    """Browser/phone push subscription (Web Push standard) for real-time alerts
    delivered to a patient's device, even when MediTrack isn't open."""
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    endpoint = Column(String(500), unique=True, nullable=False)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")
