-- MediTrack – MySQL schema (reference; SQLAlchemy also creates these automatically)
CREATE DATABASE IF NOT EXISTS meditrack CHARACTER SET utf8mb4;
USE meditrack;

CREATE TABLE IF NOT EXISTS departments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  description VARCHAR(255) DEFAULT ''
);

CREATE TABLE IF NOT EXISTS patients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_code VARCHAR(20) NOT NULL UNIQUE,
  full_name VARCHAR(120) NOT NULL,
  dob DATE NOT NULL,
  age INT NOT NULL,
  gender VARCHAR(20) NOT NULL,
  blood_group VARCHAR(5) NOT NULL,
  phone VARCHAR(20) NOT NULL UNIQUE,
  email VARCHAR(120) NOT NULL UNIQUE,
  address TEXT,
  emergency_contact_name VARCHAR(120) NOT NULL,
  emergency_contact_number VARCHAR(20) NOT NULL,
  allergies TEXT, conditions TEXT, previous_history TEXT, current_medications TEXT,
  photo LONGTEXT,
  registered_on DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS emergency_contacts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  name VARCHAR(120) NOT NULL, relation VARCHAR(60), phone VARCHAR(20) NOT NULL,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS doctors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  doctor_code VARCHAR(20) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  department_id INT NOT NULL,
  specialization VARCHAR(120) NOT NULL,
  qualification VARCHAR(120), experience_years INT DEFAULT 0,
  consultation_fee FLOAT DEFAULT 0, rating FLOAT DEFAULT 4.5,
  available BOOLEAN DEFAULT TRUE, photo LONGTEXT, bio TEXT,
  FOREIGN KEY (department_id) REFERENCES departments(id)
);

CREATE TABLE IF NOT EXISTS doctor_availability (
  id INT AUTO_INCREMENT PRIMARY KEY,
  doctor_id INT NOT NULL, day_name VARCHAR(15) NOT NULL,
  slot_date DATE NOT NULL, slot_time VARCHAR(10) NOT NULL,
  is_booked BOOLEAN DEFAULT FALSE,
  UNIQUE KEY uq_doctor_slot (doctor_id, slot_date, slot_time),
  FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appointments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  appointment_code VARCHAR(20) NOT NULL UNIQUE,
  patient_id INT NOT NULL, doctor_id INT NOT NULL,
  slot_date DATE NOT NULL, slot_time VARCHAR(10) NOT NULL,
  reason TEXT, status VARCHAR(20) DEFAULT 'Booked',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_appt_slot (doctor_id, slot_date, slot_time),
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
  FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

CREATE TABLE IF NOT EXISTS consultations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  appointment_id INT NOT NULL UNIQUE, patient_id INT NOT NULL, doctor_id INT NOT NULL,
  symptoms TEXT, diagnosis TEXT, treatment TEXT, notes TEXT,
  consultation_date DATE, followup_date DATE,
  FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
  FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

CREATE TABLE IF NOT EXISTS prescriptions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  prescription_code VARCHAR(20) NOT NULL UNIQUE,
  consultation_id INT NOT NULL UNIQUE, patient_id INT NOT NULL, doctor_id INT NOT NULL,
  instructions TEXT, followup_date DATE, active BOOLEAN DEFAULT TRUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE CASCADE,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
  FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

CREATE TABLE IF NOT EXISTS prescription_medicines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  prescription_id INT NOT NULL,
  medicine VARCHAR(120) NOT NULL, dosage VARCHAR(60), frequency VARCHAR(60),
  duration VARCHAR(60), notes VARCHAR(255),
  FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS medical_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL, event_type VARCHAR(40) NOT NULL,
  title VARCHAR(160) NOT NULL, detail TEXT,
  event_date DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL, message VARCHAR(255) NOT NULL,
  category VARCHAR(30) DEFAULT 'info', is_read BOOLEAN DEFAULT FALSE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS blood_stock (
  id INT AUTO_INCREMENT PRIMARY KEY,
  blood_group VARCHAR(5) NOT NULL UNIQUE, units INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ambulance_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL, pickup_address TEXT NOT NULL,
  contact_number VARCHAR(20) NOT NULL, emergency_type VARCHAR(80),
  status VARCHAR(20) DEFAULT 'Dispatched',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);
