import React from 'react';
import { MessageSquare, Search, FileText, GitBranch, AlertTriangle, BookOpen } from 'lucide-react';

export type TabType = 'ask' | 'search' | 'docs' | 'processes' | 'refs' | 'doc';

interface NavProps {
  currentTab: TabType;
  onSelectTab: (tab: TabType) => void;
  activeDocCode: string | null;
}

export const Nav: React.FC<NavProps> = ({ currentTab, onSelectTab, activeDocCode }) => {
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
        <span>Süreçler</span>
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
