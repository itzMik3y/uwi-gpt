# moodle_api/models.py
from pydantic import BaseModel
from typing import Optional


class MoodleCredentials(BaseModel):
    username: str
    password: str
    time_sort_from: Optional[int] = (
        1744002000  # Consider making these dynamic or configurable
    )
    time_sort_to: Optional[int] = 1744606800
    limit_num: Optional[int] = 6


class SASCredentials(BaseModel):
    username: str
    password: str
