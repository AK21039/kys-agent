import React from 'react';
import { X, Search, MessageSquare } from 'lucide-react';
import { AskTab } from './AskTab';
import { SearchTab } from './SearchTab';

export interface KysToolModalProps {
  tool: 'ask' | 'search' | null;
  onClose: () => void;
  onOpenDoc: (code: string) => void;
}

export const KysToolModal: React.FC<KysToolModalProps> = ({ tool, onClose, onOpenDoc }) => {
  if (!tool) return null;

  return (
    <div className="kys-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="kys-modal-container"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="kys-modal-header">
          <div className="kys-modal-title-group">
            {tool === 'search' ? (
              <>
                <Search size={18} className="text-accent" />
                <h3>Gelişmiş Doküman & Madde Arama</h3>
              </>
            ) : (
              <>
                <MessageSquare size={18} className="text-accent" />
                <h3>KYS Alıntılı Soru Asistanı</h3>
              </>
            )}
          </div>
          <button
            type="button"
            className="icon-btn kys-modal-close"
            onClick={onClose}
            title="Kapat"
            aria-label="Kapat"
          >
            <X size={16} />
          </button>
        </div>

        <div className="kys-modal-body">
          {tool === 'search' ? (
            <SearchTab
              onOpenDoc={(code) => {
                onOpenDoc(code);
                onClose();
              }}
            />
          ) : (
            <AskTab
              onOpenDoc={(code) => {
                onOpenDoc(code);
                onClose();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
};
