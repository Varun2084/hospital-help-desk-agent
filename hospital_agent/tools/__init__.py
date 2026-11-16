"""Feature registry: har feature ke naam ke saamne uske tools.

Pakka karna (Confirm) model ka tool nahin hai: woh button se tools/actions.py me hota hai.

Naya feature jodne ke 4 kadam:
  1. tools/ me nayi file aur function likhein (docstring ke saath).
  2. Neeche FEATURE_TOOLS me feature ka naam aur uske tools jodein.
  3. agent.py ke SPECIALISTS me us feature ka desk jodein.
  4. config*/features.yaml me flag jodein (testing tak false).
"""

from hospital_agent.tools.appointments import (
    check_available_slots,
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
from hospital_agent.tools.registration import request_registration

FEATURE_TOOLS = {
    "department_guide": [list_departments, get_department_info, suggest_department],
    "appointments": [today_date, check_available_slots, request_booking, request_cancellation],
    "hospital_faq": [get_hospital_info],
    "lab_reports": [get_lab_report_status],
    "registration": [request_registration],
}
