from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from extensions import db
from models import Course, Turma, Lesson, CalendarEvent, Holiday
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/')
def index():
    courses = Course.query.all()
    turmas = Turma.query.all()
    # Ordena as lições para exibição
    for c in courses:
        c.lessons.sort(key=lambda x: x.order)
    return render_template('admin/index.html', courses=courses, turmas=turmas)

@admin_bp.route('/save_course', methods=['POST'])
def save_course():
    course_id = request.form.get('id')
    name = request.form.get('name')
    duration = request.form.get('duration')
    price = request.form.get('price')

    if course_id:
        course = Course.query.get(course_id)
    else:
        course = Course()
        db.session.add(course)

    course.name = name
    course.duration_minutes = int(duration) if duration else 60
    course.price_per_class = float(price) if price else 0.0
    
    db.session.commit()
    flash('Curso salvo com sucesso!', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/api/update_lesson', methods=['POST'])
def api_update_lesson():
    data = request.json
    lesson_id = data.get('id')
    field = data.get('field') # 'link_presentation' ou 'link_guide'
    value = data.get('value')
    
    lesson = Lesson.query.get_or_404(lesson_id)
    
    if field == 'link_presentation':
        lesson.link_presentation = value
    elif field == 'link_guide':
        lesson.link_guide = value
        
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/api/import_lessons/<int:course_id>', methods=['POST'])
def api_import_lessons(course_id):
    course = Course.query.get_or_404(course_id)
    file = request.files.get('lessons_file')
    
    if file:
        content = file.read().decode('utf-8')
        lines = content.split('\n')
        
        # Pega a última ordem existente para adicionar no final
        last_lesson = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order.desc()).first()
        current_order = last_lesson.order + 1 if last_lesson else 0
        
        added_count = 0
        for line in lines:
            if line.strip():
                lesson = Lesson(
                    course_id=course.id,
                    title=line.strip(),
                    order=current_order
                )
                db.session.add(lesson)
                current_order += 1
                added_count += 1
        db.session.commit()
        return jsonify({'success': True, 'message': f'{added_count} aulas importadas!', 'course_id': course.id})
    
    return jsonify({'success': False, 'message': 'Arquivo inválido'})

# NOVO: API para buscar as aulas (para atualizar a lista via JS)
@admin_bp.route('/api/get_lessons/<int:course_id>')
def api_get_lessons(course_id):
    lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order).all()
    lessons_data = [{
        'id': l.id, 
        'title': l.title, 
        'link_p': l.link_presentation, 
        'link_g': l.link_guide
    } for l in lessons]
    return jsonify(lessons_data)

# NOVO: Remover Lição
@admin_bp.route('/delete_lesson/<int:lesson_id>')
def delete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    course_id = lesson.course_id
    db.session.delete(lesson)
    db.session.commit()
    # Se a chamada for via AJAX, deveria retornar JSON, mas para simplificar
    # vamos assumir redirecionamento ou uso da API de listagem
    return redirect(url_for('admin.index')) # Fallback

# NOVO: API Deletar lição (para usar no modal)
@admin_bp.route('/api/delete_lesson/<int:lesson_id>', methods=['DELETE'])
def api_delete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    db.session.delete(lesson)
    db.session.commit()
    return jsonify({'success': True})

# --- MANTENHA AS OUTRAS ROTAS (save_class, add_holiday, etc) IGUAIS ---
# (Copie as rotas save_class, add_holiday, delete_holiday, add_replacement, add_extra do seu arquivo anterior)
# ...
@admin_bp.route('/save_class', methods=['POST'])
def save_class():
    # ... (seu código existente) ...
    class_id = request.form.get('id')
    if class_id:
        turma = Turma.query.get(class_id)
    else:
        turma = Turma()
        db.session.add(turma)

    turma.name = request.form.get('name')
    turma.course_id = request.form.get('course_id')
    turma.start_time = request.form.get('start_time')
    
    total = request.form.get('total_classes')
    turma.total_classes = int(total) if total else 40

    start_date_str = request.form.get('start_date')
    if start_date_str:
        turma.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

    days_list = request.form.getlist('days')
    turma.schedule_days = ",".join(days_list)
    turma.link_backoffice = request.form.get('link_backoffice')
    turma.link_whatsapp = request.form.get('link_whatsapp')
    turma.link_extra = request.form.get('link_extra')
    turma.active = True if request.form.get('active') else False

    db.session.commit()
    flash('Turma salva com sucesso!', 'success')
    return redirect(url_for('admin.index'))

@admin_bp.route('/add_holiday', methods=['POST'])
def add_holiday():
    date_str = request.form.get('date')
    name = request.form.get('name')
    if date_str and name:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        holiday = Holiday(date=date_obj, name=name)
        db.session.add(holiday)
        events_on_date = CalendarEvent.query.filter_by(date=date_obj).all()
        for event in events_on_date:
            event.status = 'holiday' 
        db.session.commit()
        flash(f'Feriado "{name}" adicionado.', 'success')
    return redirect(url_for('main.planner'))

@admin_bp.route('/delete_holiday/<int:id>')
def delete_holiday(id):
    holiday = Holiday.query.get_or_404(id)
    events = CalendarEvent.query.filter_by(date=holiday.date, status='holiday').all()
    for event in events:
        event.status = 'scheduled'
    db.session.delete(holiday)
    db.session.commit()
    flash(f'Feriado removido.', 'info')
    return redirect(url_for('main.planner'))

@admin_bp.route('/add_replacement', methods=['POST'])
def add_replacement():
    try:
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        student_name = request.form.get('student_name')
        link_backoffice = request.form.get('link_backoffice')
        event = CalendarEvent(
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            start_time=time_str,
            duration=60, price=0.0, status='scheduled',
            is_extra=False, is_replacement=True,
            student_name=student_name, extra_link=link_backoffice
        )
        db.session.add(event)
        db.session.commit()
        flash('Reposição agendada!', 'success')
    except Exception as e:
        flash(f'Erro: {str(e)}', 'danger')
    return redirect(url_for('main.planner'))

@admin_bp.route('/add_extra', methods=['POST'])
def add_extra():
    try:
        date_str = request.form.get('date')
        time_str = request.form.get('start_time')
        duration = int(request.form.get('duration_option'))
        price = 30.0 if duration == 60 else 20.0
        turma_id_raw = request.form.get('turma_id')
        event = CalendarEvent(
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            start_time=time_str,
            duration=duration, price=price, status='scheduled', is_extra=True
        )
        if turma_id_raw == 'other':
            event.student_name = request.form.get('student_name')
            event.extra_link = request.form.get('link_backoffice') 
        else:
            event.turma_id = int(turma_id_raw)
        db.session.add(event)
        db.session.commit()
        flash('Aula extra agendada!', 'success')
    except Exception as e:
        flash(f'Erro ao agendar: {str(e)}', 'danger')
    return redirect(url_for('main.planner'))

#API para buscar dados da turma para edição
@admin_bp.route('/api/get_class/<int:class_id>')
def api_get_class(class_id):
    turma = Turma.query.get_or_404(class_id)
    return jsonify({
        'id': turma.id,
        'name': turma.name,
        'course_id': turma.course_id,
        'start_time': turma.start_time,
        'start_date': turma.start_date.strftime('%Y-%m-%d') if turma.start_date else '',
        'total_classes': turma.total_classes,
        'active': turma.active,
        # Transforma a string "0,2,4" em lista ["0", "2", "4"]
        'schedule_days': turma.schedule_days.split(',') if turma.schedule_days else [],
        'link_backoffice': turma.link_backoffice or '',
        'link_whatsapp': turma.link_whatsapp or '',
        'link_extra': turma.link_extra or ''
    })