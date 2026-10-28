import React from 'react';
import { StatsResponse, HealthResponse } from '../types/kys';
import { Sun, Moon, Settings, FileText, GitBranch, ShieldCheck, RefreshCw } from 'lucide-react';

interface HeaderProps {
  stats: StatsResponse | null;
  health: HealthResponse | null;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onOpenSettings: () => void;
  onRefresh: () => void;
  loading?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  stats,
  health,
  theme,
  onToggleTheme,
  onOpenSettings,
  onRefresh,
  loading = false,
}) => {
  return (
    <header>
      <div className="header-container">
        <div className="header-left">
          <span className="brand-badge">KYS</span>
          <h1>Kalite Yönetim Sistemi</h1>

          {stats && (
            <div className="header-stats">
              <span className="stat-item" title="Toplam Doküman">
                <FileText size={14} />
                <span className="stat-value">{stats.documents ?? 0}</span> doküman
              </span>
              {typeof stats.processes === 'number' && (
                <span className="stat-item" title="Süreçler">
                  <GitBranch size={14} />
                  <span className="stat-value">{stats.processes}</span> süreç
                </span>
              )}
              {typeof stats.rules === 'number' && (
                <span className="stat-item" title="Kurallar">
                  <ShieldCheck size={14} />
                  <span className="stat-value">{stats.rules}</span> kural
                </span>
              )}
            </div>
          )}
        </div>

        <div className="header-actions">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '12.5px',
              padding: '4px 8px',
              borderRadius: 'var(--radius)',
              background: 'var(--panel-hover)',
              border: '1px solid var(--line)',
            }}
            title={
              health
                ? `Sunucu Durumu: ${health.ok ? 'Aktif' : 'Pasif'} | Model: ${health.model || '-'}`
                : 'Sunucuya bağlanılamadı'
            }
          >
            <span className={`status-dot ${health?.ok ? 'ok' : 'err'}`} />
            <span>{health?.ok ? 'API Bağlı' : 'Bağlantı Yok'}</span>
          </div>

          <button
            className="icon-btn"
            onClick={onRefresh}
            disabled={loading}
            title="Verileri ve Durumu Yenile"
          >
            <RefreshCw size={15} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          </button>

          <button
            className="icon-btn"
            onClick={onToggleTheme}
            title={`Temayı Değiştir (${theme === 'dark' ? 'Açık' : 'Koyu'})`}
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          <button
            className="icon-btn"
            onClick={onOpenSettings}
            title="API ve Token Ayarları"
          >
            <Settings size={15} />
            <span>Ayarlar</span>
          </button>
        </div>
      </div>
    </header>
  );
};
