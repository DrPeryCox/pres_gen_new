import os
import shutil
from celery import Celery
from video_processor import process_video_with_presentation # Импортируем вашу функцию

# Настраиваем Celery. 'tasks' - это просто имя.
# broker - это наш Redis, куда сервер будет класть задачи.
# backend - тоже Redis, куда воркер будет класть результат.
# Читаем URL Redis из переменной окружения.
# Если ее нет, используем значение по умолчанию для локального запуска без Docker.
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'tasks',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Важно: Celery должен знать, где искать исходный код задач.
celery_app.conf.update(
    task_track_started=True,
)

UPLOADS_DIR = "uploads" # Убедитесь, что эта папка существует

def cleanup_files(paths: list[str]):
    """Функция для удаления списка файлов."""
    for path in paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"Error removing file {path}: {e}")

@celery_app.task(bind=True)
def create_video_task(self, json_path: str, pres_path: str, video_path: str):
    """
    Celery-задача для асинхронной генерации видео.
    `bind=True` позволяет получить доступ к объекту задачи `self`.
    """
    output_filename = f"processed_video_{self.request.id}.mp4"
    output_path = os.path.join(UPLOADS_DIR, output_filename)

    # Список всех временных файлов, которые нужно будет удалить в конце
    temp_files_to_clean = [json_path, pres_path, video_path, output_path]

    try:
        # Здесь мы можем передавать прогресс выполнения
        self.update_state(state='PROGRESS', meta={'status': 'Начинаю обработку...'})

        # Вызываем вашу основную функцию обработки
        process_video_with_presentation(
            json_path=json_path,
            presentation_path=pres_path,
            video_path=video_path,
            output_path=output_path
        )

        # Если все успешно, возвращаем путь к готовому файлу
        return {'status': 'SUCCESS', 'result_path': output_path, 'result_filename': output_filename}

    except Exception as e:
        # В случае ошибки, Celery автоматически пометит задачу как FAILED
        # и сохранит исключение.
        print(f"Task failed: {e}")
        # Подчищаем за собой в случае ошибки
        cleanup_files(temp_files_to_clean)
        # Перевыбрасываем исключение, чтобы Celery корректно обработал сбой
        raise e
    finally:
        # ВАЖНО: Не удаляем output_path, если задача выполнена успешно!
        # Удаляем только исходники.
        cleanup_files([json_path, pres_path, video_path])