"""HttpHIS: HIS ka contract, HTTP API par (sandbox ya asli vendor).

Timeout aur network error yahan pehchaane jaate hain.
"""

import httpx

from hospital_agent.his.base import Booking, BookingNotFound, HISError, HISTimeout, HISUnavailable, SlotTaken


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
        return Booking(**{k: data[k] for k in Booking.__dataclass_fields__})

    def booked_times(self, department_id: str, date: str) -> set[str]:
        r = self._call("GET", "/v1/slots/booked", params={"department_id": department_id, "date": date})
        if r.status_code != 200:
            raise HISError(f"slots: HTTP {r.status_code}")
        return set(r.json()["booked_times"])

    def book(self, key, patient_name, phone, department_id, date, time) -> Booking:
        body = {"patient_name": patient_name, "phone": phone, "department_id": department_id,
                "date": date, "time": time}
        r = self._call("POST", "/v1/bookings", json=body, headers={"Idempotency-Key": key})
        if r.status_code in (200, 201):
            return self._booking(r.json())
        if r.status_code == 409:
            raise SlotTaken(f"{department_id} {date} {time}")
        raise HISError(f"book: HTTP {r.status_code} {r.text[:200]}")

    def find_by_key(self, key: str) -> Booking | None:
        r = self._call("GET", f"/v1/bookings/by-key/{key}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HISError(f"find_by_key: HTTP {r.status_code}")
        return self._booking(r.json())

    def get_booking(self, reference: str) -> Booking | None:
        r = self._call("GET", f"/v1/bookings/{reference}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise HISError(f"get_booking: HTTP {r.status_code}")
        return self._booking(r.json())

    def cancel(self, reference: str, phone: str) -> Booking:
        r = self._call("POST", f"/v1/bookings/{reference}/cancel", json={"phone": phone})
        if r.status_code == 404:
            raise BookingNotFound(reference)
        if r.status_code != 200:
            raise HISError(f"cancel: HTTP {r.status_code}")
        return self._booking(r.json())
