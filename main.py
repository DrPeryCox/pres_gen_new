import os
import uuid
import json
import shutil
import traceback

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from video_processor import process_video_with_presentation
from generator import PresentationGenerator
from celery_worker import create_video_task # Наша новая Celery задача
from celery.result import AsyncResult

app = FastAPI(
    title="PPTX Generator API",
    description="API для генерации презентаций PowerPoint из JSON.",
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

def cleanup_files(paths: list[str]):
    """Функция для удаления списка файлов."""
    for path in paths:
        if os.path.exists(path):
            os.remove(path)

@app.post(
    "/generate-presentation/",
    responses={
        200: {
            "content": {"application/vnd.openxmlformats-officedocument.presentationml.presentation": {}},
            "description": "Успешно сгенерированный .pptx файл",
        },
        400: {"description": "Некорректные входные данные"},
        500: {"description": "Внутренняя ошибка при генерации презентации"}
    }
)
async def create_presentation(presentation_json: str = Form(...)):
    try:
        # Pydantic модель автоматически валидирует данные.
        # Преобразуем модель в словарь для нашего генератора.

        data_dict = json.loads(presentation_json)

        generator = PresentationGenerator(data_dict)
        pptx_stream = generator.generate()

        headers = {
            'Content-Disposition': 'attachment; filename="presentation.pptx"'
        }

        return StreamingResponse(
            pptx_stream,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers=headers
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        print(f"Критическая ошибка: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {e}")


# ИЗМЕНЕННЫЙ эндпоинт для генерации видео
@app.post("/generate-video")
async def generate_video_endpoint(
        json_file: UploadFile = File(...),
        presentation_file: UploadFile = File(...),
        video_file: UploadFile = File(...)
):
    """
    Принимает файлы, сохраняет их и запускает фоновую задачу.
    Сразу же перенаправляет пользователя на страницу статуса.
    """
    try:
        # Сохраняем файлы с уникальными именами, чтобы избежать конфликтов
        task_id = str(uuid.uuid4())
        json_path = os.path.join(UPLOADS_DIR, f"{task_id}_{json_file.filename}")
        pres_path = os.path.join(UPLOADS_DIR, f"{task_id}_{presentation_file.filename}")
        video_path = os.path.join(UPLOADS_DIR, f"{task_id}_{video_file.filename}")

        with open(json_path, "wb") as buffer:
            shutil.copyfileobj(json_file.file, buffer)
        with open(pres_path, "wb") as buffer:
            shutil.copyfileobj(presentation_file.file, buffer)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        # Запускаем фоновую задачу
        task = create_video_task.delay(json_path, pres_path, video_path)

        # Перенаправляем пользователя на страницу статуса
        return RedirectResponse(url=f"/video-status/{task.id}", status_code=303)

    except Exception as e:
        traceback.print_exc()
        return HTMLResponse(content=f"<h1>Ошибка при запуске задачи: {e}</h1>", status_code=500)
    finally:
        json_file.file.close()
        presentation_file.file.close()
        video_file.file.close()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Главная страница с формами"""
    return templates.TemplateResponse("index.html", {"request": request})



# НОВЫЙ эндпоинт для скачивания готового файла
@app.get("/download-video/{task_id}")
async def download_video(task_id: str):
    """
    Отдает готовый видеофайл для скачивания.
    """
    task_result = AsyncResult(task_id)
    if not task_result.ready() or task_result.status != 'SUCCESS':
        raise HTTPException(status_code=404, detail="Задача не завершена или завершилась с ошибкой")

    result_info = task_result.result
    file_path = result_info.get('result_path')
    filename = result_info.get('result_filename', 'video.mp4')

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл результата не найден")

    # После скачивания файл можно удалить, чтобы не занимать место
    # Используем BackgroundTask для этого
    # from starlette.background import BackgroundTask
    # return FileResponse(path=file_path, filename=filename, media_type='video/mp4',
    #                     background=BackgroundTask(os.remove, file_path))
    return FileResponse(path=file_path, filename=filename, media_type='video/mp4')


# НОВЫЙ эндпоинт для проверки статуса
@app.get("/video-status/{task_id}", response_class=HTMLResponse)
async def get_video_status(request: Request, task_id: str):
    """
    Отображает страницу статуса задачи.
    Эта страница будет сама себя обновлять.
    """
    task_result = AsyncResult(task_id)
    status = task_result.status
    result = task_result.result

    return templates.TemplateResponse("status.html", {
        "request": request,
        "task_id": task_id,
        "status": status,
        "result": result
    })

# НОВЫЙ эндпоинт для проверки статуса
@app.get("/video-status/{task_id}", response_class=HTMLResponse)
async def get_video_status(request: Request, task_id: str):
    """
    Отображает страницу статуса задачи.
    Эта страница будет сама себя обновлять.
    """
    task_result = AsyncResult(task_id)
    status = task_result.status
    result = task_result.result

    return templates.TemplateResponse("status.html", {
        "request": request,
        "task_id": task_id,
        "status": status,
        "result": result
    })
