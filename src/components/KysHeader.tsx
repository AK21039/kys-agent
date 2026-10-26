import React from 'react';
import {
  Search,
  Sun,
  Moon,
  Settings,
  RefreshCw,
  Play,
  ShieldAlert,
  AlertTriangle,
  FileCheck,
  Activity,
  Layers,
  Scale,
} from 'lucide-react';
import { HealthResponse, StatsResponse } from '../types/kys';

export interface KysHeaderProps {
  breadcrumbs: { label: string; onClick?: () => void }[];
  searchQuery: string;
  onSearchChange: (q: string) => void;
  stats: StatsResponse | null;
  health: HealthResponse | null;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onOpenSettings: () => void;
  onRefresh: () => void;
  onRunAudit: () => void;
  onSelectTreeKey: (key: string) => void;
  runningAudit: boolean;
  loading: boolean;
  conflictCount: number;
  gapCount: number;
  decisionCount: number;
}

export const KysHeader: React.FC<KysHeaderProps> = ({
  breadcrumbs,
  searchQuery,
  onSearchChange,
  stats,
  health,
  theme,
  onToggleTheme,
  onOpenSettings,
  onRefresh,
  onRunAudit,
  onSelectTreeKey,
  runningAudit,
  loading,
  conflictCount,
  gapCount,
  decisionCount,
}) => {
  const isHealthy = health?.ok === true;
  const totalDocs = stats?.documents ?? 0;

  return (
    <header className="kys-header" aria-label="KYS Üst Panel">
      <div className="kys-header-top">
        {/* Breadcrumb Trail */}
        <nav aria-label="Breadcrumb" className="kys-breadcrumbs">
          {breadcrumbs.map((b, idx) => {
            const isLast = idx === breadcrumbs.length - 1;
            return (
              <React.Fragment key={idx}>
                {idx > 0 && <span className="kys-breadcrumb-sep">/</span>}
                {b.onClick && !isLast ? (
                  <button
                    type="button"
                    onClick={b.onClick}
                    className="kys-breadcrumb-link"
                  >
                    {b.label}
                  </button>
                ) : (
                  <span className={`kys-breadcrumb-item ${isLast ? 'current' : ''}`}>
                    {b.label}
                  </span>
                )}
              </React.Fragment>
            );
          })}
        </nav>

        {/* Global Search */}
        <div className="kys-search-box">
          <Search size={14} className="kys-search-icon" />
          <input
            type="text"
            className="kys-search-input"
            placeholder="Doküman kodu, başlık veya karar ara..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className="kys-search-clear"
              onClick={() => onSearchChange('')}
              title="Aramayı temizle"
            >
              ×
            </button>
          )}
        </div>

        {/* Action Controls */}
        <div className="kys-header-controls">
          <button
            type="button"
            className="icon-btn kys-run-audit-btn"
            onClick={onRunAudit}
            disabled={runningAudit}
            title="Sistem genelinde kural çakışmaları ve süreç boşlukları analizini çalıştır"
          >
            <Play
              size={13}
              style={{ animation: runningAudit ? 'spin 1s linear infinite' : 'none' }}
            />
            <span>{runningAudit ? 'Analiz Ediliyor...' : 'Çakışma Analizi Yap'}</span>
          </button>

          <button
            type="button"
            className="icon-btn"
            onClick={onRefresh}
            disabled={loading}
            title="Verileri Yenile"
            aria-label="Verileri Yenile"
          >
            <RefreshCw
              size={14}
              style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
            />
          </button>

          <button
            type="button"
            className="icon-btn"
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Aydınlık moda geç' : 'Karanlık moda geç'}
            aria-label="Tema değiştir"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          <button
            type="button"
            className="icon-btn"
            onClick={onOpenSettings}
            title="Ayarlar & API"
            aria-label="Ayarlar"
          >
            <Settings size={15} />
          </button>

          {/* Health Status Indicator */}
          <div
            className={`kys-health-pill ${isHealthy ? 'ok' : 'err'}`}
            title={
              isHealthy
                ? `FastAPI Aktif (${health?.model || 'LLM hazır'})`
                : 'Arka uç bağlantısı yok / çevrimdışı'
            }
          >
            <span className={`status-dot ${isHealthy ? 'ok' : 'err'}`} />
            <span className="kys-health-label">{isHealthy ? 'Çevrimiçi' : 'Çevrimdışı'}</span>
          </div>
        </div>
      </div>

      {/* KPI Metric Strip */}
      <div className="kys-kpi-bar">
        <button
          type="button"
          className="kys-kpi-item"
          onClick={() => onSelectTreeKey('ALL')}
          title="Tüm Dokümanları Listele"
        >
          <Layers size={14} className="text-accent" />
          <span className="kys-kpi-label">Toplam Doküman:</span>
          <span className="kys-kpi-value font-mono">{totalDocs}</span>
        </button>

        <div className="kys-kpi-sep" />

        <button
          type="button"
          className="kys-kpi-item"
          onClick={() => onSelectTreeKey('DECISIONS')}
          title="Karar Envanterini Listele"
        >
          <Scale size={14} className="text-accent" />
          <span className="kys-kpi-label">Karar & Yetki:</span>
          <span className="kys-kpi-value font-mono">{decisionCount}</span>
        </button>

        <div className="kys-kpi-sep" />

        <button
          type="button"
          className="kys-kpi-item"
          onClick={() => onSelectTreeKey('CONFLICTS')}
          title="Kural Çelişkilerini Görüntüle"
        >
          <ShieldAlert size={14} className={conflictCount > 0 ? 'text-danger' : 'text-ok'} />
          <span className="kys-kpi-label">Kural Çelişkileri:</span>
          <span className={`kys-kpi-value font-mono ${conflictCount > 0 ? 'text-danger font-bold' : 'text-ok'}`}>
            {conflictCount}
          </span>
        </button>

        <div className="kys-kpi-sep" />

        <button
          type="button"
          className="kys-kpi-item"
          onClick={() => onSelectTreeKey('GAPS')}
          title="Açık Noktaları ve Boşlukları Görüntüle"
        >
          <AlertTriangle size={14} className={gapCount > 0 ? 'text-warn' : 'text-ok'} />
          <span className="kys-kpi-label">Açık Kalan Noktalar:</span>
          <span className={`kys-kpi-value font-mono ${gapCount > 0 ? 'text-warn font-bold' : 'text-ok'}`}>
            {gapCount}
          </span>
        </button>

        <div className="kys-kpi-sep" />

        <div className="kys-kpi-item static">
          <FileCheck size={14} className="text-ok" />
          <span className="kys-kpi-label">Yürürlükte:</span>
          <span className="kys-kpi-value font-mono text-ok">
            {totalDocs}
          </span>
        </div>

        {stats?.pending_rules !== undefined && stats.pending_rules > 0 && (
          <>
            <div className="kys-kpi-sep" />
            <div className="kys-kpi-item static">
              <Activity size={14} className="text-warn" />
              <span className="kys-kpi-label">Onay Bekleyen Kural:</span>
              <span className="kys-kpi-value font-mono text-warn">{stats.pending_rules}</span>
            </div>
          </>
        )}
      </div>
    </header>
  );
};
