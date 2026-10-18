"""`kys analiz` çıktısının Türkçe Markdown raporu. DB'ye yazmaz, LLM yok."""

from datetime import datetime

from .model import CheckOutcome, Finding

LABELS = {
    "guncellik_atif": "1. Yürürlükten kalkmış dokümana atıf (GUNCELLIK)",
    "kirik_referans": "2. Sistemde olmayan doküman koduna atıf — kırık referans (BOSLUK)",
    "adim_sorumlusu": "3. Sorumlusu/onaycısı tanımsız süreç adımı (BOSLUK)",
    "gorev_tanimi_eksik": "4a. Görev tanımı olmayan rol (BOSLUK)",
    "rol_kullanilmiyor": "4b. Hiçbir süreçte/kuralda geçmeyen rol (BOSLUK)",
    "esik_cakismasi": "5. Aynı özne için çakışan eşik/süre değeri (CAKISMA)",
    "mukerrer_dokuman": "6. Mükerrer/kopya doküman (CAKISMA)",
    "karar_yetki": "7. Karar sahibi ↔ ONAY/YETKI kural rolü uyumsuzluğu (YETKI_ASIMI)",
}
SEVERITY_ORDER = ("KRITIK", "ORTA", "DUSUK")


def render_report(outcomes: dict[str, CheckOutcome]) -> str:
    all_findings: list[Finding] = [f for o in outcomes.values() for f in o.findings]
    lines = ["# KYS Denetim Radarı — Bulgu Raporu", "", f"_Üretildi: {datetime.now():%Y-%m-%d %H:%M}_", "",
              "| Kontrol | İncelenen | Bulgu | Not |", "|---|---|---|---|"]
    for name, outcome in outcomes.items():
        lines.append(f"| {LABELS.get(name, name)} | {outcome.considered} | {len(outcome.findings)} | "
                      f"{outcome.note or '-'} |")
    unverified = sum(1 for f in all_findings if f.unverified_basis)
    belirsiz = [f for f in all_findings if f.finding_type.value == "BELIRSIZLIK"]
    graded = [f for f in all_findings if f.finding_type.value != "BELIRSIZLIK"]
    lines += ["", f"**Toplam bulgu: {len(all_findings)}** (doğrulanmamış kaynaklı: {unverified}, "
                  f"kaynağı izlenemeyen/BELİRSİZLİK: {len(belirsiz)})", ""]
    if belirsiz:
        # Doğrulanabilir bir alıntı bulunamadığı için kanıtsız bulgu üretilmez; bunlar ayrı, kısa bir
        # bölümde sayılır (değişmez 1) — aşağıdaki şiddet bölümlerine karışmaz.
        lines.append(f"## BELİRSİZLİK — kaynağı izlenemeyen ({len(belirsiz)})")
        lines.append("")
        for f in belirsiz:
            lines.append(f"- {f.title} · Kontrol: {LABELS.get(f.check, f.check)}")
        lines.append("")
    for sev in SEVERITY_ORDER:
        group = [f for f in graded if f.severity.value == sev]
        if not group:
            continue
        lines.append(f"## {sev} ({len(group)})")
        lines.append("")
        for f in group:
            flag = " _(doğrulanmamış kaynak)_" if f.unverified_basis else ""
            lines.append(f"### {f.title}{flag}")
            lines.append(f"- Tür: {f.finding_type.value} · Kontrol: {LABELS.get(f.check, f.check)}")
            lines.append(f"- Açıklama: {f.explanation}")
            if f.recommendation:
                lines.append(f"- Öneri: {f.recommendation}")
            if f.evidence:
                lines.append("- Kanıt:")
                for ev in f.evidence:
                    loc = f"{ev.get('doc_code')} Rev.{ev.get('revision')}"
                    if ev.get("clause_no"):
                        loc += f" md.{ev['clause_no']}"
                    lines.append(f"  - {loc}: “{ev.get('quote')}”")
            else:
                lines.append("- Kanıt: (yapısal bulgu — alıntı gerektirmez; DB'de ilgili kayıt yok)")
            lines.append("")
    return "\n".join(lines)
