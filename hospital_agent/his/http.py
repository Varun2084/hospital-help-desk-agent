"""HttpHIS: HIS ka contract, HTTP API par (sandbox ya asli vendor).

Sandbox ka contract (asli vendor ke naam aur fields uski API documentation se milane honge):
    GET  /v1/slots?department_id=&date=          khaali slot, har ek ka slot_id
    POST /v1/bookings  {slot_id, patient_ref, request_id}
                                                 201 confirmed + booking_ref, ya 409 slot_unavailable
    GET  /v1/bookings/by-request/{request_id}    is attempt ki booking, agar HIS me bani ho
    GET  /v1/patients/{patient_ref}/bookings     sirf is patient ki bookings
    GET  /v1/patients/{patient_ref}/bookings/{booking_ref}   doosre patient ki ho to 404
    POST /v1/bookings/{booking_ref}/cancel  {patient_ref}

Timeout aur network error yahan pehchaane jaate hain.
"""

import httpx

from hospital_agent.his.base import (
    Booking,
    BookingNotFound,
    HISError,
    HISTimeout,
    HISUnavailable,
    Slot,
    SlotTaken,
)


class HttpHIS:
    def __init__(self, base_url: str, timeout: float = 3.0, client: httpx.Client | None = None):
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout)

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as e:
            raise HISTimeout(f"{method} {path}") from e
        except httpx.TransportError as e:
            raise HISUnavailable(f"{method} {path}: {type(e).__name__}") from e

    @staticmethod
    def _booking(data: dict) -> Booking:
        return Booking(reference=data["booking_ref"], slot_id=data["slot_id"], patient_ref=data["patient_ref"],
                       department_id=data["department_id"], date=data["date"], time=data["time"],
                       status=data["status"])

    def open_slots(self, department_id: str, date: str) -> list[Slot]:
        r = self._call("GET", "/v1/slots", params={"department_id": department_id, "date": date})
        if r.status_code != 200:
            raise HISError(f"slots: HTTP {r.status_code}")
        return [Slot(s["slot_id"], s["time"]) for s in r.json()["slots"]]

    def book(self, request_id: str, slot_id: str, patient_ref: str) -> Booking:
        body = {"slot_id": slot_id, "patient_ref": patient_ref, "request_id": request_id}
        r = self._call("POST", "/v1/bookings", json=body)
        if r.status_code in (200, 201):
            return self._booking(r.json())
        if r.status_code == 409:
            raise SlotTaken(slot_id)
        raise HISError(f"book: HTTP {r.status_code} {r.text[:200]}")

    def find_by_request(self, request_id: str) -> Booking | None:
        r = self._call("GET", f"/v1/bookings/by-request/{request_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HISError(f"find_by_request: HTTP {r.status_code}")
        return self._booking(r.json())

    def list_for_patient(self, patient_ref: str) -> list[Booking]:
        r = self._call("GET", f"/v1/patients/{patient_ref}/bookings")
        if r.status_code != 200:
            raise HISError(f"list_for_patient: HTTP {r.status_code}")
        return [self._booking(b) for b in r.json()["bookings"]]

    def find_for_patient(self, patient_ref: str, reference: str) -> Booking | None:
        r = self._call("GET", f"/v1/patients/{patient_ref}/bookings/{reference}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HISError(f"find_for_patient: HTTP {r.status_code}")
        return self._booking(r.json())

    def cancel(self, reference: str, patient_ref: str) -> Booking:
        r = self._call("POST", f"/v1/bookings/{reference}/cancel", json={"patient_ref": patient_ref})
        if r.status_code == 404:
            raise BookingNotFound(reference)
        if r.status_code != 200:
            raise HISError(f"cancel: HTTP {r.status_code}")
        return self._booking(r.json())
