from flask import Blueprint, render_template, request
from extensions import db
from models import CalendarEvent, Turma, Holiday
from sqlalchemy import func
from datetime import datetime, timedelta

finance_bp = Blueprint('finance', __name__)

# --- FUNÇÃO DE CÁLCULO DE TÉRMINO ---
def calculate_end_date(turma):
    """
    Calcula a data prevista para o fim das aulas.
    Lógica: Conta aulas válidas no banco + Projeta as faltantes ignorando feriados.
    """
    if not turma.active:
        return "Concluído/Inativo"

    # 1. Conta quantas aulas válidas (não canceladas/feriado) JÁ EXISTEM no banco
    valid_count = CalendarEvent.query.filter(
        CalendarEvent.turma_id == turma.id,
        CalendarEvent.status.notin_(['cancelled', 'holiday']),
        CalendarEvent.is_extra == False,
        CalendarEvent.is_replacement == False
    ).count()

    remaining = turma.total_classes - valid_count

    # Se já atingiu o total, a última aula válida é a data final
    if remaining <= 0:
        last_event = CalendarEvent.query.filter(
            CalendarEvent.turma_id == turma.id,
            CalendarEvent.status.notin_(['cancelled', 'holiday'])
        ).order_by(CalendarEvent.date.desc()).first()
        return last_event.date.strftime('%d/%m/%Y') if last_event else "Concluído"

    # 2. Se faltam aulas, vamos PROJETAR a partir da última aula registrada
    last_registered_event = CalendarEvent.query.filter_by(turma_id=turma.id)\
        .order_by(CalendarEvent.date.desc()).first()
    
    # Começa a contar do dia seguinte à última aula (ou da data de início se não houver aulas)
    if last_registered_event:
        current_date = last_registered_event.date + timedelta(days=1)
    elif turma.start_date:
        current_date = turma.start_date
    else:
        current_date = datetime.today().date()

    # Prepara dados para o loop
    holidays = {h.date for h in Holiday.query.all()}
    if not turma.schedule_days:
        return "Sem dias definidos"
        
    schedule_days = [int(d) for d in turma.schedule_days.split(',')]
    
    # Loop de projeção (Simula o calendário)
    while remaining > 0:
        # Se for dia de aula E não for feriado, desconta 1
        if current_date.weekday() in schedule_days:
            if current_date not in holidays:
                remaining -= 1
        
        # Se ainda faltar, avança para o próximo dia, a menos que tenhamos acabado de descontar o último
        if remaining > 0:
            current_date += timedelta(days=1)

    return current_date.strftime('%d/%m/%Y')

@finance_bp.route('/')
def index():
    today = datetime.today()
    current_year = today.year
    selected_month = request.args.get('month', today.month, type=int)
    selected_year = request.args.get('year', today.year, type=int)
    period = request.args.get('period', 'all') 

    # --- LÓGICA DO EXTRATO (Mantida igual) ---
    query = CalendarEvent.query.filter(CalendarEvent.status != 'cancelled')
    query = query.filter(func.strftime('%Y', CalendarEvent.date) == str(selected_year))
    query = query.filter(func.strftime('%m', CalendarEvent.date) == f'{selected_month:02d}')

    if period == '1':
        query = query.filter(func.strftime('%d', CalendarEvent.date) <= '15')
    elif period == '2':
        query = query.filter(func.strftime('%d', CalendarEvent.date) > '15')

    classes_history = query.order_by(CalendarEvent.date).all()
    
    total_receber = sum(event.price for event in classes_history)
    count_classes = len(classes_history)
    total_minutes = sum(event.duration for event in classes_history)
    total_hours = round(total_minutes / 60, 2)

    # --- NOVO: LÓGICA DAS ESTIMATIVAS DE TÉRMINO ---
    # Pegamos todas as turmas ativas para calcular
    active_turmas = Turma.query.filter_by(active=True).all()
    estimates = []
    
    for t in active_turmas:
        end_date = calculate_end_date(t)
        
        # Calcula progresso (Aulas Dadas / Total)
        valid_count = CalendarEvent.query.filter(
            CalendarEvent.turma_id == t.id,
            CalendarEvent.status.notin_(['cancelled', 'holiday']),
            CalendarEvent.is_extra == False,
            CalendarEvent.is_replacement == False
        ).count()
        
        estimates.append({
            'name': t.name,
            'course': t.course.name,
            'current': valid_count,
            'total': t.total_classes,
            'end_date': end_date
        })

    return render_template('finance.html', 
                           history=classes_history, 
                           total=total_receber,
                           count_classes=count_classes,
                           total_hours=total_hours,
                           selected_month=selected_month,
                           selected_year=selected_year,
                           selected_period=period,
                           current_year=current_year,
                           estimates=estimates) # <--- Enviando nova lista