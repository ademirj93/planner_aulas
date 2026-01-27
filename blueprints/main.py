from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Turma, CalendarEvent, Holiday, Lesson
from datetime import datetime, timedelta
import calendar
from collections import defaultdict

main_bp = Blueprint('main', __name__)

# --- FUNÇÕES AUXILIARES ---


def format_weekdays(days_str):
    if not days_str:
        return ""
    map_days = {'0': 'Seg', '1': 'Ter', '2': 'Qua',
                '3': 'Qui', '4': 'Sex', '5': 'Sáb', '6': 'Dom'}
    labels = [map_days.get(d) for d in days_str.split(',') if d in map_days]
    return ", ".join(labels)


def get_next_lesson_date(event):
    next_event = CalendarEvent.query.filter(
        CalendarEvent.turma_id == event.turma_id,
        CalendarEvent.date > event.date,
        CalendarEvent.status != 'cancelled',
        CalendarEvent.status != 'holiday'
    ).order_by(CalendarEvent.date).first()
    return next_event.date.strftime('%d/%m') if next_event else "A definir"


def generate_events_for_period(start_date, end_date):
    turmas = Turma.query.filter_by(active=True).all()
    holidays = {h.date: h.name for h in Holiday.query.all()}

    current = start_date
    while current <= end_date:
        weekday = str(current.weekday())
        current_date_obj = current.date()

        if current_date_obj in holidays:
            current += timedelta(days=1)
            continue

        for turma in turmas:
            if turma.schedule_days and weekday in turma.schedule_days.split(','):
                if turma.start_date and current_date_obj < turma.start_date:
                    continue

                valid_classes_count = CalendarEvent.query.filter(
                    CalendarEvent.turma_id == turma.id,
                    CalendarEvent.status.notin_(['cancelled', 'holiday']),
                    CalendarEvent.is_extra == False,
                    CalendarEvent.is_replacement == False
                ).count()

                if valid_classes_count >= turma.total_classes:
                    continue

                exists = CalendarEvent.query.filter_by(
                    turma_id=turma.id, date=current_date_obj).first()

                if not exists:
                    new_event = CalendarEvent(
                        turma_id=turma.id,
                        date=current_date_obj,
                        start_time=turma.start_time,
                        duration=turma.course.duration_minutes,
                        price=turma.course.price_per_class,
                        status='scheduled'
                    )
                    db.session.add(new_event)
                else:
                    # Atualiza preço se mudar
                    if exists.status == 'scheduled' and not exists.is_extra and not exists.is_replacement:
                        if exists.price != turma.course.price_per_class:
                            exists.price = turma.course.price_per_class

        current += timedelta(days=1)
    db.session.commit()


@main_bp.route('/toggle_status/<int:event_id>/<string:action>')
def toggle_status(event_id, action):
    event = CalendarEvent.query.get_or_404(event_id)

    if action == 'cancel':
        event.status = 'cancelled'
        event.cancelled_at = datetime.now()
    elif action == 'reactivate':
        if event.cancelled_at:
            time_diff = datetime.now() - event.cancelled_at
            if time_diff.total_seconds() / 60 <= 30:
                event.status = 'scheduled'
                event.cancelled_at = None
            else:
                flash('Prazo de 30 minutos expirou.', 'warning')
        else:
            flash('Não é possível reativar aula antiga.', 'warning')

    db.session.commit()
    return redirect(url_for('main.planner'))


# Em blueprints/main.py

@main_bp.route('/')
def planner():
    # 1. Definição de Datas (Semana)
    selected_date_str = request.args.get('date')
    if selected_date_str:
        today = datetime.strptime(selected_date_str, '%Y-%m-%d')
    else:
        today = datetime.today()

    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    # 2. Opções do Seletor
    weeks_options = []
    base_week = start_of_week - timedelta(weeks=5)
    for _ in range(12):
        w_end = base_week + timedelta(days=6)
        weeks_options.append({
            'value': base_week.strftime('%Y-%m-%d'),
            'label': f"{base_week.strftime('%d/%m')} a {w_end.strftime('%d/%m')}",
            'selected': base_week.date() == start_of_week.date()
        })
        base_week += timedelta(weeks=1)

    # 3. Geração de Eventos Futuros
    generation_end = end_of_week + timedelta(days=45) 
    generate_events_for_period(start_of_week, generation_end)
    
    # 4. Busca Eventos
    events = CalendarEvent.query.filter(
        CalendarEvent.date >= start_of_week.date(),
        CalendarEvent.date <= end_of_week.date()
    ).order_by(CalendarEvent.date, CalendarEvent.start_time).all()

    holidays_list = Holiday.query.order_by(Holiday.date).all()
    
    # 5. Preparação de Dados
    next_dates = {}
    weekdays_map = {}
    lesson_info = {} 
    
    from collections import defaultdict
    grouped_events = defaultdict(list)
    
    for event in events:
        grouped_events[event.date].append(event)
        
        if event.turma:
            next_dates[event.id] = get_next_lesson_date(event)
            weekdays_map[event.id] = format_weekdays(event.turma.schedule_days)
            
            # Conta aulas passadas para saber qual lição é a atual
            previous_valid_count = CalendarEvent.query.filter(
                CalendarEvent.turma_id == event.turma_id,
                CalendarEvent.date < event.date,
                CalendarEvent.status.notin_(['cancelled', 'holiday']),
                CalendarEvent.is_extra == False,
                CalendarEvent.is_replacement == False
            ).count()
            
            current_lesson = Lesson.query.filter_by(
                course_id=event.turma.course_id, 
                order=previous_valid_count
            ).first()
            
            next_lesson = Lesson.query.filter_by(
                course_id=event.turma.course_id, 
                order=previous_valid_count + 1
            ).first()
            
            # --- AQUI ESTÁ O SEGREDO: ENVIAR OS LINKS ---
            lesson_info[event.id] = {
                'current': current_lesson.title if current_lesson else f"Aula {previous_valid_count + 1}",
                'link_p': current_lesson.link_presentation if current_lesson else None, # <--- VERIFIQUE ISSO
                'link_g': current_lesson.link_guide if current_lesson else None,        # <--- VERIFIQUE ISSO
                'next': next_lesson.title if next_lesson else "-"
            }
        else:
            next_dates[event.id] = "-"
            weekdays_map[event.id] = "Avulso"
            lesson_info[event.id] = {'current': '-', 'link_p': None, 'link_g': None, 'next': '-'}

    # 6. Agrupamento para HTML
    week_names = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
    daily_planner = []
    
    current_day_iter = start_of_week
    for i in range(7):
        current_date_only = current_day_iter.date()
        daily_planner.append({
            'date': current_date_only,
            'label': f"{week_names[i]}, {current_date_only.strftime('%d/%m')}",
            'events': grouped_events.get(current_date_only, [])
        })
        current_day_iter += timedelta(days=1)

    total_val = sum(e.price for e in events if e.status not in ['cancelled', 'holiday'] and not e.is_extra)
    
    return render_template('planner.html', 
                           daily_planner=daily_planner,
                           total_expected=total_val,
                           get_form_url=get_google_form_url,
                           holidays_list=holidays_list,
                           next_dates=next_dates,
                           weekdays_map=weekdays_map,
                           lesson_info=lesson_info,
                           weeks_options=weeks_options,
                           current_date=start_of_week)


def get_google_form_url(form_type, data):
    base_url = ""
    params = ""
    if form_type == 'cancel':
        base_url = "https://docs.google.com/forms/d/e/1FAIpQLSdha0_aJPJ4b_twUIp4RlicSZrZLmn2tjgWrPmh-mWpeIIEpQ/viewform"
        params = f"?entry.123456={data.get('turma')}&entry.987654={data.get('data')}"
    elif form_type == 'extra' or form_type == 'replacement':
        base_url = "https://docs.google.com/forms/d/e/1FAIpQLSfppTLjIadUpPImdxqK4a53sEJoFLLvGfBbWCQjjYsVk62-Dw/viewform"
        params = f"?entry.111222={data.get('aluno')}&entry.333444={data.get('valor')}"
    return base_url + params
