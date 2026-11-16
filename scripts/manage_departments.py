"""Departments sambhalne ka chhota command-line tool.

Upyog:
    python scripts/manage_departments.py list
    python scripts/manage_departments.py validate
    python scripts/manage_departments.py impact cardiology
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from hospital_agent import db
from hospital_agent.config import get_department, load_departments
from hospital_agent.tools.common import today


def cmd_list() -> None:
    for d in load_departments().departments:
        status = "active" if d.active else "BAND"
        print(f"{d.id:<18} {status:<7} {', '.join(d.opd_days):<28} {d.opd_hours}")


def cmd_validate() -> int:
    try:
        catalog = load_departments()
    except ValidationError as e:
        print("Config me galti hai:\n", e)
        return 1
    print(f"Config theek hai: {len(catalog.departments)} departments.")
    return 0


def cmd_impact(department_id: str) -> int:
    dept = get_department(department_id)
    if dept is None:
        print(f"'{department_id}' naam ka department config me nahin hai.")
        return 1
    with db.connect() as conn:
        n = db.count_future_bookings(conn, department_id, today().isoformat())
    print(f"{dept.name}: aaj ya aage ki {n} booked appointment(s).")
    if n:
        print("Pehle in patients ko soochit karein ya doosre department me badlein, phir active: false karein.")
    else:
        print("Koi aage ki booking nahin. active: false karna surakshit hai.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["list"]:
        cmd_list()
    elif args == ["validate"]:
        sys.exit(cmd_validate())
    elif len(args) == 2 and args[0] == "impact":
        sys.exit(cmd_impact(args[1]))
    else:
        print(__doc__)
        sys.exit(2)
