from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class FlatnessData(BaseModel):
    holeIndex: int
    holeAngle: float
    flatness: float


class ReportInfo(BaseModel):
    Balde_ID: Optional[str] = None
    Report_Time: Optional[datetime] = None
    UserName: Optional[str] = None
    MachineStartTime: Optional[datetime] = None
    MachineEndTime: Optional[datetime] = None
    Duration: Optional[str] = None
    DeepthSum: Optional[float] = None


class ReportStatistics(BaseModel):
    measure_time: str
    max_value: float
    min_value: float
    peak_to_peak: float
    rms_value: float
    data_count: int


class ReportItem(BaseModel):
    id: int
    file_name: str
    bladeId: str
    created_at: str


class FlatnessResponse(BaseModel):
    report: ReportItem
    statistics: ReportStatistics
    flatness_data: List[FlatnessData]


class FileItem(BaseModel):
    id: int
    file_name: str
    created_at: str
    file_size: int
    flatness_count: int


class ReportListResponse(BaseModel):
    reports: List[FileItem]