import uvicorn
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
class GradeRecord(BaseModel):
    student_id: int
    subject_id: int
    grade: int
    date: str
class AttendanceRecord(BaseModel):
    student_id: int
    subject_id: int
    date: str
    present: bool
class User(BaseModel):
    username: str
    role: str  # 'admin', 'curator', 'teacher'

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class Student(BaseModel):
    id: int
    name: str
    specialty: str
    start_date: str
    end_date: str
    subjects: List[int]
    attendance: List[bool] = []
    grades: List[int] = []

class Subject(BaseModel):
    id: int
    name: str
    teacher: str
    hours: int
    students: List[int]

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
    Student(id=1, name="Иван Иванов", specialty="Программирование", start_date="2023-09-01", end_date="2027-06-01", subjects=[1, 2]),
    Student(id=2, name="Мария Петрова", specialty="Дизайн", start_date="2023-09-01", end_date="2027-06-01", subjects=[1]),
]

subjects_db = [
    Subject(id=1, name="Математика", teacher="teacher", hours=60, students=[1, 2]),
    Subject(id=2, name="Программирование", teacher="teacher", hours=120, students=[1]),
]

grade_records_db = [
    GradeRecord(student_id=1, subject_id=1, grade=5, date="2023-10-01"),
    GradeRecord(student_id=1, subject_id=2, grade=4, date="2023-10-05"),
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
        role: str = payload.get("role")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return {"username": username, "role": role}

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
    access_token = create_access_token(data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# Защищенные маршруты
@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(verify_token)):
    return get_user(current_user["username"])

# CRUD для студентов
@app.get("/students/{student_id}", response_model=dict)
async def get_student(student_id: int, current_user: User = Depends(verify_token)):
    """
    Получить информацию о студенте, включая посещаемость и оценки по предметам.
    """
    # Проверка прав доступа
    if current_user["role"] not in ["admin", "curator", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Поиск студента
    student = next((s for s in students_db if s.id == student_id), None)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Фильтрация данных о посещаемости и оценках
    attendance_data = [
        {"subject_id": a.subject_id, "date": a.date, "present": a.present}
        for a in attendance_records_db
        if a.student_id == student_id
    ]
    grades_data = [
        {"subject_id": g.subject_id, "grade": g.grade, "date": g.date}
        for g in grade_records_db
        if g.student_id == student_id
    ]

    # Группировка данных по предметам
    subjects_info = {}
    for subject in subjects_db:
        if subject.id in student.subjects:
            subjects_info[subject.id] = {
                "subject_name": subject.name,
                "attendance": [],
                "grades": [],
            }

    for record in attendance_data:
        subject_id = record["subject_id"]
        if subject_id in subjects_info:
            subjects_info[subject_id]["attendance"].append(
                {"date": record["date"], "present": record["present"]}
            )

    for record in grades_data:
        subject_id = record["subject_id"]
        if subject_id in subjects_info:
            subjects_info[subject_id]["grades"].append(
                {"date": record["date"], "grade": record["grade"]}
            )

    # Подготовка результата
    result = {
        "id": student.id,
        "name": student.name,
        "specialty": student.specialty,
        "start_date": student.start_date,
        "end_date": student.end_date,
        "subjects": [
            {
                "subject_id": subject_id,
                "subject_name": info["subject_name"],
                "attendance": info["attendance"],
                "grades": info["grades"],
            }
            for subject_id, info in subjects_info.items()
        ],
    }

    return result

@app.put("/students/{student_id}", response_model=Student)
async def update_student(
    student_id: int,
    updated_student: Student,
    current_user: User = Depends(verify_token),
):
    """
    Обновить данные студента.
    Доступно только администратору и куратору.
    """
    if current_user["role"] not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for student in students_db:
        if student.id == student_id:
            # Обновляем только основные поля
            student.name = updated_student.name
            student.specialty = updated_student.specialty
            student.start_date = updated_student.start_date
            student.end_date = updated_student.end_date
            student.subjects = updated_student.subjects  # Обновляем список предметов
            return student

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

@app.post("/students", response_model=Student)
async def create_student(
    student: Student,
    current_user: User = Depends(verify_token),
):
    """
    Создать нового студента.
    Доступно только администратору и куратору.
    """
    if current_user["role"] not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Проверяем уникальность ID
    if any(s.id == student.id for s in students_db):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student with this ID already exists")

    # Добавляем нового студента
    students_db.append(student)
    return student
#CRUD для предметов
# CRUD для предметов

@app.get("/subjects", response_model=List[Subject])
async def get_subjects(current_user: User = Depends(verify_token)):
    """
    Получить список всех предметов.
    Доступно всем авторизованным пользователям.
    """
    return subjects_db

@app.post("/subjects", response_model=Subject)
async def create_subject(subject: Subject, current_user: User = Depends(verify_token)):
    """
    Создать новый предмет.
    Доступно только администратору и куратору.
    """
    if current_user["role"] not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    subjects_db.append(subject)
    return subject

@app.put("/subjects/{subject_id}", response_model=Subject)
async def update_subject(subject_id: int, updated_subject: Subject, current_user: User = Depends(verify_token)):
    """
    Обновить данные о предмете.
    Доступно только администратору и куратору.
    """
    if current_user["role"] not in ["admin", "curator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    for subject in subjects_db:
        if subject.id == subject_id:
            subject.name = updated_subject.name
            subject.teacher = updated_subject.teacher
            subject.hours = updated_subject.hours
            return subject
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

@app.delete("/subjects/{subject_id}")
async def delete_subject(subject_id: int, current_user: User = Depends(verify_token)):
    """
    Удалить предмет.
    Доступно только администратору.
    """
    if current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    for i, subject in enumerate(subjects_db):
        if subject.id == subject_id:
            del subjects_db[i]
            return {"message": f"Subject with id {subject_id} deleted"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

# Отчетность
@app.get("/export/attendance")
async def export_attendance_to_excel(current_user: User = Depends(verify_token)):
    if current_user["role"] not in ["admin", "curator"]:
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

# Обновление посещаемости
@app.put("/students/{student_id}/attendance", response_model=Student)
async def update_student_attendance(
    student_id: int,
    attendance_data: List[bool],
    current_user: User = Depends(verify_token),
):
    if current_user["role"] not in ["admin", "curator", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for student in students_db:
        if student.id == student_id:
            student.attendance = attendance_data
            return student

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

# Выставление оценок
@app.put("/students/{student_id}/grades", response_model=Student)
async def update_student_grades(
    student_id: int,
    grades_data: List[int],
    current_user: User = Depends(verify_token),
):
    if current_user["role"] not in ["admin", "curator", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for student in students_db:
        if student.id == student_id:
            student.grades = grades_data
            return student

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")


@app.post("/grades")
async def add_grade(record: GradeRecord, current_user: User = Depends(verify_token)):
    """
    Добавить оценку.
    Доступно преподавателям, администраторам и кураторам.
    """
    if current_user["role"] not in ["admin", "curator", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    grade_records_db.append(record)
    return {"message": "Grade record added"}


@app.get("/students/{student_id}/grades/{subject_id}")
async def get_student_grades(student_id: int, subject_id: int, current_user: User = Depends(verify_token)):
    """
    Получить оценки студента по конкретному предмету.
    """
    grades = [g for g in grade_records_db if g.student_id == student_id and g.subject_id == subject_id]
    if not grades:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No grades found")
    return grades


@app.post("/attendance")
async def add_attendance(record: AttendanceRecord, current_user: User = Depends(verify_token)):
    """
    Добавить запись о посещаемости.
    Доступно преподавателям, администраторам и кураторам.
    """
    if current_user["role"] not in ["admin", "curator", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    attendance_records_db.append(record)
    return {"message": "Attendance record added"}


@app.get("/students/{student_id}/attendance/{subject_id}")
async def get_student_attendance(student_id: int, subject_id: int, current_user: User = Depends(verify_token)):
    """
    Получить данные о посещаемости студента по конкретному предмету.
    """
    attendance = [a for a in attendance_records_db if a.student_id == student_id and a.subject_id == subject_id]
    if not attendance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No attendance records found")
    return attendance
@app.get("/students/{student_id}/details")
async def get_student_details(student_id: int, current_user: User = Depends(verify_token)):
    """
    Получить подробную информацию о студенте, включая посещаемость и оценки по предметам.
    """
    # Проверка прав доступа
    if current_user["role"] not in ["admin", "curator", "teacher"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Поиск студента
    student = next((s for s in students_db if s.id == student_id), None)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Фильтрация данных о посещаемости и оценках
    attendance_data = [
        {"subject_id": a.subject_id, "date": a.date, "present": a.present}
        for a in attendance_records_db
        if a.student_id == student_id
    ]
    grades_data = [
        {"subject_id": g.subject_id, "grade": g.grade, "date": g.date}
        for g in grade_records_db
        if g.student_id == student_id
    ]

    # Группировка данных по предметам
    subjects_info = {}
    for subject in subjects_db:
        if subject.id in student.subjects:
            subjects_info[subject.id] = {
                "subject_name": subject.name,
                "attendance": [],
                "grades": [],
            }

    for record in attendance_data:
        subject_id = record["subject_id"]
        if subject_id in subjects_info:
            subjects_info[subject_id]["attendance"].append(
                {"date": record["date"], "present": record["present"]}
            )

    for record in grades_data:
        subject_id = record["subject_id"]
        if subject_id in subjects_info:
            subjects_info[subject_id]["grades"].append(
                {"date": record["date"], "grade": record["grade"]}
            )

    # Подготовка результата
    result = {
        "id": student.id,
        "name": student.name,
        "specialty": student.specialty,
        "start_date": student.start_date,
        "end_date": student.end_date,
        "subjects": [
            {
                "subject_id": subject_id,
                "subject_name": info["subject_name"],
                "attendance": info["attendance"],
                "grades": info["grades"],
            }
            for subject_id, info in subjects_info.items()
        ],
    }

    return result


if __name__ == '__main__':
    uvicorn.run(app, port=8000)