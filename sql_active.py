import sqlite3
import os
from typing import List, Optional
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path: str = "schem.db"):
        self.db_path = db_path
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

    def create_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Создание таблицы пользователей (с академической группой из файла)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username VARCHAR(50) NOT NULL,
                        surname VARCHAR(50) NOT NULL,
                        patronymic VARCHAR(50),
                        email VARCHAR(100) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(10) CHECK(role IN ('куратор', 'курсант')) NOT NULL,
                        registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                        academic_group VARCHAR(50)
                    )
                ''')

                # Создание таблицы проектов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        curator_id INTEGER NOT NULL,
                        status VARCHAR(20) CHECK(status IN ('планирование', 'активен', 'завершён')) NOT NULL,
                        deadline DATE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (curator_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                ''')

                # Создание таблицы задач
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        cadet_id INTEGER NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        status_code INTEGER CHECK(status_code IN (1, 2, 3, 4)) NOT NULL DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                        FOREIGN KEY (cadet_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                ''')

                # Создание таблицы файлов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename VARCHAR(255) NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        task_id INTEGER NOT NULL,
                        author_id INTEGER NOT NULL,
                        upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                        file_size INTEGER,
                        mime_type VARCHAR(100),
                        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                        FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                ''')

                # Создание таблицы для справочника статусов задач
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS task_status_codes (
                        status_code INTEGER PRIMARY KEY,
                        status_name VARCHAR(20) NOT NULL,
                        description TEXT
                    )
                ''')

                # Создание индексов для улучшения производительности
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_curator ON projects(curator_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_cadet ON tasks(cadet_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status_code)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_task ON files(task_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_author ON files(author_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')

                # Заполнение справочника статусов задач
                cursor.execute('''
                    INSERT OR IGNORE INTO task_status_codes (status_code, status_name, description) VALUES
                    (1, 'ожидает', 'Задача ожидает начала работы'),
                    (2, 'в работе', 'Задача находится в работе'),
                    (3, 'на проверке', 'Задача отправлена на проверку'),
                    (4, 'завершена', 'Задача завершена')
                ''')

                # Триггер для автоматического обновления updated_at в задачах
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_tasks_timestamp 
                    AFTER UPDATE ON tasks
                    FOR EACH ROW
                    BEGIN
                        UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END
                ''')

                # Дополнительные триггеры для целостности данных
                
                # Триггер для проверки, что куратор имеет правильную роль
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS check_curator_role 
                    BEFORE INSERT ON projects
                    FOR EACH ROW
                    BEGIN
                        SELECT CASE
                            WHEN (SELECT role FROM users WHERE id = NEW.curator_id) != 'куратор'
                            THEN RAISE(ABORT, 'Только пользователь с ролью "куратор" может быть назначен куратором проекта')
                        END;
                    END
                ''')

                # Триггер для проверки, что курсант имеет правильную роль
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS check_cadet_role 
                    BEFORE INSERT ON tasks
                    FOR EACH ROW
                    BEGIN
                        SELECT CASE
                            WHEN (SELECT role FROM users WHERE id = NEW.cadet_id) != 'курсант'
                            THEN RAISE(ABORT, 'Только пользователь с ролью "курсант" может быть назначен исполнителем задачи')
                        END;
                    END
                ''')

                # Триггер для проверки дедлайна проекта
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS check_project_deadline 
                    BEFORE INSERT ON projects
                    FOR EACH ROW
                    BEGIN
                        SELECT CASE
                            WHEN NEW.deadline IS NOT NULL AND DATE(NEW.deadline) < DATE('now')
                            THEN RAISE(ABORT, 'Дедлайн проекта не может быть в прошлом')
                        END;
                    END
                ''')

                # Триггер для автоматической смены статуса проекта при завершении всех задач
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_project_status_on_task_completion 
                    AFTER UPDATE OF status_code ON tasks
                    FOR EACH ROW
                    WHEN NEW.status_code = 4
                    BEGIN
                        UPDATE projects 
                        SET status = 'завершён'
                        WHERE id = NEW.project_id 
                        AND NOT EXISTS (
                            SELECT 1 FROM tasks 
                            WHERE project_id = NEW.project_id 
                            AND status_code != 4
                        );
                    END
                ''')

                conn.commit()
                print(f"База данных успешно создана: {self.db_path}")
                print("Созданы следующие объекты:")
                print("- Таблицы: users, projects, tasks, files, task_status_codes")
                print("- Индексы: idx_projects_curator, idx_projects_status, idx_tasks_project, idx_tasks_cadet, idx_tasks_status, idx_files_task, idx_files_author, idx_users_email, idx_users_role")
                print("- Триггеры: update_tasks_timestamp, check_curator_role, check_cadet_role, check_project_deadline, update_project_status_on_task_completion")
                print("- Справочник статусов: заполнен значениями 1-4")
                return True

        except sqlite3.Error as e:
            print(f"Ошибка при создании базы данных: {e}")
            return False

    def database_exists(self) -> bool:
        return os.path.exists(self.db_path)

    def get_database_info(self) -> dict:
        if not self.database_exists():
            return {"error": "База данных не существует"}

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Получаем список таблиц
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]

                # Получаем количество записей в каждой таблице
                table_counts = {}
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    table_counts[table] = cursor.fetchone()[0]

                # Получаем размер файла БД
                db_size = os.path.getsize(self.db_path)

                return {
                    "tables": tables,
                    "table_counts": table_counts,
                    "database_size_bytes": db_size,
                    "database_size_mb": round(db_size / (1024 * 1024), 2)
                }

        except sqlite3.Error as e:
            return {"error": f"Ошибка при получении информации: {e}"}

    def reset_database(self):
        """Полная пересоздание базы данных (очистка всех данных)"""
        try:
            if self.database_exists():
                os.remove(self.db_path)
                print("Старая база данных удалена.")

            return self.create_database()

        except Exception as e:
            print(f"Ошибка при сбросе базы данных: {e}")
            return False

    def create_connection(self):
        """Создание соединения с базой данных"""
        return sqlite3.connect(self.db_path)

    # Методы для работы с пользователями
    def create_user(self, username: str, surname: str,
                    patronymic: str, email: str, password_hash: str,
                    role: str, academic_group: str = None) -> int:
        """Создание нового пользователя с академической группой"""
        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users 
                (username, surname, patronymic, email, academic_group, password_hash, role) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (username, surname, patronymic, email, academic_group, password_hash, role))
            conn.commit()
            return cursor.lastrowid

    def get_user_by_username(self, email: str) -> Optional[dict]:
        """Получение пользователя по имени"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_users_by_role(self, role: str):
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, surname FROM users WHERE role=?', (role,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_cadets(self, search_query=None, group_filter=None):
        """Получение всех курсантов с возможностью поиска и фильтрации"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = '''
                SELECT id, username, surname, patronymic, email, 
                       registration_date, academic_group
                FROM users 
                WHERE role = 'курсант'
            '''

            params = []

            # Добавляем поиск по ФИО или email
            if search_query:
                query += '''
                    AND (surname LIKE ? OR username LIKE ? 
                    OR patronymic LIKE ? OR email LIKE ? 
                    OR (surname || ' ' || username || ' ' || COALESCE(patronymic, '')) LIKE ?)
                '''
                search_pattern = f'%{search_query}%'
                params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])

            # Добавляем фильтрацию по группе
            if group_filter:
                if group_filter == 'без группы':
                    query += ' AND (academic_group IS NULL OR academic_group = "")'
                else:
                    query += ' AND academic_group = ?'
                    params.append(group_filter)

            query += ' ORDER BY surname, username'

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # Методы для работы с проектами
    def create_project(self, title: str, description: str, curator_id: int,
                       status: str, deadline: str) -> int:
        """Создание нового проекта"""
        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO projects (title, description, curator_id, status, deadline) 
                VALUES (?, ?, ?, ?, ?)""",
                (title, description, curator_id, status, deadline)
            )
            conn.commit()
            return cursor.lastrowid

    def get_projects_by_cadet(self, cadet_id: int):
        """Получение проектов курсанта"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.*, u.surname as curator_surname, u.username as curator_name, u.patronymic as curator_patr, u.role as role,
                       (SELECT COUNT(*) FROM tasks t2 WHERE t2.project_id = p.id AND t2.cadet_id = ?) as task_count
                FROM projects p 
                JOIN tasks t ON p.id = t.project_id 
                JOIN users u ON p.curator_id = u.id
                WHERE t.cadet_id = ?
                ORDER BY p.created_at DESC
            """, (cadet_id, cadet_id))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_active_projects(self):
        """Получение активных проектов (не завершенных)"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, u.username as curator_name
                FROM projects p 
                JOIN users u ON p.curator_id = u.id
                WHERE p.status != 'завершён'
                ORDER BY p.title
            """)
            return [dict(row) for row in cursor.fetchall()]

    def create_task(self, project_id: int, cadet_id: int, title: str,
                    description: str = None, status_code: int = 1, start_date: str = None,
                    due_date: str = None) -> int:
        """Создание новой задачи с расширенными полями"""
        with self.create_connection() as conn:
            cursor = conn.cursor()

            # Если их еще нет, нужно добавить через ALTER TABLE
            cursor.execute("""
                INSERT INTO tasks 
                (project_id, cadet_id, title, description, status_code, start_date, due_date) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project_id, cadet_id, title, description, status_code,
                  start_date, due_date))

            conn.commit()
            return cursor.lastrowid

    def get_user_by_id(self, user_id: int):
        """Получение пользователя по ID"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, surname, patronymic, 
                       email, password_hash, role, registration_date
                FROM users 
                WHERE id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_project_by_id(self, project_id: int):
        """Получение проекта по ID"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, u.surname as curator_surname, u.email as curator_email, u.username as curator_name, u.patronymic as curator_patr,
                       (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as task_count,
                       (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND status_code = 4) as completed_tasks
                FROM projects p 
                LEFT JOIN users u ON p.curator_id = u.id
                WHERE p.id = ?
            """, (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_task_by_id(self, task_id: int):
        """Получение задачи по ID"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.username as cadet_name, u.surname, u.username,
                       p.title as project_title, p.curator_id
                FROM tasks t 
                JOIN users u ON t.cadet_id = u.id 
                JOIN projects p ON t.project_id = p.id 
                WHERE t.id = ?
            """, (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # Методы для работы с базой данных
    def get_all_projects(self):
        """Получение всех проектов с информацией о кураторе"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, u.surname as curator_surname, u.username as curator_name, u.patronymic as curator_patr,
                       (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as task_count
                FROM projects p 
                JOIN users u ON p.curator_id = u.id
                ORDER BY p.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_tasks_by_cadet(self, cadet_id: int):
        """Получение задач курсанта"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.username as cadet_name, p.title as project_title
                FROM tasks t 
                JOIN users u ON t.cadet_id = u.id 
                JOIN projects p ON t.project_id = p.id 
                WHERE t.cadet_id = ?
                ORDER BY t.status_code, t.created_at DESC
            """, (cadet_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_tasks(self):
        """Получение всех задач"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, u.username as cadet_name, p.title as project_title
                FROM tasks t 
                JOIN users u ON t.cadet_id = u.id 
                JOIN projects p ON t.project_id = p.id 
                ORDER BY t.status_code, t.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    # Методы для работы с задачами
    def create_task(self, project_id: int, cadet_id: int, title: str,
                    description: str = None, status_code: int = 1) -> int:
        """Создание новой задачи"""
        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO tasks (project_id, cadet_id, title, description, status_code) 
                VALUES (?, ?, ?, ?, ?)""",
                (project_id, cadet_id, title, description, status_code)
            )
            conn.commit()
            return cursor.lastrowid

    def update_task_status(self, task_id: int, status_code: int) -> bool:
        """Обновление статуса задачи"""
        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status_code = ? WHERE id = ?",
                (status_code, task_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_task_status_name(self, status_code: int) -> str:
        """Получение названия статуса по коду"""
        status_names = {
            1: 'ожидает',
            2: 'в работе',
            3: 'на проверке',
            4: 'завершена'
        }
        return status_names.get(status_code, 'неизвестно')

    # Методы для работы с файлами
    def add_file(self, filename: str, file_path: str, task_id: int,
                 author_id: int, file_size: int = None, mime_type: str = None) -> int:
        """Добавление файла"""
        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO files (filename, file_path, task_id, author_id, file_size, mime_type) 
                VALUES (?, ?, ?, ?, ?, ?)""",
                (filename, file_path, task_id, author_id, file_size, mime_type)
            )
            conn.commit()
            return cursor.lastrowid

    def get_files_by_task(self, task_id: int) -> List[dict]:
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE task_id = ?", (task_id,))
            return [dict(row) for row in cursor.fetchall()]


    # Обновите метод add_file для работы с новой структурой
    def add_file_to_task(self, task_id: int, author_id: int, file_obj, filename: str = None):
        """Добавление файла к задаче"""
        if filename is None:
            filename = file_obj.filename

        # Генерируем уникальное имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"task_{task_id}_{author_id}_{timestamp}_{filename.replace(' ', '_')}"
        file_path = os.path.join(self.data_dir, safe_filename)

        # Сохраняем файл
        file_obj.save(file_path)

        # Получаем размер и MIME тип
        file_size = os.path.getsize(file_path)
        mime_type = file_obj.mimetype if hasattr(file_obj, 'mimetype') else 'application/octet-stream'

        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO files (filename, file_path, task_id, author_id, file_size, mime_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (filename, file_path, task_id, author_id, file_size, mime_type))
            conn.commit()
            return cursor.lastrowid

    # В класс DatabaseManager добавьте эти методы:

    def get_cadet_tasks_with_details(self, cadet_id: int):
        """Получение задач курсанта с детальной информацией о проекте"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, 
                       p.title as project_title, 
                       p.description as project_description,
                       p.status as project_status,
                       p.deadline as project_deadline,
                       u_cadet.username as cadet_name,
                       u_cadet.surname as cadet_surname,
                       u_curator.username as curator_name,
                       ts.status_name,
                       ts.description as status_description
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                JOIN users u_cadet ON t.cadet_id = u_cadet.id
                JOIN users u_curator ON p.curator_id = u_curator.id
                JOIN task_status_codes ts ON t.status_code = ts.status_code
                WHERE t.cadet_id = ?
                ORDER BY 
                    CASE 
                        WHEN t.status_code = 2 THEN 1  -- в работе - приоритет
                        WHEN t.status_code = 3 THEN 2  -- на проверке
                        WHEN t.status_code = 1 THEN 3  -- ожидает
                        WHEN t.status_code = 4 THEN 4  -- завершена
                    END,
                    t.created_at DESC
            """, (cadet_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_cadet_task_status(self, task_id: int, cadet_id: int, status_code: int) -> bool:
        """Обновление статуса задачи курсантом (с проверкой прав)"""
        with self.create_connection() as conn:
            cursor = conn.cursor()
            # Проверяем, что задача принадлежит курсанту
            cursor.execute("SELECT id FROM tasks WHERE id = ? AND cadet_id = ?", (task_id, cadet_id))
            if not cursor.fetchone():
                return False

            # Обновляем статус
            cursor.execute("""
                UPDATE tasks 
                SET status_code = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND cadet_id = ?
            """, (status_code, task_id, cadet_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_task_by_id_with_details(self, task_id: int, cadet_id: int = None):
        """Получение задачи по ID с проверкой прав курсанта"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT t.*, 
                       p.title as project_title, 
                       p.description as project_description,
                       p.status as project_status,
                       p.curator_id,
                       u_cadet.username as cadet_name,
                       u_cadet.surname as cadet_surname,
                       u_curator.username as curator_name,
                       ts.status_name,
                       ts.description as status_description
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                JOIN users u_cadet ON t.cadet_id = u_cadet.id
                JOIN users u_curator ON p.curator_id = u_curator.id
                JOIN task_status_codes ts ON t.status_code = ts.status_code
                WHERE t.id = ?
            """

            params = [task_id]

            if cadet_id:
                query += " AND t.cadet_id = ?"
                params.append(cadet_id)

            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_task_with_all_details(self, task_id: int, cadet_id: int = None):
        """Получение задачи со всей информацией"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT t.*, 
                       p.title as project_title, 
                       p.description as project_description,
                       p.status as project_status,
                       p.curator_id,
                       p.deadline as project_deadline,
                       u_cadet.username as cadet_name,
                       u_cadet.surname as cadet_surname,
                       u_cadet.email as cadet_email,
                       u_curator.username as curator_name,
                       u_curator.surname as curator_surname,
                       u_curator.email as curator_email,
                       ts.status_name,
                       ts.description as status_description
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                JOIN users u_cadet ON t.cadet_id = u_cadet.id
                JOIN users u_curator ON p.curator_id = u_curator.id
                JOIN task_status_codes ts ON t.status_code = ts.status_code
                WHERE t.id = ?
            """

            params = [task_id]

            if cadet_id:
                query += " AND t.cadet_id = ?"
                params.append(cadet_id)

            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_task_files(self, task_id: int, author_id: int = None):
        """Получение файлов задачи с возможностью фильтрации по автору"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT f.*, 
                       u.username as author_name,
                       u.surname as author_surname
                FROM files f
                JOIN users u ON f.author_id = u.id
                WHERE f.task_id = ?
            """

            params = [task_id]

            if author_id:
                query += " AND f.author_id = ?"
                params.append(author_id)

            query += " ORDER BY f.upload_time DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def add_file_to_task(self, task_id: int, author_id: int, file_obj, filename: str = None):
        """Добавление файла к задаче"""
        if filename is None:
            filename = file_obj.filename

        # Генерируем уникальное имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"task_{task_id}_{author_id}_{timestamp}_{filename.replace(' ', '_')}"
        file_path = os.path.join(self.data_dir, safe_filename)

        # Сохраняем файл
        file_obj.save(file_path)

        # Получаем размер и MIME тип
        file_size = os.path.getsize(file_path)
        mime_type = file_obj.mimetype if hasattr(file_obj, 'mimetype') else 'application/octet-stream'

        with self.create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO files (filename, file_path, task_id, author_id, file_size, mime_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (filename, file_path, task_id, author_id, file_size, mime_type))
            conn.commit()
            return cursor.lastrowid

    def get_file_with_details(self, file_id: int):
        """Получение информации о файле со всеми деталями"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    f.*,
                    u.username as author_name,
                    u.surname as author_surname,
                    u.role as author_role,
                    t.id as task_id,
                    t.title as task_title,
                    t.cadet_id,
                    p.id as project_id,
                    p.title as project_title,
                    p.curator_id
                FROM files f
                JOIN users u ON f.author_id = u.id
                JOIN tasks t ON f.task_id = t.id
                JOIN projects p ON t.project_id = p.id
                WHERE f.id = ?
            """, (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def user_can_access_task(self, task_id: int, user_id: int, user_role: str) -> bool:
        """Проверка, имеет ли пользователь доступ к задаче"""
        with self.create_connection() as conn:
            cursor = conn.cursor()

            if user_role == 'курсант':
                # Курсант может получить доступ только к своим задачам
                cursor.execute("""
                    SELECT 1 FROM tasks 
                    WHERE id = ? AND cadet_id = ?
                """, (task_id, user_id))
            elif user_role == 'куратор':
                # Куратор может получить доступ к задачам в своих проектах
                cursor.execute("""
                    SELECT 1 FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    WHERE t.id = ? AND p.curator_id = ?
                """, (task_id, user_id))
            else:
                return False

            return cursor.fetchone() is not None

    def get_task_with_access_check(self, task_id: int, user_id: int, user_role: str):
        """Получение задачи с проверкой прав доступа"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if user_role == 'курсант':
                # Курсант получает только свои задачи
                cursor.execute("""
                    SELECT t.*, 
                           u.username as cadet_name, 
                           u.surname as cadet_surname,
                           p.title as project_title,
                           ts.status_name
                    FROM tasks t
                    JOIN users u ON t.cadet_id = u.id
                    JOIN projects p ON t.project_id = p.id
                    JOIN task_status_codes ts ON t.status_code = ts.status_code
                    WHERE t.id = ? AND t.cadet_id = ?
                """, (task_id, user_id))
            elif user_role == 'куратор':
                # Куратор получает задачи из своих проектов
                cursor.execute("""
                    SELECT t.*, 
                           u.username as cadet_name, 
                           u.surname as cadet_surname,
                           p.title as project_title,
                           ts.status_name,
                           p.curator_id
                    FROM tasks t
                    JOIN users u ON t.cadet_id = u.id
                    JOIN projects p ON t.project_id = p.id
                    JOIN task_status_codes ts ON t.status_code = ts.status_code
                    WHERE t.id = ? AND p.curator_id = ?
                """, (task_id, user_id))
            else:
                return None

            row = cursor.fetchone()
            return dict(row) if row else None

    def get_task_for_view(self, task_id: int):
        """Получение задачи с полной информацией для просмотра"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, 
                       u.username as cadet_name, 
                       u.surname as cadet_surname,
                       u.email as cadet_email,
                       p.title as project_title,
                       p.description as project_description,
                       p.curator_id,
                       p.status as project_status,
                       p.deadline as project_deadline,
                       ts.status_name,
                       ts.description as status_description,
                       cu.username as curator_name,
                       cu.surname as curator_surname
                FROM tasks t
                JOIN users u ON t.cadet_id = u.id
                JOIN projects p ON t.project_id = p.id
                JOIN task_status_codes ts ON t.status_code = ts.status_code
                JOIN users cu ON p.curator_id = cu.id
                WHERE t.id = ?
            """, (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_task_status_by_curator(self, task_id: int, curator_id: int, status_code: int) -> bool:
        """Обновление статуса задачи куратором (с проверкой прав)"""
        with self.create_connection() as conn:
            cursor = conn.cursor()

            # Проверяем, что куратор имеет доступ к задаче
            cursor.execute("""
                SELECT 1 FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE t.id = ? AND p.curator_id = ?
            """, (task_id, curator_id))

            if not cursor.fetchone():
                return False

            # Обновляем статус задачи
            cursor.execute("""
                UPDATE tasks 
                SET status_code = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status_code, task_id))

            conn.commit()
            return cursor.rowcount > 0

    def get_tasks_by_cadet_in_project(self, cadet_id: int, project_id: int):
        """Получение задач курсанта в конкретном проекте"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, ts.status_name
                FROM tasks t
                JOIN task_status_codes ts ON t.status_code = ts.status_code
                WHERE t.cadet_id = ? AND t.project_id = ?
                ORDER BY t.created_at DESC
            """, (cadet_id, project_id))
            return [dict(row) for row in cursor.fetchall()]

    def get_files_by_task_with_authors(self, task_id: int):
        """Получение файлов задачи с информацией об авторах"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*, 
                       u.username as author_name,
                       u.surname as author_surname,
                       u.email as author_email
                FROM files f
                JOIN users u ON f.author_id = u.id
                WHERE f.task_id = ?
                ORDER BY f.upload_time DESC
            """, (task_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_task_with_permissions(self, task_id: int, user_id: int, user_role: str):
        """Получение задачи с учетом прав доступа"""
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if user_role == 'курсант':
                # Курсант может получить доступ только к своим задачам
                query = """
                    SELECT t.*, 
                           u.username as cadet_name, 
                           u.surname as cadet_surname,
                           u.email as cadet_email,
                           p.title as project_title,
                           p.description as project_description,
                           p.curator_id,
                           p.status as project_status,
                           p.deadline as project_deadline,
                           ts.status_name,
                           ts.description as status_description,
                           cu.username as curator_name,
                           cu.surname as curator_surname,
                           cu.email as curator_email
                    FROM tasks t
                    JOIN users u ON t.cadet_id = u.id
                    JOIN projects p ON t.project_id = p.id
                    JOIN task_status_codes ts ON t.status_code = ts.status_code
                    JOIN users cu ON p.curator_id = cu.id
                    WHERE t.id = ? AND t.cadet_id = ?
                """
                params = [task_id, user_id]

            elif user_role == 'куратор':
                # Куратор может получить доступ к задачам в своих проектах
                query = """
                    SELECT t.*, 
                           u.username as cadet_name, 
                           u.surname as cadet_surname,
                           u.email as cadet_email,
                           p.title as project_title,
                           p.description as project_description,
                           p.curator_id,
                           p.status as project_status,
                           p.deadline as project_deadline,
                           ts.status_name,
                           ts.description as status_description,
                           cu.username as curator_name,
                           cu.surname as curator_surname,
                           cu.email as curator_email,
                           (SELECT COUNT(*) FROM files WHERE task_id = t.id) as file_count
                    FROM tasks t
                    JOIN users u ON t.cadet_id = u.id
                    JOIN projects p ON t.project_id = p.id
                    JOIN task_status_codes ts ON t.status_code = ts.status_code
                    JOIN users cu ON p.curator_id = cu.id
                    WHERE t.id = ? AND p.curator_id = ?
                """
                params = [task_id, user_id]

            else:
                return None

            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
