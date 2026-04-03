export const API_BASE = window.location.origin;

export function buildApiUrl(path, params = {}) {
    const url = new URL(path, API_BASE);
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            url.searchParams.set(key, value);
        }
    });
    return url.toString();
}

export async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    return { response, data };
}
