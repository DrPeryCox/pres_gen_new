import os
import uuid
import shutil
from fastapi import Request, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask  # Убедитесь, что этот импорт есть
import json
from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import StreamingResponse

from models import PresentationRequest
from generator import PresentationGenerator

# Импортируем нашу логику
# from presentation_generator import create_presentation_from_json
from video_processor import process_video_with_presentation

# --- Настройка приложения ---
app = FastAPI(title="Генератор Контента")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)



# пример json
# должны быть заполнены либо только центр, либо оба право и лево
input_json = {
    "slides": [
        {
            "title": "1st title",
            "background": "TBD задний фон слайда",
            "font_color": [255, 255, 255], # размер шрифта в формате RGB
            "font_size": 24, # размер шрифта заголовка для заголовка
            "start": 2, # время начала показа слайда (в сек от начала видео)
            "end": 34, # время конца показа слайда (в сек от начала видео)
            "left_part": {
                "content": "Какой-то текст",
                "bullet_points": ["список", "булет", "поинтов"],
                "list": ["нумерованный", "список"],
                "image": "TBD картинка",
                "font_size": 16,  # размер шрифта для конкретной части
                "font_color": [255, 255, 255],  # размер шрифта для конкретной части в формате RGB
            },
            "center_part": {},
            "right_part": {},
        },
        ...
    ]
}





# --- Вспомогательные функции ---
def cleanup_files(paths: list[str]):
    """Функция для удаления списка файлов."""
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


# --- Эндпоинты ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Главная страница с формами"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post(
    "/generate-presentation/",
    tags=["Presentation"],
    summary="Создать презентацию из JSON в form-data",
    description="Принимает JSON-структуру в виде строки в поле 'presentation_json' и возвращает .pptx файл.",
    responses={
        200: {
            "content": {"application/vnd.openxmlformats-officedocument.presentationml.presentation": {}},
            "description": "Успешно сгенерированный .pptx файл",
        },
        400: {
            "description": "Некорректный JSON или ошибка валидации данных",
        },
        422: {
            "description": "Ошибка валидации данных (стандартный ответ FastAPI/Pydantic)",
        },
        500: {
            "description": "Внутренняя ошибка при генерации презентации",
        }
    }
)
async def generate_presentation_endpoint(presentation_json: str = Form(
        ...,
        description="Строка, содержащая полную JSON-структуру презентации."
    ),
    output_filename: str = Form(
        "presentation.pptx",
        description="Желаемое имя для скачиваемого файла."
    )
):
    """
    Эндпоинт для генерации презентации.

    - **presentation_json**: Строка с JSON-данными.
    - **output_filename**: Имя файла для заголовка Content-Disposition.
    """
    try:
        # 1. Парсим строку JSON в словарь Python
        data_dict = json.loads(presentation_json)

        # 2. Валидируем полученный словарь с помощью нашей Pydantic модели
        # Это дает нам всю мощь валидации, даже при приеме данных через форму
        validated_data = PresentationRequest.model_validate(data_dict)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Ошибка декодирования JSON. Пожалуйста, проверьте синтаксис."
        )
    except Exception as e:
        # Pydantic при ошибке валидации вызовет свое исключение,
        # которое FastAPI перехватит и вернет 422 ошибку.
        # Мы ловим другие возможные ошибки.
        raise HTTPException(status_code=400, detail=f"Ошибка валидации данных: {e}")

    try:
        # 3. Преобразуем валидированную модель обратно в словарь для генератора
        # Используем exclude_none=True для чистоты данных
        generator_data = validated_data.model_dump(exclude_none=True)

        generator = PresentationGenerator(generator_data)
        pptx_stream = generator.generate()

        # 4. Формируем заголовки для скачивания файла
        headers = {
            'Content-Disposition': f'attachment; filename="{output_filename}"'
        }

        return StreamingResponse(
            pptx_stream,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers=headers
        )

    except Exception as e:
        # Ловим ошибки, которые могли произойти на этапе генерации
        print(f"Критическая ошибка во время генерации PPTX: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера при генерации файла: {e}")



@app.post("/generate-video")
async def generate_video_endpoint(
        presentation_file: UploadFile = File(...),
        video_file: UploadFile = File(...)
):
    """
    Принимает два файла, обрабатывает их и отдает видеофайл.
    """
    pres_path = os.path.join(UPLOADS_DIR, f"pres_{uuid.uuid4()}_{presentation_file.filename}")
    video_path = os.path.join(UPLOADS_DIR, f"vid_{uuid.uuid4()}_{video_file.filename}")

    temp_files_to_clean = [pres_path, video_path]

    try:
        with open(pres_path, "wb") as buffer:
            shutil.copyfileobj(presentation_file.file, buffer)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        output_filename = f"processed_video_{uuid.uuid4()}.mp4"
        output_path = os.path.join(UPLOADS_DIR, output_filename)
        temp_files_to_clean.append(output_path)

        process_video_with_presentation(
            presentation_path=pres_path,
            video_path=video_path,
            output_path=output_path
        )

        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type='video/mp4',
            background=BackgroundTask(cleanup_files, temp_files_to_clean)
        )
    except Exception as e:
        cleanup_files(temp_files_to_clean)
        return HTMLResponse(content=f"<h1 style='color:red;'>Произошла ошибка при обработке видео: {e}</h1>",
                            status_code=500)
    finally:
        presentation_file.file.close()
        video_file.file.close()

