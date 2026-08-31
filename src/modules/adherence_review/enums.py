"""Severity/Action enums, split out from service.py to break a circular
import: service.py's orchestrator calls into llm.py (classify_remedy), and
llm.py's enforce_patient_message_gate needs Action -- if both enums stayed
defined in service.py, llm.py importing them back from service.py would
import a module still mid-initialization. Both service.py and llm.py import
from here instead; service.py re-exports both names so existing callers
importing them from src.modules.adherence_review.service (established by
Stage 4, before this split existed) keep working unchanged.
"""
from enum import Enum


class Severity(str, Enum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class Action(str, Enum):
    NONE = "NONE"
    PATIENT_NOTIFICATION = "PATIENT_NOTIFICATION"
    DOCTOR_WARNING = "DOCTOR_WARNING"
    DOCTOR_ALERT = "DOCTOR_ALERT"
