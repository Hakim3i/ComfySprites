/** Export Lab — shared constants and helpers. */

const EXPORT_LAB_VIDEO_LIMIT = 100;
const EXPORT_LAB_COMFYUI_LAB = 'export';
const EXPORT_THUMB_WIDTH = 96;
const EXPORT_MAX_FRAMES = 600;

const EXPORT_FORM_DEFAULTS = {
  columns: '8',
  spacing: '0',
  background: 'transparent', // 'transparent' | 'solid'
  background_color: '#00000000',
  solid_color: '#222222',
  format: 'png', // 'png' | 'jpeg' | 'webp'
  filename: 'spritesheet',
  export_type: 'sheet', // 'sheet' | 'pictures'
  rmbg_background: 'transparent', // 'transparent' | 'solid'
  rmbg_color: '#000000',
};

const EXPORT_FORMAT_MIME = {
  png: 'image/png',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
};

const EXPORT_FORMAT_EXT = {
  png: 'png',
  jpeg: 'jpg',
  webp: 'webp',
};

function exportFormatMime(format) {
  return EXPORT_FORMAT_MIME[format] || 'image/png';
}

function exportFormatExt(format) {
  return EXPORT_FORMAT_EXT[format] || 'png';
}

function exportFormatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function exportSanitizeFilename(name, fallback) {
  const cleaned = String(name || '')
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return cleaned || fallback;
}

function exportPad(num, width) {
  return String(num).padStart(width, '0');
}
