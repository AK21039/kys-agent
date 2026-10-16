import React from 'react';
import { StatsResponse } from '../types/kys';

interface HeaderProps {
  stats: StatsResponse | null;
  hasToken: boolean;
  onOpenLogin: () => void;
  onOpenDrive: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  stats,
  hasToken,
  onOpenLogin,
  onOpenDrive,
}) => {
  const getStatusText = () => {
    if (!stats) return 'yükleniyor…';
    if (stats.documents === 0) return '0 doküman · Veritabanı henüz yüklenmedi';
    const dateStr = stats.last_update ? ` · son güncelleme ${String(stats.last_update).slice(0, 10)}` : '';
    return `${stats.documents} doküman${dateStr}`;
  };

  return (
    <header>
      <div className="header-left">
        <h1>KYS Sorgu</h1>
        <small id="status">{getStatusText()}</small>
      </div>
      <div className="header-actions">
        <button
          type="button"
          className="header-btn"
          onClick={onOpenDrive}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', borderColor: 'var(--accent)', color: 'var(--accent)', fontWeight: 500 }}
          title="Google Drive'daki KYS Agent > docs klasörüne bağlan"
        >
          📁 Google Drive (KYS Agent)
        </button>
        <button
          type="button"
          className="header-btn"
          onClick={onOpenLogin}
          title="Erişim Anahtarı Ayarları"
        >
          {hasToken ? '🔑 Anahtar Etkin' : 'Erişim Anahtarı'}
        </button>
      </div>
    </header>
  );
};
