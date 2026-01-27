from extensions import db
from datetime import datetime

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    price_per_class = db.Column(db.Float, default=0.0)
    active = db.Column(db.Boolean, default=True)
    # Cascade delete para limpar aulas se curso for deletado
    lessons = db.relationship('Lesson', backref='course', lazy=True, cascade="all, delete-orphan", order_by='Lesson.order')
    classes = db.relationship('Turma', backref='course', lazy=True)

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    order = db.Column(db.Integer, default=0)
    link_presentation = db.Column(db.String(500))
    link_guide = db.Column(db.String(500))

class Turma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    active = db.Column(db.Boolean, default=True)
    
    link_backoffice = db.Column(db.String(500))
    link_whatsapp = db.Column(db.String(500))
    link_extra = db.Column(db.String(500))

    schedule_days = db.Column(db.String(20)) 
    start_time = db.Column(db.String(5))
    start_date = db.Column(db.Date, nullable=True)
    
    total_classes = db.Column(db.Integer, default=40)

class Holiday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)

class CalendarEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    turma_id = db.Column(db.Integer, db.ForeignKey('turma.id'), nullable=True)
    turma = db.relationship('Turma', backref='calendar_events', lazy=True)

    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    duration = db.Column(db.Integer)
    price = db.Column(db.Float)
    
    status = db.Column(db.String(20), default='scheduled') 
    
    # NOVO: Para controlar a reativação de 30min
    cancelled_at = db.Column(db.DateTime, nullable=True)

    is_extra = db.Column(db.Boolean, default=False)
    is_replacement = db.Column(db.Boolean, default=False) 
    
    student_name = db.Column(db.String(100))
    extra_link = db.Column(db.String(500))
    lesson_title_given = db.Column(db.String(200))