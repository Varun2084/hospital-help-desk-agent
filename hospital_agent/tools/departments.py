"""Department guide wale tools: list, jaankari, aur lakshan (symptom) se department sujhana."""

from hospital_agent.config import (
    active_departments,
    feature_required,
    get_department,
    load_hospital_info,
)
from hospital_agent.text_match import contains_keyword


@feature_required("department_guide")
def list_departments() -> dict:
    """Lists all departments that currently run an OPD.

    Returns:
        A dictionary with 'count' and 'departments', each having 'id', 'name' and 'name_hi'.
    """
    depts = active_departments()
    return {
        "count": len(depts),
        "departments": [{"id": d.id, "name": d.name, "name_hi": d.name_hi} for d in depts],
    }


@feature_required("department_guide")
def get_department_info(department_id: str) -> dict:
    """Returns location, OPD days and OPD hours for one department.

    Args:
        department_id: The department's id, for example 'cardiology'. Use list_departments to find ids.

    Returns:
        Department details, or an error with the list of valid ids.
    """
    dept = get_department(department_id)
    if dept is None:
        return {
            "status": "error",
            "message": f"'{department_id}' naam ka koi department nahin mila.",
            "valid_ids": [d.id for d in active_departments()],
        }
    if not dept.active:
        return {"status": "closed", "message": f"{dept.name} ki OPD abhi band hai."}
    return {
        "status": "ok",
        "id": dept.id,
        "name": dept.name,
        "name_hi": dept.name_hi,
        "location": f"{dept.building}, floor {dept.floor}",
        "opd_days": dept.opd_days,
        "opd_hours": dept.opd_hours,
    }


@feature_required("department_guide")
def suggest_department(symptoms: str) -> dict:
    """Suggests which OPD department a patient could visit, based on symptom words.
    This is routing help only, not a diagnosis.

    Args:
        symptoms: The patient's symptoms in their own words, in Hindi or English.

    Returns:
        Up to 3 matching departments with the words that matched, plus a safety note.
    """
    matches = []
    for dept in active_departments():
        hits = [k for k in dept.keywords if contains_keyword(symptoms, k)]
        if hits:
            matches.append({"id": dept.id, "name": dept.name, "matched_words": hits})
    matches.sort(key=lambda m: len(m["matched_words"]), reverse=True)
    if not matches:
        general = get_department("general_medicine")
        if general is None or not general.active:  # fallback department hi na ho to crash nahin, helpdesk
            return {"suggestions": [], "helpdesk": load_hospital_info().helpdesk,
                    "note": "Koi department match nahin hua. Kripya helpdesk se puchhein."}
        matches = [{"id": general.id, "name": general.name, "matched_words": []}]
    return {
        "suggestions": matches[:3],
        "note": "Yeh sirf department chunne me madad hai, diagnosis nahin. Doctor hi jaanch karke batayenge.",
    }
