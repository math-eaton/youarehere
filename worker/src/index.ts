import { DurableObject } from 'cloudflare:workers';

const NOMINATIM_BASE = 'https://nominatim.openstreetmap.org';
// Nominatim's usage policy caps requests at 1/sec, globally, regardless of who's
// asking — so this has to be a single shared gate, not a per-request delay.
const MIN_INTERVAL_MS = 1100;

/**
 * Durable Object singleton that serializes every outbound Nominatim request
 * through one queue, spaced by MIN_INTERVAL_MS, so concurrent requests from
 * multiple students never collectively exceed the 1 req/sec policy limit.
 */
export class NominatimGate extends DurableObject<Env> {
	private lastRequestAt = 0;
	private queue: Promise<void> = Promise.resolve();

	async fetchJSON(path: string, params: Record<string, string>): Promise<unknown> {
		this.queue = this.queue.then(() => this.throttle());
		await this.queue;

		const url = new URL(path, NOMINATIM_BASE);
		for (const [key, value] of Object.entries(params)) {
			url.searchParams.set(key, value);
		}

		const res = await fetch(url, {
			headers: {
				'User-Agent': this.env.NOMINATIM_USER_AGENT,
				Accept: 'application/json'
			}
		});
		if (!res.ok) {
			throw new Error(`Nominatim ${path} failed: ${res.status}`);
		}
		return res.json();
	}

	private async throttle(): Promise<void> {
		const wait = Math.max(0, this.lastRequestAt + MIN_INTERVAL_MS - Date.now());
		if (wait > 0) {
			await new Promise((resolve) => setTimeout(resolve, wait));
		}
		this.lastRequestAt = Date.now();
	}
}

function corsHeaders(env: Env): HeadersInit {
	return {
		'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN,
		'Access-Control-Allow-Methods': 'GET, OPTIONS',
		'Content-Type': 'application/json'
	};
}

function jsonError(env: Env, status: number, message: string): Response {
	return new Response(JSON.stringify({ error: message }), { status, headers: corsHeaders(env) });
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		if (request.method === 'OPTIONS') {
			return new Response(null, { headers: corsHeaders(env) });
		}
		if (request.method !== 'GET') {
			return jsonError(env, 405, 'Method not allowed');
		}

		const url = new URL(request.url);
		const gate = env.NOMINATIM_GATE.getByName('global');

		try {
			if (url.pathname === '/search') {
				const q = url.searchParams.get('q');
				if (!q) return jsonError(env, 400, 'Missing required "q" parameter');
				const limit = url.searchParams.get('limit') ?? '5';
				const results = await gate.fetchJSON('/search', { q, format: 'jsonv2', limit });
				return new Response(JSON.stringify(results), { headers: corsHeaders(env) });
			}

			if (url.pathname === '/reverse') {
				const lat = url.searchParams.get('lat');
				const lon = url.searchParams.get('lon');
				if (!lat || !lon) return jsonError(env, 400, 'Missing required "lat"/"lon" parameters');
				const result = await gate.fetchJSON('/reverse', { lat, lon, format: 'jsonv2' });
				return new Response(JSON.stringify(result), { headers: corsHeaders(env) });
			}

			return jsonError(env, 404, 'Not found');
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			return jsonError(env, 502, message);
		}
	}
} satisfies ExportedHandler<Env>;
