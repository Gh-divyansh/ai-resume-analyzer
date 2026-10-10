from pydantic import BaseModel


class Experience(BaseModel):
    company: str
    role: str
    duration: str


class Education(BaseModel):
    degree: str
    institution: str


class ResumeData(BaseModel):
    name: str
    title: str
    summary: str
    skills: list[str]
    experience: list[Experience]
    education: list[Education]
    projects: list[str]