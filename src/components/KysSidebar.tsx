import React, { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  ChevronRight,
  ChevronDown,
  ShieldAlert,
  AlertTriangle,
  Link2,
  Search,
  MessageSquare,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Layers,
  CheckCircle2,
  Scale,
} from 'lucide-react';
import { StatsResponse } from '../types/kys';

export interface KysSidebarProps {
  activeTreeKey: string;
  onSelectTreeKey: (key: string) => void;
  stats: StatsResponse | null;
  conflictCount: number;
  gapCount: number;
  missingRefsCount: number;
  decisionCount: number;
  docCountsByType: Record<string, number>;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenSearch: () => void;
  onOpenAsk: () => void;
  onOpenSettings: () => void;
}

interface DocTypeCategory {
  key: string;
  label: string;
  docTypes: string[];
}

const CATEGORIES: DocTypeCategory[] = [
  {
    key: 'PROSEDUR',
    label: 'Prosedürler',
    docTypes: ['PROSEDUR'],
  },
  {
    key: 'TALIMAT',
    label: 'Talimatlar',
    docTypes: ['TALIMAT'],
  },
  {
    key: 'FORM',
    label: 'Formlar & Raporlar',
    docTypes: ['FORM'],
  },
  {
    key: 'EL_KITABI',
    label: 'El Kitapları & Kılavuzlar',
    docTypes: ['EL_KITABI'],
  },
  {
    key: 'POLITIKA',
    label: 'Politika & Yönetmelikler',
    docTypes: ['POLITIKA', 'YONETMELIK'],
  },
  {
    key: 'SUREC',
    label: 'Süreç & Akış Kartları',
    docTypes: ['PROSES_KARTI', 'SUREC'],
  },
  {
    key: 'DIGER',
    label: 'Diğer Kontrollü Dokümanlar',
    docTypes: ['GOREV_TANIMI', 'YETKI_MATRISI', 'LISTE', 'PLAN', 'DIS_KAYNAK'],
  },
];

export const KysSidebar: React.FC<KysSidebarProps> = ({
  activeTreeKey,
  onSelectTreeKey,
  stats,
  conflictCount,
  gapCount,
  missingRefsCount,
  decisionCount,
  docCountsByType,
  collapsed,
  onToggleCollapse,
  onOpenSearch,
  onOpenAsk,
  onOpenSettings,
}) => {
  const [docTreeOpen, setDocTreeOpen] = useState<boolean>(true);

  const getCategoryCount = (cat: DocTypeCategory): number => {
    let sum = 0;
    cat.docTypes.forEach((t) => {
      sum += docCountsByType[t] || 0;
    });
    return sum;
  };

  const totalDocs = stats?.documents ?? 0;

  if (collapsed) {
    return (
      <aside className="kys-sidebar kys-sidebar-collapsed" aria-label="KYS Navigasyon">
        <div className="kys-sidebar-top-collapsed">
          <button
            type="button"
            className="icon-btn kys-collapse-btn"
            onClick={onToggleCollapse}
            title="Navigasyon Ağacını Genişlet"
            aria-label="Navigasyon Ağacını Genişlet"
          >
            <PanelLeft size={18} />
          </button>
        </div>

        <div className="kys-sidebar-icons">
          <button
            type="button"
            className={`kys-nav-icon-btn ${activeTreeKey === 'ALL' ? 'active' : ''}`}
            onClick={() => onSelectTreeKey('ALL')}
            title={`Tüm Dokümanlar (${totalDocs})`}
          >
            <Layers size={18} />
          </button>

          <button
            type="button"
            className={`kys-nav-icon-btn ${activeTreeKey === 'DECISIONS' ? 'active' : ''}`}
            onClick={() => onSelectTreeKey('DECISIONS')}
            title={`Karar Envanteri & Yetki Limitleri (${decisionCount})`}
          >
            <Scale size={18} />
          </button>

          <button
            type="button"
            className={`kys-nav-icon-btn ${activeTreeKey === 'CONFLICTS' ? 'active alert' : ''}`}
            onClick={() => onSelectTreeKey('CONFLICTS')}
            title={`Kural Çelişkileri (${conflictCount})`}
          >
            <ShieldAlert size={18} />
            {conflictCount > 0 && <span className="mini-badge-dot danger" />}
          </button>

          <button
            type="button"
            className={`kys-nav-icon-btn ${activeTreeKey === 'GAPS' ? 'active warn' : ''}`}
            onClick={() => onSelectTreeKey('GAPS')}
            title={`Açık Noktalar & Boşluklar (${gapCount})`}
          >
            <AlertTriangle size={18} />
            {gapCount > 0 && <span className="mini-badge-dot warn" />}
          </button>

          <button
            type="button"
            className={`kys-nav-icon-btn ${activeTreeKey === 'MISSING_REFS' ? 'active' : ''}`}
            onClick={() => onSelectTreeKey('MISSING_REFS')}
            title={`Eksik Atıflar (${missingRefsCount})`}
          >
            <Link2 size={18} />
          </button>

          <div className="kys-sidebar-divider" />

          <button
            type="button"
            className="kys-nav-icon-btn"
            onClick={onOpenSearch}
            title="Hızlı Ara"
          >
            <Search size={18} />
          </button>

          <button
            type="button"
            className="kys-nav-icon-btn"
            onClick={onOpenAsk}
            title="KYS Soru Asistanı"
          >
            <MessageSquare size={18} />
          </button>

          <button
            type="button"
            className="kys-nav-icon-btn"
            onClick={onOpenSettings}
            title="Sistem Ayarları"
          >
            <Settings size={18} />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="kys-sidebar" aria-label="KYS Klasör ve Doküman Ağacı">
      {/* Brand Header */}
      <div className="kys-sidebar-brand">
        <div className="kys-brand-content">
          <div className="kys-brand-badge">KYS</div>
          <div className="kys-brand-text">
            <span className="kys-brand-title">Doküman & Denetim</span>
            <span className="kys-brand-sub">Kalite Yönetim ve Karar Merkezi</span>
          </div>
        </div>
        <button
          type="button"
          className="icon-btn kys-collapse-btn"
          onClick={onToggleCollapse}
          title="Menüyü Daralt"
          aria-label="Menüyü Daralt"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      {/* Tree Content */}
      <div className="kys-tree-container">
        {/* Section 1: Doküman Yönetimi Ağacı */}
        <div className="kys-tree-section">
          <div className="kys-tree-section-header">
            <span>DOKÜMAN YÖNETİMİ</span>
          </div>

          {/* Root All Documents */}
          <button
            type="button"
            className={`kys-tree-item kys-tree-root ${activeTreeKey === 'ALL' ? 'active' : ''}`}
            onClick={() => onSelectTreeKey('ALL')}
          >
            <div className="kys-tree-item-left">
              <button
                type="button"
                className="kys-expander-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setDocTreeOpen((prev) => !prev);
                }}
                aria-label="Alt dalları aç/kapa"
              >
                {docTreeOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {docTreeOpen ? <FolderOpen size={16} className="text-accent" /> : <Folder size={16} className="text-accent" />}
              <span className="kys-tree-label">Tüm Dokümanlar</span>
            </div>
            <span className="kys-tree-count font-mono">{totalDocs}</span>
          </button>

          {/* Child Document Categories */}
          {docTreeOpen && (
            <div className="kys-tree-children">
              {CATEGORIES.map((cat) => {
                const count = getCategoryCount(cat);
                const isActive = activeTreeKey === cat.key;
                return (
                  <button
                    key={cat.key}
                    type="button"
                    className={`kys-tree-item kys-tree-child ${isActive ? 'active' : ''}`}
                    onClick={() => onSelectTreeKey(cat.key)}
                  >
                    <div className="kys-tree-item-left">
                      <FileText size={14} className={isActive ? 'text-accent' : 'text-muted'} />
                      <span className="kys-tree-label">{cat.label}</span>
                    </div>
                    <span className="kys-tree-count font-mono">{count}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Section 2: Karar Envanteri ve Yetki Limitleri */}
        <div className="kys-tree-section">
          <div className="kys-tree-section-header">
            <span>KARAR & YETKİ MATRİSİ</span>
          </div>

          <button
            type="button"
            className={`kys-tree-item ${activeTreeKey === 'DECISIONS' ? 'active' : ''}`}
            onClick={() => onSelectTreeKey('DECISIONS')}
          >
            <div className="kys-tree-item-left">
              <Scale size={15} className="text-accent" />
              <span className="kys-tree-label">Karar Envanteri & Yetkiler</span>
            </div>
            <span className="kys-badge muted font-mono">{decisionCount}</span>
          </button>
        </div>

        {/* Section 3: Çelişki ve Boşluk Radarı */}
        <div className="kys-tree-section">
          <div className="kys-tree-section-header">
            <span>DENETİM & ÇELİŞKİ RADARI</span>
          </div>

          <button
            type="button"
            className={`kys-tree-item ${activeTreeKey === 'CONFLICTS' ? 'active alert-active' : ''}`}
            onClick={() => onSelectTreeKey('CONFLICTS')}
          >
            <div className="kys-tree-item-left">
              <ShieldAlert size={15} className="text-danger" />
              <span className="kys-tree-label">Kural Çelişkileri</span>
            </div>
            {conflictCount > 0 ? (
              <span className="kys-badge danger font-mono">{conflictCount}</span>
            ) : (
              <span className="kys-tree-clean">
                <CheckCircle2 size={13} className="text-ok" />
              </span>
            )}
          </button>

          <button
            type="button"
            className={`kys-tree-item ${activeTreeKey === 'GAPS' ? 'active warn-active' : ''}`}
            onClick={() => onSelectTreeKey('GAPS')}
          >
            <div className="kys-tree-item-left">
              <AlertTriangle size={15} className="text-warn" />
              <span className="kys-tree-label">Açık Noktalar & Boşluklar</span>
            </div>
            {gapCount > 0 ? (
              <span className="kys-badge warn font-mono">{gapCount}</span>
            ) : (
              <span className="kys-tree-clean">
                <CheckCircle2 size={13} className="text-ok" />
              </span>
            )}
          </button>

          <button
            type="button"
            className={`kys-tree-item ${activeTreeKey === 'MISSING_REFS' ? 'active' : ''}`}
            onClick={() => onSelectTreeKey('MISSING_REFS')}
          >
            <div className="kys-tree-item-left">
              <Link2 size={15} className="text-muted" />
              <span className="kys-tree-label">Eksik / İptal Atıflar</span>
            </div>
            {missingRefsCount > 0 && (
              <span className="kys-badge muted font-mono">{missingRefsCount}</span>
            )}
          </button>
        </div>

        {/* Section 4: Hızlı Araçlar */}
        <div className="kys-tree-section">
          <div className="kys-tree-section-header">
            <span>HIZLI ARAÇLAR</span>
          </div>

          <button
            type="button"
            className="kys-tree-item kys-action-item"
            onClick={onOpenSearch}
          >
            <div className="kys-tree-item-left">
              <Search size={14} className="text-muted" />
              <span className="kys-tree-label">Gelişmiş Madde Arama</span>
            </div>
            <kbd className="kys-kbd">Ara</kbd>
          </button>

          <button
            type="button"
            className="kys-tree-item kys-action-item"
            onClick={onOpenAsk}
          >
            <div className="kys-tree-item-left">
              <MessageSquare size={14} className="text-muted" />
              <span className="kys-tree-label">KYS Soru Asistanı</span>
            </div>
            <span className="kys-tree-tag">AI Destekli</span>
          </button>
        </div>
      </div>

      {/* Sidebar Footer */}
      <div className="kys-sidebar-footer">
        <button
          type="button"
          className="kys-footer-btn"
          onClick={onOpenSettings}
        >
          <Settings size={15} />
          <span>Sistem Yapılandırması</span>
        </button>
      </div>
    </aside>
  );
};
