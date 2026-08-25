from dataclasses import dataclass, field
from typing import List


@dataclass
class Dataset:
    dsn: str
    disp: str
    content: str = "" # holds instream data

@dataclass
class DDStatement:
    name: str
    raw_block: str
    datasets: List[Dataset] = field(default_factory=list)

@dataclass
class JclStep:
    name: str
    program: str
    steplib: List[str] = field(default_factory=list)
    dds:List[DDStatement] = field(default_factory=list)


@dataclass
class JclJob:
    name:str
    joblib: List[str] = field(default_factory=list)
    global_dds: List[DDStatement] = field(default_factory=list)
    steps: List[JclStep] = field(default_factory=list)