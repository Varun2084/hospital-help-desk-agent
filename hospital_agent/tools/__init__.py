"""Feature registry: har feature ke naam ke saamne uske tools.

Naya feature jodne ke 3 kadam:
  1. tools/ me nayi file aur function likhein (docstring ke saath).
  2. Neeche FEATURE_TOOLS me feature ka naam aur uske tools jodein.
  3. config/features.yaml me us naam ko true karein.
"""

from hospital_agent.tools.appointments import (
    check_available_slots,
    confirm_action,
    request_booking,
    request_cancellation,
    today_date,
)
from hospital_agent.tools.departments import (
    get_department_info,
    list_departments,
    suggest_department,
)
from hospital_agent.tools.faq import get_hospital_info
from hospital_agent.tools.lab_reports import get_lab_report_status

FEATURE_TOOLS = {
    "department_guide": [list_departments, get_department_info, suggest_department],
    "appointments": [today_date, check_available_slots, request_booking, request_cancellation, confirm_action],
    "hospital_faq": [get_hospital_info],
    "lab_reports": [get_lab_report_status],
}
