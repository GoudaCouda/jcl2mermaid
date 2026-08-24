from dataclasses import dataclass, field
from typing import List


@dataclass
class Dataset:
    dsn: str
    disp: str

@dataclass
class DDStatement:
    name: str
    raw_block: str
    datasets: List[Dataset] = field(default_factory=list)

@dataclass
class JclStep:
    name: str
    program: str
    dds:List[DDStatement] = field(default_factory=list)


@dataclass
class JclJob:
    name:str
    global_dds: List[DDStatement] = field(default_factory=list)
    steps: List[JclStep] = field(default_factory=list)