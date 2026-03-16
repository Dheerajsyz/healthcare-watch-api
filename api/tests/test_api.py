"""API tests: auth, RBAC, patients, vitals, activity."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def test_token_success(client: AsyncClient, provider_token: str):
    assert len(provider_token) > 20


async def test_token_invalid_credentials(client: AsyncClient):
    resp = await client.post("/auth/token", data={"username": "nobody@x.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_healthz(client: AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Protected routes — 401 without token
# ---------------------------------------------------------------------------

async def test_list_patients_requires_auth(client: AsyncClient):
    resp = await client.get("/patients")
    assert resp.status_code == 401


async def test_post_patient_requires_auth(client: AsyncClient):
    resp = await client.post("/patients", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Patient CRUD
# ---------------------------------------------------------------------------

async def test_create_patient(client: AsyncClient, provider_token: str):
    resp = await client.post(
        "/patients",
        json={
            "email": "newpatient@test.com",
            "password": "Patient123!",
            "full_name": "New Patient",
            "sex": "M",
            "consent_given": True,
        },
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newpatient@test.com"
    assert data["sex"] == "M"
    return data


async def test_create_patient_duplicate_email(client: AsyncClient, provider_token: str):
    payload = {"email": "dup@test.com", "password": "Patient123!", "full_name": "Dup"}
    await client.post("/patients", json=payload, headers={"Authorization": f"Bearer {provider_token}"})
    resp = await client.post("/patients", json=payload, headers={"Authorization": f"Bearer {provider_token}"})
    assert resp.status_code == 409


async def test_create_patient_invalid_sex(client: AsyncClient, provider_token: str):
    resp = await client.post(
        "/patients",
        json={"email": "bad@test.com", "password": "Password1!", "full_name": "Bad", "sex": "Z"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 422


async def test_list_patients(client: AsyncClient, provider_token: str):
    resp = await client.get("/patients", headers={"Authorization": f"Bearer {provider_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


async def test_pagination(client: AsyncClient, provider_token: str):
    resp = await client.get("/patients?limit=1&offset=0", headers={"Authorization": f"Bearer {provider_token}"})
    assert resp.status_code == 200
    assert resp.json()["limit"] == 1


async def test_get_patient_not_found(client: AsyncClient, provider_token: str):
    resp = await client.get(
        "/patients/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Patient‑scoped RBAC: patient cannot access other patients
# ---------------------------------------------------------------------------

async def _create_patient_and_get_token(client: AsyncClient, provider_token: str, email: str) -> tuple[str, str]:
    """Helper: creates a patient via provider, logs in as that patient, returns (patient_id, token)."""
    create_resp = await client.post(
        "/patients",
        json={"email": email, "password": "Patient123!", "full_name": "Test Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert create_resp.status_code == 201, create_resp.json()
    patient_id = create_resp.json()["id"]
    login_resp = await client.post("/auth/token", data={"username": email, "password": "Patient123!"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return patient_id, token


async def test_patient_cannot_access_other_patient(client: AsyncClient, provider_token: str):
    pid_a, token_a = await _create_patient_and_get_token(client, provider_token, "patA@test.com")
    pid_b, _ = await _create_patient_and_get_token(client, provider_token, "patB@test.com")

    resp = await client.get(f"/patients/{pid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 403


async def test_patient_can_access_own_record(client: AsyncClient, provider_token: str):
    pid, token = await _create_patient_and_get_token(client, provider_token, "self@test.com")
    resp = await client.get(f"/patients/{pid}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Vitals
# ---------------------------------------------------------------------------

async def test_post_and_get_vitals(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "vpatient@test.com", "password": "Patient123!", "full_name": "Vital Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    # Post a vital
    v_resp = await client.post(
        f"/patients/{pid}/vitals",
        json={"metric": "HR", "value": 72, "recorded_at": "2026-03-01T10:00:00Z"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert v_resp.status_code == 201
    assert v_resp.json()["metric"] == "HR"

    # Get vitals
    list_resp = await client.get(f"/patients/{pid}/vitals", headers={"Authorization": f"Bearer {provider_token}"})
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1


async def test_vitals_date_range_filter(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "drpatient@test.com", "password": "Patient123!", "full_name": "Date Range Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    for day, value in [("2026-02-01T10:00:00Z", 70), ("2026-03-01T10:00:00Z", 80)]:
        await client.post(
            f"/patients/{pid}/vitals",
            json={"metric": "HR", "value": value, "recorded_at": day},
            headers={"Authorization": f"Bearer {provider_token}"},
        )

    resp = await client.get(
        f"/patients/{pid}/vitals?start=2026-03-01T00:00:00Z",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["value"] == 80.0


async def test_vitals_invalid_metric(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "invmetric@test.com", "password": "Patient123!", "full_name": "Invalid Metric Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.post(
        f"/patients/{pid}/vitals",
        json={"metric": "INVALID_METRIC", "value": 100, "recorded_at": "2026-03-01T10:00:00Z"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 422


async def test_vitals_flagging(client: AsyncClient, provider_token: str):
    """SPO2 < 92 should be auto-flagged."""
    create_resp = await client.post(
        "/patients",
        json={"email": "spo2patient@test.com", "password": "Patient123!", "full_name": "SPO2 Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.post(
        f"/patients/{pid}/vitals",
        json={"metric": "SPO2", "value": 89, "recorded_at": "2026-03-01T10:00:00Z"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_flagged"] is True


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

async def test_post_and_get_activity(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "actpatient@test.com", "password": "Patient123!", "full_name": "Activity Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    a_resp = await client.post(
        f"/patients/{pid}/activity",
        json={"recorded_at": "2026-03-01T10:00:00Z", "steps": 8000, "sleep_hours": 7.5},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert a_resp.status_code == 201
    assert a_resp.json()["steps"] == 8000

    list_resp = await client.get(f"/patients/{pid}/activity", headers={"Authorization": f"Bearer {provider_token}"})
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1


async def test_activity_negative_steps_rejected(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "negsteps@test.com", "password": "Patient123!", "full_name": "Neg Steps Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.post(
        f"/patients/{pid}/activity",
        json={"recorded_at": "2026-03-01T10:00:00Z", "steps": -100},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

async def test_list_alerts_empty(client: AsyncClient, provider_token: str):
    """New patient has no alert events yet."""
    create_resp = await client.post(
        "/patients",
        json={"email": "alertpatient@test.com", "password": "Patient123!", "full_name": "Alert Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    resp = await client.get(
        f"/patients/{pid}/alerts",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] == 0


async def test_alerts_requires_auth(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "alertauth@test.com", "password": "Patient123!", "full_name": "Alert Auth Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.get(f"/patients/{pid}/alerts")
    assert resp.status_code == 401


async def test_update_alert_not_found(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "alertnf@test.com", "password": "Patient123!", "full_name": "Alert NF Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.patch(
        f"/patients/{pid}/alerts/00000000-0000-0000-0000-000000000000",
        json={"status": "RESOLVED"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 404


async def test_update_alert_invalid_status(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "alertinvalid@test.com", "password": "Patient123!", "full_name": "Alert Invalid Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.patch(
        f"/patients/{pid}/alerts/00000000-0000-0000-0000-000000000000",
        json={"status": "DELETED"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Risk Score
# ---------------------------------------------------------------------------

async def test_risk_score_not_found_initially(client: AsyncClient, provider_token: str):
    """New patient without any vitals has no risk score."""
    create_resp = await client.post(
        "/patients",
        json={"email": "riskpatient@test.com", "password": "Patient123!", "full_name": "Risk Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    resp = await client.get(
        f"/patients/{pid}/risk",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 404


async def test_risk_calculate(client: AsyncClient, provider_token: str):
    """POST /risk/calculate returns a risk score."""
    create_resp = await client.post(
        "/patients",
        json={"email": "riskcalc@test.com", "password": "Patient123!", "full_name": "Risk Calc Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    # Post a vital first so there's data
    await client.post(
        f"/patients/{pid}/vitals",
        json={"metric": "HR", "value": 72, "recorded_at": "2026-03-01T10:00:00Z"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )

    resp = await client.post(
        f"/patients/{pid}/risk/calculate",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "score" in body
    assert "risk_level" in body
    assert body["risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert 0.0 <= body["score"] <= 100.0


async def test_risk_get_after_calculate(client: AsyncClient, provider_token: str):
    """GET /risk returns latest score after calculation."""
    create_resp = await client.post(
        "/patients",
        json={"email": "riskget@test.com", "password": "Patient123!", "full_name": "Risk Get Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    await client.post(
        f"/patients/{pid}/risk/calculate",
        headers={"Authorization": f"Bearer {provider_token}"},
    )

    resp = await client.get(
        f"/patients/{pid}/risk",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["patient_id"] == pid


async def test_risk_critical_vitals(client: AsyncClient, provider_token: str):
    """Critically abnormal vitals should produce a HIGH or CRITICAL risk level."""
    create_resp = await client.post(
        "/patients",
        json={"email": "riskcrit@test.com", "password": "Patient123!", "full_name": "Risk Crit Patient"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]

    # Post critically abnormal vitals
    for metric, value in [("SPO2", 88), ("HR", 135), ("BP_SYS", 160), ("GLUCOSE", 220)]:
        await client.post(
            f"/patients/{pid}/vitals",
            json={"metric": metric, "value": value, "recorded_at": "2026-03-01T10:00:00Z"},
            headers={"Authorization": f"Bearer {provider_token}"},
        )

    resp = await client.post(
        f"/patients/{pid}/risk/calculate",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["risk_level"] in ("HIGH", "CRITICAL")
    assert resp.json()["score"] > 50


async def test_risk_requires_auth(client: AsyncClient, provider_token: str):
    create_resp = await client.post(
        "/patients",
        json={"email": "risknoauth@test.com", "password": "Patient123!", "full_name": "Risk No Auth"},
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    pid = create_resp.json()["id"]
    resp = await client.get(f"/patients/{pid}/risk")
    assert resp.status_code == 401
