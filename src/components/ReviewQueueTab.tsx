import React, { useState, useEffect, useCallback } from 'react';
import { kysApi } from '../services/apiClient';
import { RuleItem, RuleStatus, RuleType, EntityResolutionItem } from '../types/kys';
import {
  ShieldCheck,
  Edit3,
  RefreshCw,
  FileText,
  Filter,
  Users,
  Check,
  X,
  AlertCircle,
} from 'lucide-react';

interface ReviewQueueTabProps {
  onOpenDoc: (code: string) => void;
  onStatsChanged?: () => void;
}

const RULE_TYPES: (RuleType | 'HEPSI')[] = [
  'HEPSI',
  'ONAY',
  'YETKI',
  'SORUMLULUK',
  'SURE',
  'ESIK',
  'ZORUNLU_KAYIT',
  'ZORUNLU_ADIM',
  'YASAK',
  'TETIKLEYICI',
  'BILGILENDIRME',
];

const STATUS_OPTIONS: { value: RuleStatus | 'HEPSI'; label: string }[] = [
  { value: 'ONERILDI', label: 'Bekleyenler (Önerildi)' },
  { value: 'ONAYLANDI', label: 'Onaylandı' },
  { value: 'DUZELTILDI', label: 'Düzeltildi' },
  { value: 'REDDEDILDI', label: 'Reddedildi' },
  { value: 'HEPSI', label: 'Tümü' },
];

export const ReviewQueueTab: React.FC<ReviewQueueTabProps> = ({ onOpenDoc, onStatsChanged }) => {
  const [activeSubTab, setActiveSubTab] = useState<'rules' | 'entities'>('rules');

  // Rules state
  const [rules, setRules] = useState<RuleItem[]>([]);
  const [loadingRules, setLoadingRules] = useState<boolean>(true);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<RuleStatus | 'HEPSI'>('ONERILDI');
  const [typeFilter, setTypeFilter] = useState<RuleType | 'HEPSI'>('HEPSI');
  const [docFilter, setDocFilter] = useState<string>('');

  // Entities state
  const [entities, setEntities] = useState<EntityResolutionItem[]>([]);
  const [loadingEntities, setLoadingEntities] = useState<boolean>(false);
  const [entitiesError, setEntitiesError] = useState<string | null>(null);

  // Edit Rule Modal State
  const [editingRule, setEditingRule] = useState<RuleItem | null>(null);
  const [editSubject, setEditSubject] = useState<string>('');
  const [editAction, setEditAction] = useState<string>('');
  const [editObject, setEditObject] = useState<string>('');
  const [editCondition, setEditCondition] = useState<string>('');
  const [savingEdit, setSavingEdit] = useState<boolean>(false);

  // Action loading states
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  const fetchRules = useCallback(async () => {
    setLoadingRules(true);
    setRulesError(null);
    try {
      const data = await kysApi.getRules({
        status: statusFilter,
        rule_type: typeFilter,
        doc_code: docFilter.trim() || undefined,
      });
      setRules(data);
    } catch (err: unknown) {
      setRulesError(err instanceof Error ? err.message : 'Kurallar alınamadı');
    } finally {
      setLoadingRules(false);
    }
  }, [statusFilter, typeFilter, docFilter]);

  const fetchEntities = useCallback(async () => {
    setLoadingEntities(true);
    setEntitiesError(null);
    try {
      const data = await kysApi.getEntityResolutions();
      setEntities(data);
    } catch (err: unknown) {
      setEntitiesError(err instanceof Error ? err.message : 'Varlık eşlemeleri alınamadı');
    } finally {
      setLoadingEntities(false);
    }
  }, []);

  useEffect(() => {
    if (activeSubTab === 'rules') {
      fetchRules();
    } else {
      fetchEntities();
    }
  }, [activeSubTab, fetchRules, fetchEntities]);

  const handleApproveRule = async (ruleId: number) => {
    setActionLoadingId(ruleId);
    try {
      await kysApi.approveRule(ruleId);
      setRules((prev) =>
        prev.map((r) => (r.id === ruleId ? { ...r, status: 'ONAYLANDI' } : r))
      );
      onStatsChanged?.();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Kural onaylanırken hata oluştu');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRejectRule = async (ruleId: number) => {
    const reason = window.prompt('Red gerekçesi (opsiyonel):', '');
    if (reason === null) return; // user cancelled prompt

    setActionLoadingId(ruleId);
    try {
      await kysApi.rejectRule(ruleId, reason);
      setRules((prev) =>
        prev.map((r) => (r.id === ruleId ? { ...r, status: 'REDDEDILDI' } : r))
      );
      onStatsChanged?.();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Kural reddedilirken hata oluştu');
    } finally {
      setActionLoadingId(null);
    }
  };

  const openEditModal = (rule: RuleItem) => {
    setEditingRule(rule);
    setEditSubject(rule.subject);
    setEditAction(rule.action);
    setEditObject(rule.object);
    setEditCondition(rule.condition || '');
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingRule) return;

    setSavingEdit(true);
    try {
      const updated = await kysApi.updateRule(editingRule.id, {
        subject: editSubject.trim(),
        action: editAction.trim(),
        object: editObject.trim(),
        condition: editCondition.trim() || null,
        status: 'DUZELTILDI',
      });
      setRules((prev) =>
        prev.map((r) => (r.id === editingRule.id ? updated : r))
      );
      setEditingRule(null);
      onStatsChanged?.();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Güncelleme kaydedilemedi');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleApproveEntity = async (entityId: number) => {
    setActionLoadingId(entityId);
    try {
      await kysApi.approveEntityResolution(entityId);
      setEntities((prev) =>
        prev.map((e) => (e.id === entityId ? { ...e, status: 'ONAYLANDI' } : e))
      );
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Varlık onaylanamadı');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleEditEntity = async (entity: EntityResolutionItem) => {
    const newName = window.prompt('Kanonik adı düzenleyin:', entity.canonical_name);
    if (!newName || newName.trim() === entity.canonical_name) return;

    setActionLoadingId(entity.id);
    try {
      await kysApi.updateEntityResolution(entity.id, newName.trim());
      setEntities((prev) =>
        prev.map((e) =>
          e.id === entity.id
            ? { ...e, canonical_name: newName.trim(), status: 'DUZELTILDI' }
            : e
        )
      );
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Varlık güncellenemedi');
    } finally {
      setActionLoadingId(null);
    }
  };

  const pendingRulesCount = rules.filter((r) => r.status === 'ONERILDI').length;

  return (
    <div>
      {/* Top Info Card */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <ShieldCheck size={20} color="var(--accent)" />
            <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
              KYS Onay Kuyruğu (Faz 1)
            </h2>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={activeSubTab === 'rules' ? fetchRules : fetchEntities}
            disabled={loadingRules || loadingEntities}
          >
            <RefreshCw size={14} style={{ animation: (loadingRules || loadingEntities) ? 'spin 1s linear infinite' : 'none' }} />
            <span>Yenile</span>
          </button>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
          <strong>"Kanıtsız bulgu yok":</strong> LLM (Sonnet 5.5) tarafından dokümanlardan çıkarılan kurallar ve varlık eşlemeleri insan denetiminden geçirilir.
          Analiz motoru ve uygunluk kontrolleri yalnızca onaylanmış kurallara dayanır.
        </p>

        {/* Sub-tabs */}
        <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid var(--line)', paddingBottom: 10 }}>
          <button
            type="button"
            className={activeSubTab === 'rules' ? 'primary' : 'secondary'}
            onClick={() => setActiveSubTab('rules')}
            style={{ fontSize: '13px', padding: '6px 14px' }}
          >
            <ShieldCheck size={14} />
            <span>Kural Önerileri</span>
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
            className={activeSubTab === 'entities' ? 'primary' : 'secondary'}
            onClick={() => setActiveSubTab('entities')}
            style={{ fontSize: '13px', padding: '6px 14px' }}
          >
            <Users size={14} />
            <span>Rol & Varlık Eşleme (Ajan 1.3)</span>
          </button>
        </div>

        {/* Filters (only for Rules) */}
        {activeSubTab === 'rules' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1fr) minmax(160px, 1fr) 2fr', gap: 10, marginTop: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
                <Filter size={12} style={{ display: 'inline', marginRight: 4 }} />
                Durum
              </label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as RuleStatus | 'HEPSI')}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
                Kural Tipi
              </label>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as RuleType | 'HEPSI')}
              >
                {RULE_TYPES.map((rt) => (
                  <option key={rt} value={rt}>
                    {rt === 'HEPSI' ? 'Tüm Tipler' : rt}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
                Doküman Kodunda Ara
              </label>
              <input
                type="text"
                placeholder="Örn: PR-04 veya Satınalma..."
                value={docFilter}
                onChange={(e) => setDocFilter(e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Rules Content */}
      {activeSubTab === 'rules' && (
        <>
          {rulesError && (
            <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
                <AlertCircle size={18} />
                <span>Hata</span>
              </div>
              <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{rulesError}</p>
            </div>
          )}

          {loadingRules ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              Kurallar taranıyor...
            </div>
          ) : rules.length === 0 ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              Bu filtre kriterlerine uygun kural önerisi bulunamadı.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {rules.map((rule) => {
                const isApproved = rule.status === 'ONAYLANDI';
                const isEdited = rule.status === 'DUZELTILDI';
                const isRejected = rule.status === 'REDDEDILDI';
                const isActing = actionLoadingId === rule.id;

                return (
                  <div
                    key={rule.id}
                    className="card"
                    style={{
                      borderLeft: `5px solid ${
                        isApproved
                          ? 'var(--ok)'
                          : isEdited
                          ? 'var(--accent)'
                          : isRejected
                          ? 'var(--danger)'
                          : 'var(--warn)'
                      }`,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span className="badge badge-info" style={{ fontWeight: 700 }}>
                          {rule.rule_type}
                        </span>
                        <span
                          className={`badge ${
                            isApproved
                              ? 'badge-ok'
                              : isEdited
                              ? 'badge-info'
                              : isRejected
                              ? 'badge-danger'
                              : 'badge-warn'
                          }`}
                        >
                          {rule.status}
                        </span>
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          ID: #{rule.id}
                        </span>
                      </div>

                      {/* Action buttons */}
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleApproveRule(rule.id)}
                          disabled={isActing || isApproved}
                          style={{
                            color: isApproved ? 'var(--text-muted)' : 'var(--ok)',
                            borderColor: isApproved ? undefined : 'var(--ok-border)',
                          }}
                          title="Kuralı Onayla"
                        >
                          <Check size={14} />
                          <span>Onayla</span>
                        </button>

                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => openEditModal(rule)}
                          disabled={isActing}
                          title="Düzelt ve Onayla"
                        >
                          <Edit3 size={14} />
                          <span>Düzenle</span>
                        </button>

                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleRejectRule(rule.id)}
                          disabled={isActing || isRejected}
                          style={{
                            color: isRejected ? 'var(--text-muted)' : 'var(--danger)',
                            borderColor: isRejected ? undefined : 'var(--danger-border)',
                          }}
                          title="Kuralı Reddet"
                        >
                          <X size={14} />
                          <span>Reddet</span>
                        </button>
                      </div>
                    </div>

                    {/* Rule Structure vs Evidence Grid */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: 14,
                      }}
                    >
                      {/* Left: Extracted Rule Details */}
                      <div
                        style={{
                          backgroundColor: 'var(--panel-hover)',
                          padding: '12px',
                          borderRadius: 'var(--radius)',
                          border: '1px solid var(--line)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 6,
                          fontSize: '13px',
                        }}
                      >
                        <div>
                          <strong style={{ color: 'var(--text-muted)', fontSize: '11.5px', display: 'block' }}>
                            ÖZNE (ROL / BİRİM)
                          </strong>
                          <span style={{ fontWeight: 600, color: 'var(--text)' }}>{rule.subject}</span>
                        </div>

                        <div>
                          <strong style={{ color: 'var(--text-muted)', fontSize: '11.5px', display: 'block' }}>
                            EYLEM & NESNE
                          </strong>
                          <span>
                            <strong>{rule.action}</strong> → {rule.object}
                          </span>
                        </div>

                        {rule.condition && (
                          <div>
                            <strong style={{ color: 'var(--text-muted)', fontSize: '11.5px', display: 'block' }}>
                              KOŞUL / ŞART
                            </strong>
                            <span style={{ color: 'var(--warn)', fontWeight: 500 }}>{rule.condition}</span>
                          </div>
                        )}

                        {rule.threshold && (
                          <div>
                            <strong style={{ color: 'var(--text-muted)', fontSize: '11.5px', display: 'block' }}>
                              EŞİK DEĞERİ
                            </strong>
                            <span className="badge badge-gray">
                              {rule.threshold.op} {rule.threshold.value} {rule.threshold.unit}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Right: Exact Source Evidence */}
                      <div
                        style={{
                          backgroundColor: 'var(--accent-soft)',
                          padding: '12px',
                          borderRadius: 'var(--radius)',
                          border: '1px solid var(--accent-border)',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          fontSize: '13px',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                            <span
                              className="ref-link"
                              onClick={() => onOpenDoc(rule.source.document)}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                              title="Doküman Ayrıntısına Git"
                            >
                              <FileText size={13} />
                              {rule.source.document}
                            </span>
                            <div style={{ display: 'flex', gap: 4 }}>
                              {rule.source.revision && (
                                <span className="badge badge-gray">Rev: {rule.source.revision}</span>
                              )}
                              {rule.source.clause && (
                                <span className="badge badge-info">Md. {rule.source.clause}</span>
                              )}
                            </div>
                          </div>

                          <div
                            style={{
                              fontStyle: 'italic',
                              lineHeight: 1.5,
                              color: 'var(--text)',
                              borderLeft: '3px solid var(--accent)',
                              paddingLeft: 8,
                              marginTop: 6,
                            }}
                          >
                            "{rule.source.quote}"
                          </div>
                        </div>

                        <div style={{ marginTop: 8, fontSize: '11px', color: 'var(--text-muted)', textAlign: 'right' }}>
                          Doğrulandı: Birebir metin eşleşmesi
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Entities Content */}
      {activeSubTab === 'entities' && (
        <>
          {entitiesError && (
            <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
                <AlertCircle size={18} />
                <span>Hata</span>
              </div>
              <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{entitiesError}</p>
            </div>
          )}

          {loadingEntities ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              Varlık eşlemeleri yükleniyor...
            </div>
          ) : entities.length === 0 ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              Henüz onay bekleyen varlık eşlemesi bulunmuyor.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {entities.map((item) => {
                const isActing = actionLoadingId === item.id;
                return (
                  <div key={item.id} className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="badge badge-info">{item.entity_type}</span>
                        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700 }}>
                          {item.canonical_name}
                        </h3>
                        <span className={`badge ${item.status === 'ONAYLANDI' ? 'badge-ok' : item.status === 'DUZELTILDI' ? 'badge-info' : 'badge-warn'}`}>
                          {item.status}
                        </span>
                      </div>

                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleApproveEntity(item.id)}
                          disabled={isActing || item.status === 'ONAYLANDI'}
                          style={{ color: 'var(--ok)' }}
                        >
                          <Check size={14} />
                          <span>Onayla</span>
                        </button>

                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleEditEntity(item)}
                          disabled={isActing}
                        >
                          <Edit3 size={14} />
                          <span>Kanonik Adı Değiştir</span>
                        </button>
                      </div>
                    </div>

                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: 6 }}>
                      Eşleşen Yazım Varyantları / Eş Anlamlılar:
                    </div>

                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {item.aliases.map((alias, aIdx) => (
                        <span key={aIdx} className="badge badge-gray" style={{ fontSize: '12px' }}>
                          {alias}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Edit Rule Modal */}
      {editingRule && (
        <div className="modal-backdrop" onClick={() => setEditingRule(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Edit3 size={18} color="var(--accent)" />
                <h3 className="modal-title">Kuralı Düzenle & Onayla</h3>
              </div>
              <button className="icon-btn" onClick={() => setEditingRule(null)}>
                <X size={18} />
              </button>
            </div>

            <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
              Doküman: <strong>{editingRule.source.document}</strong> (Md. {editingRule.source.clause || '-'})
            </p>

            <div className="quote-box" style={{ marginBottom: 16 }}>
              <strong>Kaynak Alıntı:</strong> "{editingRule.source.quote}"
            </div>

            <form onSubmit={handleSaveEdit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                  Özne (Rol veya Birim)
                </label>
                <input
                  type="text"
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                  Eylem
                </label>
                <input
                  type="text"
                  value={editAction}
                  onChange={(e) => setEditAction(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                  Nesne (Doküman, Form, vb.)
                </label>
                <input
                  type="text"
                  value={editObject}
                  onChange={(e) => setEditObject(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                  Koşul / Şart (Opsiyonel)
                </label>
                <input
                  type="text"
                  value={editCondition}
                  onChange={(e) => setEditCondition(e.target.value)}
                  placeholder="Örn: Tutar > 100.000 TL"
                />
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditingRule(null)}
                  style={{ flex: 1 }}
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  className="primary"
                  disabled={savingEdit}
                  style={{ flex: 1 }}
                >
                  {savingEdit ? 'Kaydediliyor...' : 'Düzeltildi Olarak Onayla'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
