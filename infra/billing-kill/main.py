"""Bütçe kesici: bütçe bildirimi maliyetin bütçeyi aştığını söylerse projenin faturalandırmasını kapatır.

Cloud Billing bütçesi → Pub/Sub konusu → bu fonksiyon. Faturalandırma kapanınca projedeki ücretli
servisler (Cloud Run dahil) durur; veri silinmez. Yeniden açmak elle yapılır.
"""

import base64
import json
import os

import functions_framework
from googleapiclient import discovery
from googleapiclient.errors import HttpError

PROJECT_ID = os.environ["KILL_PROJECT_ID"]
PROJECT_NAME = f"projects/{PROJECT_ID}"


def _billing():
    return discovery.build("cloudbilling", "v1", cache_discovery=False)


def _billing_enabled(billing):
    """Okuma izni yoksa None döner; kesme yine denenir (yalnızca deleteBillingAssignment gerekir)."""
    try:
        return billing.projects().getBillingInfo(name=PROJECT_NAME).execute().get("billingEnabled")
    except HttpError as e:
        print(f"faturalandırma durumu okunamadı: {e.status_code}")
        return None


@functions_framework.cloud_event
def stop_billing(event):
    data = json.loads(base64.b64decode(event.data["message"]["data"]).decode())
    cost = float(data.get("costAmount", 0))
    budget = float(data.get("budgetAmount", 0))
    print(f"bütçe bildirimi: maliyet={cost} bütçe={budget} {data.get('currencyCode', '')}")

    if data.get("selfTest"):
        # Kurulum testi: yetkiyi doğrula, hiçbir şeyi değiştirme.
        crm = discovery.build("cloudresourcemanager", "v1", cache_discovery=False)
        perms = crm.projects().testIamPermissions(
            resource=PROJECT_ID,
            body={"permissions": ["resourcemanager.projects.deleteBillingAssignment"]},
        ).execute().get("permissions", [])
        print(f"SELFTEST yetki={perms} faturalandirma_acik={_billing_enabled(_billing())}")
        return

    if budget <= 0 or cost <= budget:
        print("bütçe aşılmadı; işlem yok")
        return

    billing = _billing()
    if _billing_enabled(billing) is False:
        print("faturalandırma zaten kapalı")
        return
    billing.projects().updateBillingInfo(name=PROJECT_NAME, body={"billingAccountName": ""}).execute()
    print(f"FATURALANDIRMA KAPATILDI: {PROJECT_ID}")
