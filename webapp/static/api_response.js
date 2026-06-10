/** Shared fetch response parsing for Make and Video Lab. */

async function parseApiResponse(response) {
  const text = await response.text();
  if (!text) return { data: {}, raw: '' };
  try {
    return { data: JSON.parse(text), raw: text };
  } catch {
    return { data: { detail: text }, raw: text };
  }
}

function apiErrorDetail(data, status, fallback) {
  return (
    (typeof data.detail === 'string' && data.detail) ||
    (Array.isArray(data.detail) && data.detail[0]?.msg) ||
    (typeof data.error === 'string' && data.error) ||
    fallback + ' (HTTP ' + status + ')'
  );
}
