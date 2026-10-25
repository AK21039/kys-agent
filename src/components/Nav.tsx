import React from 'react';
import {
  MessageSquare,
  Search,
  FileText,
  GitBranch,
  AlertTriangle,
  BookOpen,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';

export type TabType =
  | 'ask'
  | 'search'
  | 'docs'
  | 'processes'
  | 'review'
  | 'radar'
  | 'sandbox'
  | 'refs'
  | 'doc';

interface NavProps {
  currentTab: TabType;
  onSelectTab: (tab: TabType) => void;
  activeDocCode: string | null;
  pendingRulesCount?: number;
  criticalFindingsCount?: number;
}

export const Nav: React.FC<NavProps> = ({
  currentTab,
  onSelectTab,
  activeDocCode,
  pendingRulesCount = 0,
  criticalFindingsCount = 0,
}) => {
  return (
    <nav aria-label="Ana Menü">
      <button
        type="button"
        className={currentTab === 'ask' ? 'active' : ''}
        onClick={() => onSelectTab('ask')}
      >
        <MessageSquare size={16} />
        <span>Soru Sor</span>
      </button>

      <button
        type="button"
        className={currentTab === 'search' ? 'active' : ''}
        onClick={() => onSelectTab('search')}
      >
        <Search size={16} />
        <span>Ara</span>
      </button>

      <button
        type="button"
        className={currentTab === 'docs' ? 'active' : ''}
        onClick={() => onSelectTab('docs')}
      >
        <FileText size={16} />
        <span>Dokümanlar</span>
      </button>

      <button
        type="button"
        className={currentTab === 'processes' ? 'active' : ''}
        onClick={() => onSelectTab('processes')}
      >
        <GitBranch size={16} />
        <span>Süreç & Karar Stüdyosu</span>
      </button>

      <button
        type="button"
        className={currentTab === 'review' ? 'active' : ''}
        onClick={() => onSelectTab('review')}
        style={{ position: 'relative' }}
      >
        <ShieldCheck size={16} />
        <span>Onay Kuyruğu</span>
        {pendingRulesCount > 0 && (
          <span
            style={{
              backgroundColor: 'var(--warn)',
              color: '#fff',
              borderRadius: '10px',
              padding: '1px 6px',
              fontSize: '11px',
              fontWeight: 700,
              marginLeft: 4,
            }}
          >
            {pendingRulesCount}
          </span>
        )}
      </button>

      <button
        type="button"
        className={currentTab === 'radar' ? 'active' : ''}
        onClick={() => onSelectTab('radar')}
        style={{ position: 'relative' }}
      >
        <ShieldAlert size={16} />
        <span>Denetim Radarı</span>
        {criticalFindingsCount > 0 && (
          <span
            style={{
              backgroundColor: 'var(--danger)',
              color: '#fff',
              borderRadius: '10px',
              padding: '1px 6px',
              fontSize: '11px',
              fontWeight: 700,
              marginLeft: 4,
            }}
          >
            {criticalFindingsCount}
          </span>
        )}
      </button>

      <button
        type="button"
        className={currentTab === 'sandbox' ? 'active' : ''}
        onClick={() => onSelectTab('sandbox')}
      >
        <Sparkles size={16} />
        <span>Kum Havuzu</span>
      </button>

      <button
        type="button"
        className={currentTab === 'refs' ? 'active' : ''}
        onClick={() => onSelectTab('refs')}
      >
        <AlertTriangle size={16} />
        <span>Eksik Atıflar</span>
      </button>

      {activeDocCode && (
        <button
          type="button"
          className={currentTab === 'doc' ? 'active' : ''}
          onClick={() => onSelectTab('doc')}
        >
          <BookOpen size={16} />
          <span>Ayrıntı: {activeDocCode}</span>
        </button>
      )}
    </nav>
  );
};
