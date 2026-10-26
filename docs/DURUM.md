\
 
## 2026-10-26 Cloud Run Deploy Calismasi (bu oturum) 

### Sorun 
Cloud Run service kys-agent sadece React (nginx) sunuyordu, Python FastAPI backend yoktu: 
- Unexpected token - /api/* isteklerine index.html donuyordu 
- 405 Method Not Allowed - nginx static dosyalara POST yapiyordu 

### Kok Neden 
Mevcut Dockerfile sadece React build + nginx iceriyordu. Python backend (backend/kys/api/app.py) container icinde yoktu. 

### Cozum (main branch-e commit-lendi) 
| Commit | Degisiklik | 
|--------|------------| 
| dee2628 | Multi-stage Dockerfile: React (node:20) to uvicorn (python:3.12-slim) | 
| e008641 | Fix: COPY package.json ./ explicit before npm install | 
| cb7602d | Fix: BuildKit cache issue - explicit COPY order | 
| 9e0483b | Fix: Add missing tsconfig.json, tsconfig.node.json, vite.config.ts (ai branch-ten) | 

### Yeni Dockerfile Mimarisi (main branch) 
Tek konteyner, tek port (8080), uvicorn StaticFiles ile React SPA sunumu (/qa/app/), API endpointleri (/qa/api/*) dogrudan uvicorn-dan, nginx/supervisor karmasasi yok. 

### Cloud Build Deploy (cloudbuild.yaml) 
Secret Manager entegrasyonu: KYS_ACCESS_TOKEN=kys-access-token:latest, GEMINI_API_KEY=gemini-api-key:latest, KYS_OPENAI_API_KEY=openai-api-key:latest, KYS_DB_URL=gs://kys-agent-db/kys.db 

### Git Branch Stratejisi 
| Branch | Mimari | Durum | 
|--------|--------|-------| 
| main | uvicorn-only (StaticFiles) | Deploy edildi (bu calisma) | 
| ai | nginx + uvicorn + supervisor | Commit edildi, merge YASAK (oturum karari) | 

> Not: Cloud Build / GitHub Actions trigger-i main branch-e bakiyor. Ai branch-i deploy etmek icin trigger konfigurasyonu degistirilmeli. 

### Acik Is Eklemesi 
6. Cloud Run yeni deploy test edilecek - kys-agent service-i yeni Dockerfile ile calisiyor mu?
