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


def check_auto_completion():
    """
    Verifica aulas agendadas que já passaram do horário (+90min)
    e marca como 'completed_auto'.
    """
    now = datetime.now()
    # Busca eventos agendados de hoje ou antes
    events = CalendarEvent.query.filter(
        CalendarEvent.status == 'scheduled',
        CalendarEvent.date <= now.date()
    ).all()

    for event in events:
        # Se for data passada, conclui
        if event.date < now.date():
            event.status = 'completed_auto'
        # Se for hoje, verifica hora
        elif event.date == now.date():
            try:
                h, m = map(int, event.start_time.split(':'))
                event_dt = datetime(event.date.year, event.date.month, event.date.day, h, m)
                # Se passou 90 min do início + duração (ou fixo 90min de tolerância após inicio)
                # Vamos considerar: Inicio + Duração + 30min tolerância ou apenas Inicio + 90min
                limit = event_dt + timedelta(minutes=90)
                if now > limit:
                    event.status = 'completed_auto'
            except:
                pass # Erro de formato de hora
    db.session.commit()

def generate_events_for_period(view_end_date):
    """
    Gera eventos para todas as turmas ativas.
    CORREÇÃO: Em vez de gerar apenas para a semana visível, verifica
    qual foi a última aula gerada de cada turma e preenche o 'gap' até a data de visualização.
    Isso corrige o problema da contagem de aulas quando a data de início é antiga.
    """
    turmas = Turma.query.filter(Turma.active == True).all()
    holidays = {h.date: h.name for h in Holiday.query.all()}

    for turma in turmas:
        # Determina de onde começar a gerar para ESTA turma
        last_event = CalendarEvent.query.filter_by(turma_id=turma.id).order_by(CalendarEvent.date.desc()).first()
        
        if last_event:
            start_gen = last_event.date + timedelta(days=1)
        elif turma.start_date:
            # SE tiver offset (começar da aula X) e a data de início for passado,
            # começa a gerar de HOJE para não criar eventos retroativos inúteis.
            if turma.lesson_offset > 0 and turma.start_date < datetime.now().date():
                start_gen = datetime.now().date()
            else:
                start_gen = turma.start_date
        else:
            start_gen = datetime.today().date()
            
        # Se a data de início de geração for maior que a data limite de visualização, pula
        if start_gen > view_end_date.date():
            continue
            
        # CONTAGEM INICIAL: Conta quantas aulas válidas já existem no banco (passado + futuro agendado)
        # Isso evita fazer count() dentro do loop repetidamente e corrige o problema de gerar além do limite no mesmo lote.
        valid_classes_count = CalendarEvent.query.filter(
            CalendarEvent.turma_id == turma.id,
            CalendarEvent.status.notin_(['cancelled', 'holiday']),
            CalendarEvent.is_extra == False,
            CalendarEvent.is_replacement == False
        ).count()

        current = start_gen
        
        # Loop dia a dia para esta turma até o fim do período de visualização
        while current <= view_end_date.date():
            if current in holidays:
                current += timedelta(days=1)
                continue
                
            weekday = str(current.weekday())
            
            if turma.schedule_days and weekday in turma.schedule_days.split(','):
                # Verifica limite de aulas considerando o OFFSET (Ajuste de Progresso)
                # Se o aluno pulou aulas (offset > 0) ou repetiu (offset < 0), o limite é sobre o CONTEÚDO.
                current_lesson_index = valid_classes_count + turma.lesson_offset
                
                if current_lesson_index >= turma.total_classes:
                    # Auto-Graduação
                    turma.status = 'graduated'
                    turma.active = False # Desativa para não gerar mais
                    break # Sai do loop desta turma

                exists = CalendarEvent.query.filter_by(
                    turma_id=turma.id, date=current).first()

                if not exists:
                    new_event = CalendarEvent(
                        turma_id=turma.id,
                        date=current,
                        start_time=turma.start_time,
                        duration=turma.course.duration_minutes,
                        price=turma.course.price_per_class,
                        status='scheduled'
                    )
                    db.session.add(new_event)
                    # Incrementa contador local para que a próxima iteração saiba que já existe mais uma aula
                    valid_classes_count += 1
            
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
    elif action == 'conclude':
        event.status = 'completed'
        event.cancelled_at = None
    elif action == 'replacement':
        event.status = 'completed'
        event.is_replacement = True
        event.cancelled_at = None
    elif action == 'scheduled':
        # Permite voltar de concluído para agendado se necessário
        event.status = 'scheduled'
        event.is_replacement = False
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
        # Se não tem data selecionada, gera eventos futuros para encontrar a próxima aula real
        generate_events_for_period(datetime.today() + timedelta(days=60))
        
        now_date = datetime.now().date()
        # Busca a primeira aula válida de hoje em diante
        next_event = CalendarEvent.query.filter(
            CalendarEvent.date >= now_date,
            CalendarEvent.status.notin_(['cancelled', 'holiday'])
        ).order_by(CalendarEvent.date).first()

        if next_event:
            today = datetime.combine(next_event.date, datetime.min.time())
        else:
            today = datetime.today()

    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    # Executa verificação de conclusão automática
    check_auto_completion()

    # 2. Opções do Seletor
    weeks_options = []
    base_week = start_of_week - timedelta(weeks=5)
    for _ in range(12):
        w_end = base_week + timedelta(days=6)
        weeks_options.append({
            'value': base_week.strftime('%Y-%m-%d'),
            'label': f"{base_week.strftime('%d/%m/%Y')} a {w_end.strftime('%d/%m/%Y')}",
            'selected': base_week.date() == start_of_week.date()
        })
        base_week += timedelta(weeks=1)

    # 3. Geração de Eventos Futuros
    generation_end = end_of_week + timedelta(days=45) 
    generate_events_for_period(generation_end)
    
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
            
            # Ajusta o número da aula somando o offset (ex: se offset é 9, a 1ª aula gerada é a 10)
            real_lesson_index = previous_valid_count + event.turma.lesson_offset
            
            current_lesson = Lesson.query.filter_by(
                course_id=event.turma.course_id, 
                order=real_lesson_index
            ).first()
            
            next_lesson = Lesson.query.filter_by(
                course_id=event.turma.course_id, 
                order=real_lesson_index + 1
            ).first()
            
            # --- AQUI ESTÁ O SEGREDO: ENVIAR OS LINKS ---
            lesson_info[event.id] = {
                'current': current_lesson.title if current_lesson else f"Aula {real_lesson_index + 1}",
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

    total_val = sum(e.price for e in events if e.status not in ['cancelled', 'holiday'] and not e.is_extra and not e.is_replacement)
    
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
    if form_type == 'cancel' or form_type == 'replacement':
        base_url = "https://docs.google.com/forms/d/e/1FAIpQLSdha0_aJPJ4b_twUIp4RlicSZrZLmn2tjgWrPmh-mWpeIIEpQ/viewform"
        params = f"?entry.123456={data.get('turma')}&entry.987654={data.get('data')}"
    elif form_type == 'extra':
        base_url = "https://docs.google.com/forms/d/e/1FAIpQLSfppTLjIadUpPImdxqK4a53sEJoFLLvGfBbWCQjjYsVk62-Dw/viewform"
        params = f"?entry.111222={data.get('aluno')}&entry.333444={data.get('valor')}"
    return base_url + params
