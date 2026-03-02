📚 Library Management System (Flask + MySQL)

A complete Library Management System built using Python Flask and MySQL.
This system supports Admin and Student roles, book issuing/returning, fine calculation, and automatic book cover fetching using Google Books API.

🚀 Features
👨‍🎓 Student Module

Student Registration & Login

View Available Books

Search by Title / Author / Category

Issue Books (14-day loan period)

Return Books

Automatic Late Fine Calculation (₹2 per day)

Dashboard with:

Issued Books

Overdue Status

Total Fine

Issue History

👨‍💼 Admin Module

Secure Admin Login

Add / Edit / Delete Books

View All Students

View Issued Books

Return Books from Admin Panel

Track Overdue Books

View Total Fine Collection

Dashboard Statistics:

Total Books

Available Books

Issued Books

Total Students

Overdue Count

🛠️ Technologies Used

Backend: Python (Flask)

Database: MySQL

Frontend: HTML, CSS (Jinja Templates)

API Integration: Google Books API (for automatic book covers)

Authentication: Session-based login system

Password Security: SHA-256 Hashing

🗄️ Database Structure

The system automatically creates the database and tables if they don’t exist.

Tables:

admins

students

books

issues

All data persists across restarts.

⚙️ Installation & Setup
1️⃣ Clone the Repository
git clone https://github.com/your-username/library-management-system.git
cd library-management-system
2️⃣ Install Dependencies
pip install flask mysql-connector-python
3️⃣ Configure Database

Update these values inside app.py:

DB_HOST = "localhost"
DB_USER = "your_mysql_username"
DB_PASS = "your_mysql_password"
DB_NAME = "library_db"

Make sure MySQL server is running.

4️⃣ Run the Application
python app.py

Open in browser:

http://127.0.0.1:5000/
🔐 Default Admin Credentials
Email: admin@library.com
Password: ********

⚠️ Change password after first login for security.

📌 Business Logic

Loan Period: 14 Days

Late Fine: ₹2 per day

Book cannot be deleted if currently issued

Student cannot issue same book twice

Book availability automatically updates on issue/return

Overdue status dynamically calculated

📸 Automatic Book Cover Feature

When an admin adds a new book:

System automatically fetches book cover from Google Books API

If not available, a placeholder cover is generated

📊 Project Highlights (For Interview)

Role-Based Authentication System

Real-time Fine Calculation Logic

Relational Database Design (Foreign Keys, Constraints)

Secure Password Hashing

REST API Integration

Dynamic Dashboard Statistics

Production-ready Database Initialization

👨‍💻 Author

Nithin Kumar Doddi
B.Tech – Artificial Intelligence & Data Science
Python | Flask | MySQL | Full Stack Developer
