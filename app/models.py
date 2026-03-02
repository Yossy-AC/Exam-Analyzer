from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PassageBase(BaseModel):
    university: str
    year: int
    faculty: str = ""
    question_number: str
    passage_index: int = 1


class PassageCreate(PassageBase):
    id: str
    text_type: str
    text_style: Optional[str] = None
    word_count: Optional[int] = None
    source_title: Optional[str] = None
    source_author: Optional[str] = None
    source_year: Optional[int] = None
    genre_main: str
    genre_sub: str = ""
    theme: str = ""
    has_jp_written: bool = False
    has_en_written: bool = False
    has_summary: bool = False
    comp_type: str = "none"
    has_jp_translation: bool = False
    has_jp_explanation: bool = False
    has_en_explanation: bool = False
    has_jp_summary: bool = False
    has_en_summary: bool = False
    has_visual_info: bool = False
    visual_info_type: str = ""
    reviewed: bool = False
    notes: str = ""


class PassageUpdate(BaseModel):
    text_type: Optional[str] = None
    text_style: Optional[str] = None
    genre_main: Optional[str] = None
    genre_sub: Optional[str] = None
    theme: Optional[str] = None
    has_jp_written: Optional[bool] = None
    has_en_written: Optional[bool] = None
    has_summary: Optional[bool] = None
    comp_type: Optional[str] = None
    has_jp_translation: Optional[bool] = None
    has_jp_explanation: Optional[bool] = None
    has_en_explanation: Optional[bool] = None
    has_jp_summary: Optional[bool] = None
    has_en_summary: Optional[bool] = None
    has_visual_info: Optional[bool] = None
    visual_info_type: Optional[str] = None
    reviewed: Optional[bool] = None
    notes: Optional[str] = None


class TextAnalysisResult(BaseModel):
    text_type: str
    text_style: str
    word_count: int
    source_title: Optional[str] = None
    source_author: Optional[str] = None
    source_year: Optional[int] = None
    genre_main: str
    genre_sub: str = ""
    theme: str = ""


class QuestionAnalysisResult(BaseModel):
    has_jp_written: bool = False
    has_en_written: bool = False
    has_summary: bool = False
    comp_type: str = "none"
    has_jp_translation: bool = False
    has_jp_explanation: bool = False
    has_en_explanation: bool = False
    has_jp_summary: bool = False
    has_en_summary: bool = False
    has_visual_info: bool = False
    visual_info_type: str = ""


class ParsedQuestion(BaseModel):
    university: str
    year: int
    faculty: str = ""
    question_number: str
    passage_index: int = 1
    text_section: str
    questions_section: str
    passage_id: str
