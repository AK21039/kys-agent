import React from 'react';

export type TabType = 'ask' | 'search' | 'docs' | 'refs' | 'doc';

interface NavProps {
  currentTab: TabType;
  onSelectTab: (tab: TabType) => void;
  activeDocCode: string | null;
}

export const Nav: React.FC<NavProps> = ({ currentTab, onSelectTab, activeDocCode }) => {
  return (
    <nav>
      <button
        type="button"
        className={currentTab === 'ask' ? 'on' : ''}
        onClick={() => onSelectTab('ask')}
      >
        Soru sor
      </button>
      <button
        type="button"
        className={currentTab === 'search' ? 'on' : ''}
        onClick={() => onSelectTab('search')}
      >
        Ara
      </button>
      <button
        type="button"
        className={currentTab === 'docs' ? 'on' : ''}
        onClick={() => onSelectTab('docs')}
      >
        Dokümanlar
      </button>
      <button
        type="button"
        className={currentTab === 'refs' ? 'on' : ''}
        onClick={() => onSelectTab('refs')}
      >
        Eksik atıflar
      </button>
      {activeDocCode && (
        <button
          type="button"
          className={currentTab === 'doc' ? 'on' : ''}
          onClick={() => onSelectTab('doc')}
        >
          Doküman ({activeDocCode})
        </button>
      )}
    </nav>
  );
};
