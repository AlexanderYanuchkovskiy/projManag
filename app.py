# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, redirect, send_file, abort
import hashlib
from sql_active import DatabaseManager
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    db_manager = DatabaseManager()
    if not db_manager.database_exists():
        from sql_active import DatabaseManager as FullDBManager
        full_db = FullDBManager()
        full_db.create_database()
        print("База данных инициализирована")


def login_required(f):
    """Декоратор для проверки авторизации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Для доступа к этой странице необходимо войти в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    """Декоратор для проверки роли пользователя"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session:
                flash('Ошибка доступа', 'error')
                return redirect(url_for('login'))
            if session['role'] != required_role:
                flash(f'Доступ запрещен. Требуется роль: {required_role}', 'error')
                return redirect(url_for('curator_dashboard' if session['role'] == 'куратор' else 'cadet_dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Маршруты Flask
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        surname = request.form['last_name']
        username = request.form['first_name']
        patronymic = request.form['patronymic']
        user_email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return render_template('register.html')

        db_manager = DatabaseManager()

        # Хеширование пароля и создание пользователя (только куратор)
        password_hash = hash_password(password)
        try:
            db_manager.create_user(username, surname, patronymic, user_email, password_hash, 'куратор')
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Ошибка при регистрации: {str(e)}', 'error')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_email = request.form['email']
        password = request.form['password']
        user_type = request.form.get('user_type', 'курсант')  # По умолчанию курсант

        db_manager = DatabaseManager()
        user = db_manager.get_user_by_username(user_email)

        if user and user['password_hash'] == hash_password(password):
            # Проверка роли пользователя
            if user_type == 'курсант' and user['role'] != 'курсант':
                flash('Доступ разрешен только для курсантов', 'error')
                return render_template('login.html')
            elif user_type == 'куратор' and user['role'] != 'куратор':
                flash('Доступ разрешен только для кураторов', 'error')
                return render_template('login.html')

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['role'] = user['role']

            flash(f'Успешный вход! Добро пожаловать, {user["username"]}', 'success')

            # Перенаправляем в зависимости от роли
            if user['role'] == 'куратор':
                return redirect(url_for('curator_dashboard'))
            else:
                return redirect(url_for('cadet_dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/cadet_login')
def cadet_login():
    return render_template('login.html', default_user_type='курсант')


@app.route('/curator_dashboard')
def curator_dashboard():
    if 'user_id' not in session or session.get('role') != 'куратор':
        flash('Доступ запрещен', 'error')
        return redirect(url_for('login'))

    return render_template('curator_dashboard.html', username=session.get('username'))


@app.route('/cadet_dashboard')
def cadet_dashboard():
    if 'user_id' not in session or session.get('role') != 'курсант':
        flash('Доступ запрещен', 'error')
        return redirect(url_for('login'))

    return render_template('cadet_dashboard.html', username=session.get('username'))


@app.route('/cadet/task/<int:task_id>', methods=['GET', 'POST'])
@login_required
@role_required('курсант')
def cadet_task_detail(task_id):
    """Детальная страница задачи для курсанта с загрузкой файлов"""
    db = DatabaseManager()

    if request.method == 'POST':
        # Проверяем, есть ли файл в запросе
        if 'file' in request.files:
            file = request.files['file']

            # Проверяем, что файл выбран
            if file.filename == '':
                flash('Файл не выбран', 'error')
                return redirect(url_for('cadet_task_detail', task_id=task_id))

            # Проверяем, что файл имеет допустимое расширение
            allowed_extensions = {'pdf', 'doc', 'docx', 'txt', 'zip', 'rar', 'jpg', 'jpeg', 'png', 'gif'}
            if '.' in file.filename:
                file_ext = file.filename.rsplit('.', 1)[1].lower()
                if file_ext not in allowed_extensions:
                    flash('Недопустимый тип файла. Разрешенные: pdf, doc, docx, txt, zip, rar, jpg, png, gif', 'error')
                    return redirect(url_for('cadet_task_detail', task_id=task_id))

            # Проверяем размер файла (максимум 10MB)
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)

            if file_length > 10 * 1024 * 1024:  # 10 MB
                flash('Файл слишком большой. Максимальный размер: 10MB', 'error')
                return redirect(url_for('cadet_task_detail', task_id=task_id))

            try:
                # Добавляем файл в базу данных
                file_id = db.add_file_to_task(task_id, session['user_id'], file)

                # Обновляем статус задачи на "на проверке"
                db.update_cadet_task_status(task_id, session['user_id'], 3)
                flash('Файл загружен и задача отправлена на проверку куратору!', 'success')

            except Exception as e:
                flash(f'Ошибка при загрузке файла: {str(e)}', 'error')

        return redirect(url_for('cadet_task_detail', task_id=task_id))

    # GET запрос - показываем детали задачи
    try:
        # Автоматически устанавливаем статус "в работе" при первом открытии
        task = db.get_task_with_all_details(task_id, session['user_id'])

        if not task:
            flash('Задача не найдена или у вас нет к ней доступа', 'error')
            return redirect(url_for('cadet_tasks_table'))

        # Если задача в статусе "ожидает" (1), автоматически меняем на "в работе" (2)
        if task['status_code'] == 1:
            db.update_cadet_task_status(task_id, session['user_id'], 2)
            # Обновляем данные задачи
            task = db.get_task_with_all_details(task_id, session['user_id'])
            flash('Статус задачи автоматически изменен на "В работе"', 'info')

        # Получаем файлы задачи (только от текущего курсанта)
        files = db.get_task_files(task_id, session['user_id'])

        return render_template('cadet_task_detail.html',
                               task=task,
                               files=files)

    except Exception as e:
        flash(f'Ошибка при загрузке задачи: {str(e)}', 'error')
        return redirect(url_for('cadet_tasks_table'))


@app.route('/cadet/tasks')
@login_required
@role_required('курсант')
def cadet_tasks():
    """Карточный просмотр задач для курсанта"""
    db = DatabaseManager()

    try:
        tasks = db.get_cadet_tasks_with_details(session['user_id'])

        # Статистика
        total_tasks = len(tasks)
        tasks_by_status = {
            'ожидает': 0,
            'в работе': 0,
            'на проверке': 0,
            'завершена': 0
        }

        for task in tasks:
            status_name = task['status_name']
            if status_name in tasks_by_status:
                tasks_by_status[status_name] += 1

        return render_template('cadet_tasks.html',
                               tasks=tasks,
                               total_tasks=total_tasks,
                               tasks_by_status=tasks_by_status,
                               now=datetime.now())

    except Exception as e:
        flash(f'Ошибка при загрузке задач: {str(e)}', 'error')
        return redirect(url_for('cadet_dashboard'))

@app.route('/cadets_list', methods=['GET', 'POST'])
@login_required
@role_required('куратор')
def cadets_list():
    """Страница со списком всех курсантов с поиском и фильтрацией"""
    db = DatabaseManager()

    try:
        # Получаем параметры поиска из GET запроса
        search_query = request.args.get('search', '').strip()
        group_filter = request.args.get('group', '')

        # Получаем курсантов с учетом фильтров
        cadets = db.get_all_cadets(search_query, group_filter)

        # Получаем уникальные группы для фильтра
        all_cadets = db.get_all_cadets()  # все курсанты без фильтров
        unique_groups = set()
        for cadet in all_cadets:
            if cadet.get('academic_group'):
                unique_groups.add(cadet['academic_group'])

        # Статистика
        total_cadets = len(all_cadets)
        filtered_cadets = len(cadets)

        # Группировка по академическим группам
        groups = {}
        for cadet in all_cadets:
            group = cadet.get('academic_group', 'без группы')
            if group not in groups:
                groups[group] = 0
            groups[group] += 1

        return render_template('cadets_list.html',
                               cadets=cadets,
                               total_cadets=total_cadets,
                               filtered_cadets=filtered_cadets,
                               groups=groups,
                               unique_groups=sorted(unique_groups),
                               search_query=search_query,
                               group_filter=group_filter)

    except Exception as e:
        flash(f'Ошибка при загрузке списка курсантов: {str(e)}', 'error')
        return redirect(url_for('curator_dashboard'))


@app.route('/register_cadet', methods=['GET', 'POST'])
@login_required
@role_required('куратор')
def register_cadet():
    """Регистрация нового курсанта (только для кураторов)"""
    db = DatabaseManager()
    if request.method == 'POST':
        # Получаем данные из формы
        username = request.form.get('first_name')
        last_name = request.form.get('last_name')
        patronymic = request.form.get('patronymic', '')
        email = request.form.get('email')
        academic_group = request.form.get('academic_group', '')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Валидация данных
        errors = []

        # Проверка обязательных полей
        required_fields = {
            'username': 'Логин',
            'last_name': 'Фамилия',
            'patronymic': 'Отчетство',
            'email': 'Email',
            'academic_group': 'Академическая группа',
            'password': 'Пароль',
            'confirm_password': 'Подтверждение пароля'
        }

        for field, field_name in required_fields.items():
            if not locals().get(field):
                errors.append(f'Поле "{field_name}" обязательно для заполнения')

        if academic_group and len(academic_group) < 2:
            errors.append('Академическая группа должна содержать минимум 2 символа')

        # Проверка длины пароля
        if password and len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов')

        # Проверка совпадения паролей
        if password and confirm_password and password != confirm_password:
            errors.append('Пароли не совпадают')

        # Проверка email
        if email and '@' not in email:
            errors.append('Некорректный формат email')

        # Если есть ошибки, показываем их
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register_cadet.html')


        # Проверка уникальности email
        existing_email = db.get_user_by_username(email)
        if existing_email:
            flash('Пользователь с таким email уже существует', 'error')
            return render_template('register_cadet.html')

        try:
            # Хеширование пароля
            password_hash = hash_password(password)

            # Создание пользователя с ролью 'курсант'
            user_id = db.create_user(
                username=username,
                surname=last_name,
                patronymic=patronymic,
                email=email,
                academic_group=academic_group,
                password_hash=password_hash,
                role='курсант'
            )

            # Логирование успешной регистрации
            current_user = db.get_user_by_id(session['user_id'])
            print(f"Куратор {current_user['username']} зарегистрировал курсанта {username} (ID: {user_id})")

            flash(f'Курсант {username} {last_name} успешно зарегистрирован!', 'success')

            # Перенаправляем на страницу со списком курсантов
            return redirect(url_for('curator_dashboard'))

        except Exception as e:
            flash(f'Ошибка при регистрации: {str(e)}', 'error')
            return render_template('register_cadet.html')

    # GET запрос - показываем форму регистрации
    return render_template('register_cadet.html')

@app.route('/projects')
@login_required
def projects():
    db = DatabaseManager()
    """Страница управления проектами"""
    user_id = session.get('user_id')
    user_role = session.get('role')

    try:
        if user_role == 'куратор':
            # Кураторы видят все проекты
            projects_list = db.get_all_projects()
        else:
            # Курсанты видят только свои проекты
            projects_list = db.get_projects_by_cadet(user_id)

        print(projects_list)
        return render_template('projects.html',
                               projects=projects_list,
                               now=datetime.now())
    except Exception as e:
        flash(f'Ошибка при загрузке проектов: {str(e)}', 'error')
        return redirect(url_for('curator_dashboard' if user_role == 'куратор' else 'cadet_dashboard'))


@app.route('/tasks')
@login_required
def tasks():
    """Страница управления задачами"""
    db = DatabaseManager()
    user_id = session.get('user_id')
    user_role = session.get('role')

    try:
        if user_role == 'куратор':
            # Кураторы видят все задачи
            tasks_list = db.get_all_tasks()
        else:
            # Курсанты видят только свои задачи
            tasks_list = db.get_tasks_by_cadet(user_id)

        return render_template('tasks.html', tasks=tasks_list)
    except Exception as e:
        flash(f'Ошибка при загрузке задач: {str(e)}', 'error')
        return redirect(url_for('curator_dashboard' if user_role == 'куратор' else 'cadet_dashboard'))


@app.route('/projects/create', methods=['GET', 'POST'])
@login_required
@role_required('куратор')
def create_project():
    db = DatabaseManager()
    """Создание нового проекта"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        status = request.form.get('status', 'планирование')
        deadline = request.form.get('deadline')

        if not title:
            flash('Название проекта обязательно', 'error')
            return render_template('create_project.html')

        try:
            project_id = db.create_project(
                title=title,
                description=description,
                curator_id=session['user_id'],
                status=status,
                deadline=deadline
            )

            # Если выбраны курсанты, создаем для них задачи
            cadet_ids = request.form.getlist('cadet_id')
            if cadet_ids:
                for cadet_id in cadet_ids:
                    db.create_task(
                        project_id=project_id,
                        cadet_id=cadet_id,
                        title=f"Задача по проекту '{title[:30]}...'",
                        description=f"Начальная задача по проекту '{title}'",
                        status_code=1
                    )

            flash(f'Проект "{title}" успешно создан!', 'success')
            return redirect(url_for('projects'))

        except Exception as e:
            flash(f'Ошибка при создании проекта: {str(e)}', 'error')

    # GET запрос - показываем форму
    try:
        cadets = db.get_users_by_role('курсант')
        return render_template('create_project.html', cadets=cadets)
    except Exception as e:
        flash(f'Ошибка при загрузке данных: {str(e)}', 'error')
        return redirect(url_for('projects'))


@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
@role_required('куратор')
def create_task():
    """Создание новой задачи"""
    db = DatabaseManager()
    if request.method == 'POST':
        # Получаем данные из формы
        title = request.form.get('title')
        description = request.form.get('description')
        project_id = request.form.get('project_id')
        cadet_id = request.form.get('cadet_id')
        status_code = request.form.get('status_code', '1')
        start_date = request.form.get('start_date')
        due_date = request.form.get('due_date')

        # Валидация данных
        errors = []
        if not title:
            errors.append('Название задачи обязательно')
        if not project_id:
            errors.append('Необходимо выбрать проект')
        if not cadet_id:
            errors.append('Необходимо выбрать курсанта')

        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('create_task'))

        try:
            # Создаем задачу
            task_id = db.create_task(
                project_id=int(project_id),
                cadet_id=int(cadet_id),
                title=title,
                description=description,
                status_code=int(status_code),
                start_date=start_date,
                due_date=due_date
            )

            # Получаем информацию о курсанте и проекте для сообщения
            cadet = db.get_user_by_id(int(cadet_id))
            project = db.get_project_by_id(int(project_id))

            if cadet and project:
                flash(
                    f'Задача "{title[:30]}" успешно создана и назначена курсанту '
                    f'{cadet["surname"]} {cadet["username"]} по проекту "{project["title"]}"',
                    'success'
                )
            else:
                flash(f'Задача "{title[:30]}" успешно создана!', 'success')

            return redirect(url_for('tasks'))

        except Exception as e:
            flash(f'Ошибка при создании задачи: {str(e)}', 'error')
            return redirect(url_for('create_task'))

    # GET запрос - показываем форму
    try:
        # Получаем список активных проектов
        projects = db.get_all_active_projects()

        # Получаем список курсантов
        cadets = db.get_users_by_role('курсант')

        return render_template('create_task.html',
                               projects=projects,
                               cadets=cadets)
    except Exception as e:
        flash(f'Ошибка при загрузке данных: {str(e)}', 'error')
        return redirect(url_for('tasks'))


@app.route('/task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def view_task(task_id):
    """Просмотр и управление задачей"""
    db = DatabaseManager()

    if request.method == 'POST':
        # Проверяем, что пользователь - куратор
        if session['role'] != 'куратор':
            flash('Только кураторы могут изменять статус задач', 'error')
            return redirect(url_for('view_task', task_id=task_id))

        action = request.form.get('action')

        if action == 'approve':
            # Устанавливаем статус "завершена" (4)
            success = db.update_task_status_by_curator(task_id, session['user_id'], 4)
            if success:
                flash('Задача одобрена и помечена как завершенная!', 'success')
            else:
                flash('Не удалось обновить статус задачи', 'error')

        elif action == 'reject':
            # Устанавливаем статус "в работе" (2)
            success = db.update_task_status_by_curator(task_id, session['user_id'], 2)
            if success:
                flash('Задача отклонена и возвращена в работу!', 'warning')
            else:
                flash('Не удалось обновить статус задачи', 'error')

        return redirect(url_for('view_task', task_id=task_id))

    # GET запрос - показываем страницу
    try:
        user_id = session['user_id']
        user_role = session['role']

        # Получаем задачу с учетом прав доступа
        task = db.get_task_with_permissions(task_id, user_id, user_role)

        if not task:
            flash('Задача не найдена или у вас нет доступа', 'error')
            return redirect(url_for('tasks'))

        # Получаем все файлы задачи с информацией об авторе
        files = []
        if hasattr(db, 'get_files_by_task_with_authors'):
            files = db.get_files_by_task_with_authors(task_id)
        else:
            # Fallback если метод не существует
            files = db.get_files_by_task(task_id)

        # Дополнительная информация для куратора
        additional_info = {}
        if user_role == 'куратор':
            # Получаем статистику курсанта
            with db.create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_tasks,
                        SUM(CASE WHEN status_code = 4 THEN 1 ELSE 0 END) as completed_tasks,
                        SUM(CASE WHEN status_code = 3 THEN 1 ELSE 0 END) as in_review_tasks
                    FROM tasks 
                    WHERE cadet_id = ? AND project_id = ?
                """, (task['cadet_id'], task['project_id']))
                progress = cursor.fetchone()
                if progress:
                    additional_info['cadet_total_tasks'] = progress[0]
                    additional_info['cadet_completed_tasks'] = progress[1]
                    additional_info['cadet_in_review_tasks'] = progress[2]

        return render_template('view_task.html',
                               task=task,
                               user_role=user_role,
                               files=files,
                               **additional_info)

    except Exception as e:
        flash(f'Ошибка при загрузке задачи: {str(e)}', 'error')
        return redirect(url_for('tasks'))

@app.route('/tast/<int:task_id>/edit')
@login_required
def edit_task(task_id):
    return None

@app.route('/project/<int:project_id>')
@login_required
def view_project(project_id):
    """Простой просмотр проекта"""
    db = DatabaseManager()
    try:
        project = db.get_project_by_id(project_id)
        if not project:
            flash('Проект не найден', 'error')
            return redirect(url_for('projects'))

        # Просто отображаем информацию о проекте
        return render_template('simple_view_project.html', project=project)

    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('projects'))


@app.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('куратор')
def edit_project(project_id):
    """Редактирование существующего проекта"""
    db = DatabaseManager()

    # Получаем проект для проверки прав
    project = db.get_project_by_id(project_id)
    if not project:
        flash('Проект не найден', 'error')
        return redirect(url_for('projects'))

    # Проверяем, что текущий пользователь - куратор этого проекта
    if project['curator_id'] != session['user_id']:
        flash('У вас нет прав для редактирования этого проекта', 'error')
        return redirect(url_for('projects'))

    if request.method == 'POST':
        # Получаем данные из формы
        title = request.form.get('title')
        description = request.form.get('description')
        status = request.form.get('status')
        deadline = request.form.get('deadline')

        # Валидация данных
        errors = []
        if not title:
            errors.append('Название проекта обязательно')
        if not status:
            errors.append('Статус проекта обязателен')

        if errors:
            for error in errors:
                flash(error, 'error')
            # Возвращаем на страницу редактирования с текущими данными
            cadets = db.get_users_by_role('курсант')
            return render_template('edit_project.html',
                                   project=project,
                                   cadets=cadets)

        try:
            # Обновляем проект в базе данных
            with db.create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE projects 
                    SET title = ?, description = ?, status = ?, deadline = ?
                    WHERE id = ?
                ''', (title, description, status, deadline, project_id))
                conn.commit()

            # Обновляем задачи, если были выбраны курсанты
            cadet_ids = request.form.getlist('cadet_id')

            # Если выбраны курсанты, проверяем существующие задачи
            with db.create_connection() as conn:
                cursor = conn.cursor()

                # Получаем текущих курсантов проекта
                cursor.execute('''
                    SELECT DISTINCT cadet_id FROM tasks WHERE project_id = ?
                ''', (project_id,))
                current_cadet_ids = {row[0] for row in cursor.fetchall()}

                # Добавляем новые задачи для курсантов, которых еще нет
                for cadet_id in cadet_ids:
                    if int(cadet_id) not in current_cadet_ids:
                        cursor.execute('''
                            INSERT INTO tasks (project_id, cadet_id, title, description, status_code)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (project_id, cadet_id,
                              f"Задача по проекту '{title[:30]}...'",
                              f"Начальная задача по проекту '{title}'",
                              1))

                # Удаляем задачи курсантов, которых убрали из проекта
                # (опционально, закомментируйте если не нужно)
                # for cadet_id in current_cadet_ids:
                #     if cadet_id not in [int(cid) for cid in cadet_ids]:
                #         cursor.execute('''
                #             DELETE FROM tasks
                #             WHERE project_id = ? AND cadet_id = ?
                #         ''', (project_id, cadet_id))

                conn.commit()

            flash(f'Проект "{title}" успешно обновлен!', 'success')
            return redirect(url_for('view_project', project_id=project_id))

        except Exception as e:
            flash(f'Ошибка при обновлении проекта: {str(e)}', 'error')
            cadets = db.get_users_by_role('курсант')
            return render_template('edit_project.html',
                                   project=project,
                                   cadets=cadets)

    # GET запрос - показываем форму редактирования
    try:
        # Получаем список курсантов
        cadets = db.get_users_by_role('курсант')

        # Получаем текущих курсантов проекта для предварительного выбора
        with db.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT cadet_id FROM tasks WHERE project_id = ?
            ''', (project_id,))
            current_cadet_ids = [str(row[0]) for row in cursor.fetchall()]

        return render_template('edit_project.html',
                               project=project,
                               cadets=cadets,
                               current_cadet_ids=current_cadet_ids)
    except Exception as e:
        flash(f'Ошибка при загрузке данных: {str(e)}', 'error')
        return redirect(url_for('projects'))


@app.route('/project/<int:project_id>/delete')
@login_required
@role_required('куратор')
def delete_project(project_id):
    """Простое удаление проекта с подтверждением через JavaScript"""
    db = DatabaseManager()

    # Получаем проект для проверки прав и информации
    project = db.get_project_by_id(project_id)
    if not project:
        flash('Проект не найден', 'error')
        return redirect(url_for('projects'))

    # Проверяем, что текущий пользователь - куратор этого проекта
    if project['curator_id'] != session['user_id']:
        flash('У вас нет прав для удаления этого проекта', 'error')
        return redirect(url_for('projects'))

    try:
        # Удаляем проект (все связанные задачи и файлы удалятся каскадно)
        with db.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()

        flash(f'Проект "{project["title"]}" успешно удален!', 'success')

        # Логирование удаления
        current_user = db.get_user_by_id(session['user_id'])
        print(f"Куратор {current_user['username']} удалил проект '{project['title']}' (ID: {project_id})")

    except Exception as e:
        flash(f'Ошибка при удалении проекта: {str(e)}', 'error')

    return redirect(url_for('projects'))


@app.route('/cadet/tasks/table')
@login_required
@role_required('курсант')
def cadet_tasks_table():
    """Табличный просмотр задач для курсанта"""
    db = DatabaseManager()

    try:
        tasks = db.get_cadet_tasks_with_details(session['user_id'])

        return render_template('cadet_tasks_table.html',
                               tasks=tasks,
                               now=datetime.now())

    except Exception as e:
        flash(f'Ошибка при загрузке задач: {str(e)}', 'error')
        return redirect(url_for('cadet_dashboard'))


@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    """Скачивание файла с безопасным именем"""
    db = DatabaseManager()

    try:
        # Получаем информацию о файле из базы данных
        file_info = db.get_file_with_details(file_id)

        if not file_info:
            flash('Файл не найден', 'error')
            return redirect(request.referrer or url_for('index'))

        # Проверяем права доступа
        user_id = session['user_id']
        user_role = session['role']

        # Проверка прав доступа
        if user_role == 'курсант' and file_info['author_id'] != user_id:
            flash('У вас нет доступа к этому файлу', 'error')
            return redirect(request.referrer or url_for('index'))
        elif user_role == 'куратор' and file_info['curator_id'] != user_id:
            flash('У вас нет доступа к этому файлу', 'error')
            return redirect(request.referrer or url_for('index'))

        # Проверяем существование файла
        file_path = file_info['file_path']
        if not os.path.exists(file_path):
            flash('Файл не найден на сервере', 'error')
            return redirect(request.referrer or url_for('index'))

        # Создаем безопасное имя для скачивания
        original_name = file_info['filename']
        task_title = file_info['task_title']
        author_name = file_info['author_name']

        # Очищаем имя файла от небезопасных символов
        safe_task_title = ''.join(c for c in task_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_author_name = ''.join(c for c in author_name if c.isalnum() or c in (' ', '-', '_')).rstrip()

        # Формируем имя файла для скачивания
        download_name = f"task_{file_info['task_id']}_{safe_task_title}_{safe_author_name}_{original_name}"

        # Заменяем пробелы на подчеркивания
        download_name = download_name.replace(' ', '_')

        # Логирование
        print(f"Скачивание файла: {original_name} -> {download_name}")

        # Отправляем файл
        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=file_info.get('mime_type', 'application/octet-stream')
        )

    except Exception as e:
        flash(f'Ошибка при скачивании файла: {str(e)}', 'error')
        return redirect(request.referrer or url_for('index'))



@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
