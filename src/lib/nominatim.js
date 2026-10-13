// Talks to our own Cloudflare Worker proxy (see worker/), never Nominatim
// directly — the proxy sets an identifying User-Agent and serializes requests
// to respect Nominatim's 1 req/sec usage policy. See worker/README.md.
const API_BASE = import.meta.env.VITE_GEOCODE_API_URL ?? 'http://localhost:8787';

/**
 * Forward-geocode a free-text place name into candidate results.
 * Call only on an explicit user action (submit) — never per keystroke.
 * @param {string} query
 * @param {{ limit?: number, signal?: AbortSignal }} [options]
 * @returns {Promise<Array<{ display_name: string, lat: string, lon: string, place_id: number }>>}
 */
export async function searchPlaces(query, { limit = 5, signal } = {}) {
	const trimmed = query.trim();
	if (!trimmed) return [];

	const url = new URL('/search', API_BASE);
	url.searchParams.set('q', trimmed);
	url.searchParams.set('limit', String(limit));

	const res = await fetch(url, { signal });
	if (!res.ok) throw new Error(`Geocode search failed: ${res.status}`);
	return res.json();
}

/**
 * Reverse-geocode a coordinate into a place name.
 * @param {number} lat
 * @param {number} lon
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<{ display_name: string, lat: string, lon: string }>}
 */
export async function reverseGeocode(lat, lon, { signal } = {}) {
	const url = new URL('/reverse', API_BASE);
	url.searchParams.set('lat', String(lat));
	url.searchParams.set('lon', String(lon));

	const res = await fetch(url, { signal });
	if (!res.ok) throw new Error(`Reverse geocode failed: ${res.status}`);
	return res.json();
}
