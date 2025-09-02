from pdf2image import convert_from_path
import subprocess
import json
import logging
import tempfile
import os
from PyPDF2 import PdfReader
from fastapi.responses import HTMLResponse



logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def convert_pdf_to_images(pdf_path, output_folder='input'):
    logging.info(f'+++++++++++++++++++++++++++ Converting PDF {pdf_path} to images in {output_folder}')
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    slides = convert_from_path(pdf_path)
    image_paths = []
    for i, slide in enumerate(slides):
        image_path = os.path.join(output_folder, f'slide_{i+1:02d}.png')
        slide.save(image_path, 'PNG')
        image_paths.append(image_path)
    return image_paths

def cut_video(input_video_path, start, end, output_video_path, video_codec = 'libx264', audio_codec = 'aac'):
    logging.info('+++++++++++++++++++++++++++ Cutting video')
    cmd = [
        'ffmpeg',
        '-ss', str(start),
        '-to', str(end),
        '-i', input_video_path,
        '-hide_banner',
        '-c:v', video_codec,
        '-c:a', audio_codec,
        '-y',
        output_video_path
    ]
    subprocess.run(cmd, check=True)


def slide_to_video(slide_img_path, duration, output_video_path):
    """
    -loop 1 — зациклить входное изображение (то есть повторять его) для создания видео.
    -i <file> — входной файл (изображение).
    -t <duration> — длительность выходного видео в секундах.
    -vf scale=1280:1080 — видеофильтр (vf) для масштабирования видео до 1280x1080.
    -c:v libx264 — кодек видео.
    -y — перезаписывать без запроса.
    """
    logging.info('+++++++++++++++++++++++++++ Slide to video')
    cmd = [
        'ffmpeg',
        '-loop', '1',
        '-i', slide_img_path,
        '-hide_banner',
        '-t', str(duration),
        '-vf', 'scale=1080:1080',  # Левая часть (2/3 ширины)
        '-c:v', 'libx264',
        '-y',
        output_video_path
    ]
    subprocess.run(cmd, check=True)


def resize_video(input_video_path, output_video_path):
    """
    -i <file> — входной файл.
    -vf scale=640:1080 — масштабирует видео до 640 по ширине и 1080 по высоте.
    -c:v libx264 — кодек видео.
    -y — перезаписывать без запроса.
    """
    logging.info('+++++++++++++++++++++++++++ Resizing video')
    cmd = [
        'ffmpeg',
        '-i', input_video_path,
        '-hide_banner',
        '-vf', 'scale=840:1080',
        '-c:v', 'libx264',
        '-y',
        output_video_path
    ]
    subprocess.run(cmd, check=True)


def combine_videos(slide_video_path, speaker_video_path, output_video_path):
    """
    Объединяет два видео в одно, расположив их горизонтально рядом (слайд слева, спикер справа), и берёт аудио
    только из видео спикера.

    -i <file> (две раза) — два входных видео.
    -filter_complex '[0:v][1:v]hstack=inputs=2[v]' — комплексный фильтр, который объединяет два видеопотока
                                                    горизонтально (hstack), результат сохраняется в метку [v].
    -map '[v]' — взять из фильтра выходное видео.
    -map '1:a?' — взять аудио из второго входного файла (индекс 1), знак вопроса ? значит "если аудио есть, то взять,
                  если нет — не ругаться".
    -c:v libx264 — кодек видео.
    -c:a aac — кодек аудио.
    -y — перезаписывать без запроса.
    """
    logging.info('+++++++++++++++++++++++++++ Combining videos')
    cmd = [
        'ffmpeg',
        '-i', slide_video_path,
        '-i', speaker_video_path,
        '-hide_banner',
        '-filter_complex', '[0:v][1:v]hstack=inputs=2[v]',
        '-map', '[v]',
        '-map', '1:a?',  # Аудио только из видео спикера
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-y',
        output_video_path
    ]
    subprocess.run(cmd, check=True)


def concat_videos(video_list, output_video_path):
    """
    Склеивает несколько видеофайлов последовательно (конкатенация), без перекодирования.
    """
    logging.info('+++++++++++++++++++++++++++ Concatinating videos')
    with open('inputs.txt', 'w') as f:
        for v in video_list:
            f.write(f"file '{v}'\n")
    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', 'inputs.txt',
        '-hide_banner',
        '-c', 'copy',
        '-y',
        output_video_path
    ]
    subprocess.run(cmd, check=True)


def process_video_with_presentation(json_path: str, presentation_path: str, video_path: str, output_path: str):
    """
    Основная функция обработки видео.
    В случае ошибки выбрасывает исключение ValueError.
    """
    logging.info(f"+++++++++++++++++++++++++++ Loading JSON data from {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    slides_data_list = data["slides"]

    reader = PdfReader(presentation_path)
    if len(slides_data_list) != len(reader.pages):
        error_message = f"Количество слайдов не совпадает! В JSON: {len(slides_data_list)}, в PDF: {len(reader.pages)}"
        logging.error(error_message)
        # ИСПРАВЛЕНО: Выбрасываем исключение вместо return
        raise ValueError(error_message)

    # Убедимся, что папка для временных файлов существует
    temp_folder = os.path.dirname(output_path)
    os.makedirs(temp_folder, exist_ok=True)

    slide_image_paths = convert_pdf_to_images(presentation_path, output_folder=temp_folder)

    video_fragments = []
    # Список временных файлов, созданных в цикле, для очистки
    cycle_temp_files = list(slide_image_paths)

    try:
        for i, slide_data in enumerate(slides_data_list):
            logging.info(
                f"+++++++++++++++++++++++++++ Processing slide {i + 1}/{len(slides_data_list)}: '{slide_data.get('title', 'No Title')}' ---")

            start = slide_data['start']
            end = slide_data['end']
            duration = end - start

            slide_img_path = slide_image_paths[i]

            speaker_cut = os.path.join(temp_folder, f'speaker_{i:02d}.mp4')
            cut_video(video_path, start, end, speaker_cut)
            cycle_temp_files.append(speaker_cut)

            slide_vid = os.path.join(temp_folder, f'slide_{i:02d}.mp4')
            slide_to_video(slide_img_path, duration, slide_vid)
            cycle_temp_files.append(slide_vid)

            speaker_resized = os.path.join(temp_folder, f'speaker_{i:02d}_resized.mp4')
            resize_video(speaker_cut, speaker_resized)
            cycle_temp_files.append(speaker_resized)

            combined = os.path.join(temp_folder, f'combined_{i:02d}.mp4')
            combine_videos(slide_vid, speaker_resized, combined)
            video_fragments.append(combined)
            cycle_temp_files.append(combined)

        logging.info("All fragments processed. Concatenating into final video.")
        concat_videos(video_fragments, output_path)

        logging.info(f"Successfully created final video at: {output_path}")
        # ИСПРАВЛЕНО: Функция больше ничего не возвращает при успехе.
        # Ее успешное завершение само по себе является результатом.

    finally:
        # Очищаем все промежуточные файлы, созданные в этом процессе
        inputs_txt_path = 'inputs.txt'
        if os.path.exists(inputs_txt_path):
             cycle_temp_files.append(inputs_txt_path)

        for f_path in cycle_temp_files:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except OSError as e:
                    logging.warning(f"Could not remove temp file {f_path}: {e}")