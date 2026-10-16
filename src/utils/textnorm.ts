/**
 * Türkçe metin normalizasyonu ve alıntı doğrulama.
 * Python backend/kys/textnorm.py ve backend/kys/query/retrieval.py mantığının TypeScript portu.
 */

const TR_MAP: Record<string, string> = {
  'İ': 'i', 'I': 'i', 'ı': 'i',
  'Ş': 's', 'ş': 's',
  'Ğ': 'g', 'ğ': 'g',
  'Ü': 'u', 'ü': 'u',
  'Ö': 'o', 'ö': 'o',
  'Ç': 'c', 'ç': 'c',
  'Â': 'a', 'â': 'a',
  'Î': 'i', 'î': 'i',
  'Û': 'u', 'û': 'u',
};

const QUOTE_MAP: Record<string, string> = {
  '’': "'", '‘': "'", '“': '"', '”': '"', '–': '-', '—': '-', '\u00A0': ' ',
};

export function foldChars(text: string): string {
  let result = '';
  for (const char of text) {
    if (QUOTE_MAP[char]) {
      result += QUOTE_MAP[char];
    } else if (TR_MAP[char]) {
      result += TR_MAP[char];
    } else {
      result += char.toLowerCase();
    }
  }
  return result;
}

export function fold(text: string): string {
  if (!text) return '';
  // Normalize unicode (NFC), map quotes & Turkish characters, collapse whitespace
  const normalized = text.normalize('NFC');
  const folded = foldChars(normalized);
  return folded.replace(/\s+/g, ' ').trim();
}

export function quoteKey(text: string): string {
  // Katla, noktalama ve tablo ayıracı farklarını yok say
  const folded = fold(text);
  const stripped = folded.replace(/[|*_#`"'.,;:()[\]-]/g, ' ');
  return stripped.replace(/\s+/g, ' ').trim();
}

/**
 * Alıntı kaynak metinde (biçim farkları dışında) birebir geçiyor mu?
 * LLM çıktısındaki her kanıt alıntısı bununla doğrulanır (CLAUDE.md değişmez 1).
 * Çok kısa alıntılar kanıt sayılmaz (varsayılan minLen = 12).
 */
export function verifyQuote(quote: string, source: string, minLen = 12): boolean {
  if (!quote || !source) return false;
  const q = quoteKey(quote);
  if (q.length < minLen) {
    return false;
  }
  return quoteKey(source).includes(q);
}

/**
 * Doküman kodunu normalize edilmiş anahtara çevirir: PR-04 -> pr04 / pr4
 */
export function codeKey(code: string): string {
  return fold(code).replace(/[^a-z0-9]/g, '');
}

export const STOPWORDS = new Set([
  've', 'veya', 'ile', 'bir', 'bu', 'su', 'icin', 'mi', 'mu', 'ne', 'nedir', 'nasil', 'hangi', 'kim',
  'kimdir', 'olan', 'olarak', 'gibi', 'da', 'de', 'ki', 'var', 'yok', 'midir', 'ise', 'daha', 'en', 'her',
  'tum', 'hangisi', 'neler', 'nelerdir', 'kac', 'gore', 'kadar', 'sonra', 'once', 'uzere', 'yapilir',
  'dokuman', 'dokumanda', 'dokumanlarda', 'olur', 'eder', 'edilir',
]);

/**
 * Türkçe ekleri kabaca budar: uzun kelimelerin ilk 6 harfi (trigram alt dizge eşleşmesi için)
 */
export function extractTerms(question: string): string[] {
  const out: string[] = [];
  const words = fold(question).replace(/"/g, ' ').split(/\s+/);

  for (let w of words) {
    w = w.replace(/^[.,;:!?()'"]+|[.,;:!?()'"]+$/g, '');
    if (w.length < 3 || STOPWORDS.has(w)) {
      continue;
    }
    if (w.length > 7) {
      w = w.slice(0, 6);
    }
    if (!out.includes(w)) {
      out.push(w);
    }
  }
  return out;
}

/**
 * Bilinen doküman kodu kalıplarını kontrol eder (PR, TL, FR, LS, PL, YM, KEK, GT, vb.)
 */
export function looksLikeDocCode(code: string): boolean {
  const c = code.trim().toUpperCase();
  const knownPrefixes = ['PR', 'TL', 'FR', 'LS', 'PL', 'YM', 'KEK', 'GT', 'POL', 'PRK', 'DK'];
  const parts = c.split(/[-._/]/);
  if (parts.length >= 2 && knownPrefixes.includes(parts[0])) {
    return true;
  }
  return /^[A-Z]{2,4}[-._/]\d+/.test(c);
}
