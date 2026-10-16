import { DocumentItem, DocType, DocStatus } from '../types/kys';
import { codeKey } from '../utils/textnorm';

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime?: string;
  size?: string;
  parents?: string[];
}

export interface DriveFolder {
  id: string;
  name: string;
  path: string;
}

export class GoogleDriveService {
  private static async fetchWithAuth(url: string, token: string, options: RequestInit = {}): Promise<Response> {
    const headers = {
      ...options.headers,
      Authorization: `Bearer ${token}`,
    };
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      const errJson = await res.json().catch(() => null);
      throw new Error(errJson?.error?.message || `Google Drive API hatası (${res.status}): ${res.statusText}`);
    }
    return res;
  }

  /**
   * 'KYS Agent' ve 'docs' klasörlerini bulur
   */
  public static async findKysFolders(token: string): Promise<DriveFolder[]> {
    // Klasörleri ara
    const q = "mimeType = 'application/vnd.google-apps.folder' and trashed = false";
    const url = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}&fields=files(id,name,parents)&pageSize=50`;

    const res = await this.fetchWithAuth(url, token);
    const data = await res.json();
    const allFolders: { id: string; name: string; parents?: string[] }[] = data.files || [];

    const kysAgentFolders = allFolders.filter((f) => f.name.toLowerCase().includes('kys agent'));
    const results: DriveFolder[] = [];

    // 'KYS Agent' altındaki 'docs' klasörlerini bul
    for (const parent of kysAgentFolders) {
      const childDocs = allFolders.filter(
        (f) => f.parents?.includes(parent.id) && f.name.toLowerCase() === 'docs'
      );
      if (childDocs.length > 0) {
        for (const child of childDocs) {
          results.push({
            id: child.id,
            name: child.name,
            path: `${parent.name} > ${child.name}`,
          });
        }
      } else {
        // Doğrudan 'KYS Agent' klasörünü de listele
        results.push({
          id: parent.id,
          name: parent.name,
          path: parent.name,
        });
      }
    }

    // Ayrıca adı doğrudan 'docs' veya 'KYS' olan diğer klasörleri ekle
    for (const f of allFolders) {
      if (!results.some((r) => r.id === f.id)) {
        if (f.name.toLowerCase() === 'docs' || f.name.toLowerCase().includes('kys')) {
          results.push({
            id: f.id,
            name: f.name,
            path: f.name,
          });
        }
      }
    }

    return results;
  }

  /**
   * Belirtilen klasördeki dosyaları listeler
   */
  public static async listFilesInFolder(token: string, folderId: string): Promise<DriveFile[]> {
    const q = `'${folderId}' in parents and trashed = false`;
    const url = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}&fields=files(id,name,mimeType,modifiedTime,size)&pageSize=100`;

    const res = await this.fetchWithAuth(url, token);
    const data = await res.json();
    return data.files || [];
  }

  /**
   * Dosya içeriğini metin olarak okur
   */
  public static async readFileContent(token: string, file: DriveFile): Promise<string> {
    if (file.mimeType === 'application/vnd.google-apps.document') {
      // Google Docs belgesini metin olarak dışa aktar
      const url = `https://www.googleapis.com/drive/v3/files/${file.id}/export?mimeType=text/plain`;
      const res = await this.fetchWithAuth(url, token);
      return await res.text();
    } else {
      // Düz metin veya JSON dosyası
      const url = `https://www.googleapis.com/drive/v3/files/${file.id}?alt=media`;
      const res = await this.fetchWithAuth(url, token);
      return await res.text();
    }
  }

  /**
   * Okunan dosya içeriğini KYS DocumentItem yapısına dönüştürür
   */
  public static parseFileToDocuments(fileName: string, content: string): DocumentItem[] {
    const trimmed = content.trim();

    // 1. JSON formatında ise (KYS publish veya export)
    if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parsed.map((item, idx) => ({
            id: item.id || idx + 1,
            code: String(item.code || fileName.replace(/\.[^/.]+$/, '')).trim(),
            code_key: codeKey(item.code || fileName),
            revision: String(item.revision || '00').trim(),
            title: String(item.title || fileName).trim(),
            doc_type: item.doc_type || this.detectDocType(item.code || fileName),
            status: item.status || DocStatus.YURURLUKTE,
            revision_date: item.revision_date || null,
            effective_date: item.effective_date || null,
            owner_unit: item.owner_unit || null,
            summary: item.summary || null,
            parse_warnings: item.parse_warnings || [],
            sections: Array.isArray(item.sections)
              ? item.sections.map((s: any, sIdx: number) => ({
                  id: s.id || sIdx + 1,
                  document_id: item.id || idx + 1,
                  ordinal: s.ordinal || sIdx + 1,
                  clause_no: s.clause_no || null,
                  heading: s.heading || null,
                  heading_path: s.heading_path || null,
                  text: String(s.text || ''),
                }))
              : [],
            references: Array.isArray(item.references) ? item.references : [],
            referenced_by: Array.isArray(item.referenced_by) ? item.referenced_by : [],
          }));
        } else if (parsed && typeof parsed === 'object' && parsed.code) {
          return [
            {
              id: parsed.id || 1,
              code: String(parsed.code).trim(),
              code_key: codeKey(parsed.code),
              revision: String(parsed.revision || '00').trim(),
              title: String(parsed.title || fileName).trim(),
              doc_type: parsed.doc_type || this.detectDocType(parsed.code),
              status: parsed.status || DocStatus.YURURLUKTE,
              revision_date: parsed.revision_date || null,
              effective_date: parsed.effective_date || null,
              owner_unit: parsed.owner_unit || null,
              summary: parsed.summary || null,
              parse_warnings: parsed.parse_warnings || [],
              sections: Array.isArray(parsed.sections) ? parsed.sections : [],
              references: Array.isArray(parsed.references) ? parsed.references : [],
              referenced_by: Array.isArray(parsed.referenced_by) ? parsed.referenced_by : [],
            },
          ];
        }
      } catch {
        // Metin olarak devam et
      }
    }

    // 2. Düz metin / Google Doküman içeriğini maddelere ve üstbilgiye ayrıştırma
    const lines = trimmed.split(/\r?\n/);
    let code = '';
    let rev = '00';
    let title = '';
    let ownerUnit = '';
    let revDate = '';

    // Dosya adından veya ilk satırlardan kod çıkarma (örn. PR-04_Satinalma_Proseduru.txt)
    const codeMatch = fileName.match(/([A-Z]{2,4}[-._/]\d+)/i) || trimmed.match(/(?:Doküman\s*No|Kod)\s*[:：]?\s*([A-Z0-9.\-_/]+)/i);
    if (codeMatch) {
      code = codeMatch[1].toUpperCase();
    } else {
      code = fileName.replace(/\.[^/.]+$/, '').toUpperCase();
    }

    const revMatch = trimmed.match(/(?:Rev|Revizyon)\s*(?:No)?\s*[:：]?\s*(\d+)/i);
    if (revMatch) {
      rev = revMatch[1].padStart(2, '0');
    }

    const dateMatch = trimmed.match(/(?:Revizyon\s*Tarihi|Yayın\s*Tarihi)\s*[:：]?\s*(\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2})/i);
    if (dateMatch) {
      revDate = dateMatch[1];
    }

    const unitMatch = trimmed.match(/(?:Hazırlayan|Sorumlu\s*Birim|Birim)\s*[:：]?\s*([^\n\r]+)/i);
    if (unitMatch) {
      ownerUnit = unitMatch[1].trim();
    }

    // Başlık bulma: ilk anlamlı büyük başlık
    for (const l of lines.slice(0, 10)) {
      const cleanLine = l.trim().replace(/^#+\s*/, '');
      if (cleanLine.length > 5 && !cleanLine.includes('Doküman No') && !cleanLine.includes('Revizyon')) {
        title = cleanLine;
        break;
      }
    }
    if (!title) {
      title = fileName.replace(/\.[^/.]+$/, '');
    }

    // Maddelere bölme (1.0 AMAÇ, 4.1 ..., vb.)
    const sections: {
      id: number;
      document_id: number;
      ordinal: number;
      clause_no: string | null;
      heading: string | null;
      heading_path: string | null;
      text: string;
    }[] = [];

    let currentClause: string | null = null;
    let currentHeading = 'Genel';
    let currentTextLines: string[] = [];
    let ordinal = 1;

    const clauseRegex = /^(?:#+\s*)?(\d+(?:\.\d+)*)\s+([^\n\r]+)/;

    for (const line of lines) {
      const match = line.trim().match(clauseRegex);
      if (match) {
        if (currentTextLines.length > 0) {
          sections.push({
            id: ordinal,
            document_id: 1,
            ordinal,
            clause_no: currentClause,
            heading: currentHeading,
            heading_path: currentHeading,
            text: currentTextLines.join('\n').trim(),
          });
          ordinal++;
          currentTextLines = [];
        }
        currentClause = match[1];
        currentHeading = match[0].trim().replace(/^#+\s*/, '');
      } else {
        if (line.trim()) {
          currentTextLines.push(line.trim());
        }
      }
    }

    if (currentTextLines.length > 0) {
      sections.push({
        id: ordinal,
        document_id: 1,
        ordinal,
        clause_no: currentClause,
        heading: currentHeading,
        heading_path: currentHeading,
        text: currentTextLines.join('\n').trim(),
      });
    }

    // Eğer hiç madde bulunamazsa tek bölüm olarak al
    if (sections.length === 0) {
      sections.push({
        id: 1,
        document_id: 1,
        ordinal: 1,
        clause_no: null,
        heading: 'İçerik',
        heading_path: 'İçerik',
        text: trimmed,
      });
    }

    return [
      {
        id: 1,
        code,
        code_key: codeKey(code),
        revision: rev,
        title,
        doc_type: this.detectDocType(code + ' ' + title),
        status: DocStatus.YURURLUKTE,
        revision_date: revDate || null,
        owner_unit: ownerUnit || null,
        summary: null,
        parse_warnings: [],
        sections,
        references: [],
        referenced_by: [],
      },
    ];
  }

  private static detectDocType(text: string): DocType {
    const t = text.toUpperCase();
    if (t.includes('KEK') || t.includes('EL KITAB')) return DocType.EL_KITABI;
    if (t.includes('POL') || t.includes('POLITIKA')) return DocType.POLITIKA;
    if (t.includes('PR-') || t.includes('PROSEDUR')) return DocType.PROSEDUR;
    if (t.includes('TL-') || t.includes('TALIMAT')) return DocType.TALIMAT;
    if (t.includes('YM-') || t.includes('YETKI') || t.includes('MATRIS')) return DocType.YETKI_MATRISI;
    if (t.includes('GT-') || t.includes('GOREV TANIM')) return DocType.GOREV_TANIMI;
    if (t.includes('FR-') || t.includes('FORM')) return DocType.FORM;
    if (t.includes('LS-') || t.includes('LISTE')) return DocType.LISTE;
    if (t.includes('PL-') || t.includes('PLAN')) return DocType.PLAN;
    return DocType.DIGER;
  }
}
