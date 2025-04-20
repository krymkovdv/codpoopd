from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd

# Константы для JWT
SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Модели данных
class User(BaseModel):
    username: str
    role: str  # 'admin', 'curator', 'teacher'

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class Student(BaseModel):
    id: int
    name: str
    specialty: str
    start_date: str
    end_date: str
    attendance: List[bool]
    grades: List[int]

class Subject(BaseModel):
    id: int
    name: str
    teacher: str
    hours: int

class AttendanceRecord(BaseModel):
    student_id: int
    subject_id: int
    date: str
    present: bool

# Хранилище данных (вместо базы данных)
users_db = {
    "admin": {"password": "adminpass", "role": "admin"},
    "curator": {"password": "curatorpass", "role": "curator"},
    "teacher": {"password": "teacherpass", "role": "teacher"},
}

students_db = [
    Student(id=1, name="Иван Иванов", specialty="Программирование", start_date="2023-09-01", end_date="2027-06-01", attendance=[True, False], grades=[5, 4]),
    Student(id=2, name="Мария Петрова", specialty="Дизайн", start_date="2023-09-01", end_date="2027-06-01", attendance=[True, True], grades=[4, 5]),
]

subjects_db = [
    Subject(id=1, name="Математика", teacher="teacher", hours=60),
    Subject(id=2, name="Программирование", teacher="teacher", hours=120),
]

attendance_records_db = [
    AttendanceRecord(student_id=1, subject_id=1, date="2023-10-01", present=True),
    AttendanceRecord(student_id=2, subject_id=1, date="2023-10-01", present=False),
]

# Инициализация FastAPI
app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Вспомогательные функции
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def get_user(username: str):
    user_data = users_db.get(username)
    if user_data:
        return User(username=username, role=user_data["role"])
    return None

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user or users_db[username]["password"] != password:
        return None
    return user

# Авторизация
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# Защищенные маршруты
@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(verify_token)):
    return get_user(current_user)

# CRUD для студентов
@app.get("/students", response_model=List[Student])
async def get_students(current_user: User = Depends(verify_token)):
    if current_user.role not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return students_db

@app.post("/students", response_model=Student)
async def create_student(student: Student, current_user: User = Depends(verify_token)):
    if current_user.role not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    students_db.append(student)
    return student

@app.put("/students/{student_id}", response_model=Student)
async def update_student(student_id: int, updated_student: Student, current_user: User = Depends(verify_token)):
    if current_user.role not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    for student in students_db:
        if student.id == student_id:
            student.name = updated_student.name
            student.specialty = updated_student.specialty
            student.start_date = updated_student.start_date
            student.end_date = updated_student.end_date
            student.attendance = updated_student.attendance
            student.grades = updated_student.grades
            return student
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

# Отчетность
@app.get("/export/attendance")
async def export_attendance_to_excel(current_user: User = Depends(verify_token)):
    if current_user.role not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    data = []
    for record in attendance_records_db:
        student = next((s for s in students_db if s.id == record.student_id), None)
        subject = next((s for s in subjects_db if s.id == record.subject_id), None)
        if student and subject:
            data.append({
                "Student": student.name,
                "Subject": subject.name,
                "Date": record.date,
                "Present": record.present,
            })
    df = pd.DataFrame(data)
    file_path = "attendance_report.xlsx"
    df.to_excel(file_path, index=False)
    return {"message": f"Attendance report exported to {file_path}"}