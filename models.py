from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class ContentPart(BaseModel):
    """Модель для одной части контента (left, center, right)."""
    content: Optional[str] = None
    bullet_points: Optional[List[str]] = Field(default=None)
    image: Optional[str] = None  # base64 строка
    font_size: Optional[int] = 16
    font_color: Optional[List[int]] = Field(default=[0, 0, 0])

    @model_validator(mode='before')
    @classmethod
    def check_exclusive_content(cls, values):
        """Проверяет, что задан только один тип контента."""
        content_fields = ['content', 'bullet_points', 'image']
        provided_fields = [field for field in content_fields if values.get(field)]
        if len(provided_fields) > 1:
            raise ValueError(f"Должен быть указан только один из полей: {', '.join(content_fields)}")
        return values


class Slide(BaseModel):
    """Модель для одного слайда."""
    title: str
    background: Optional[str] = None  # base64 строка
    font_color: List[int] = Field(default=[0, 0, 0])
    font_size: int = 24

    # Игнорируемые поля
    start: Optional[int] = Field(default=None, exclude=True)
    end: Optional[int] = Field(default=None, exclude=True)

    # Части контента
    left_part: Optional[ContentPart] = None
    center_part: Optional[ContentPart] = None
    right_part: Optional[ContentPart] = None

    @model_validator(mode='before')
    @classmethod
    def check_layout_parts(cls, values):
        """Проверяет, что задан либо center_part, либо left/right."""
        has_center = 'center_part' in values and values['center_part']
        has_left_or_right = ('left_part' in values and values['left_part']) or \
                            ('right_part' in values and values['right_part'])
        if has_center and has_left_or_right:
            raise ValueError("Нельзя одновременно использовать 'center_part' и 'left_part'/'right_part'")
        return values


class PresentationRequest(BaseModel):
    """Корневая модель для всего JSON-запроса."""
    slides: List[Slide]
