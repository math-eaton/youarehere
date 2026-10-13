<script>
	import MapView from '#lib/MapView.svelte';
	import { searchPlaces } from '#lib/nominatim.js';
	import { ancestorChain, chainToFeatureCollection, quadkey } from '#lib/tiles.js';

	const MAX_ZOOM = 22;
	const PMTILES_URL = 'https://latest.protomaps.com/v4.pmtiles';

	let query = $state('');
	let suggestions = $state([]);
	let searching = $state(false);
	/** @type {{ lon: number, lat: number, label: string } | null} */
	let point = $state(null);
	let zoom = $state(2);

	/** @type {AbortController | undefined} */
	let inFlight;

	// Nominatim's usage policy disallows search-as-you-type against the public
	// API — only fire on an explicit submit, never per keystroke.
	/** @param {SubmitEvent} event */
	async function onSearchSubmit(event) {
		event.preventDefault();
		if (!query.trim()) {
			suggestions = [];
			return;
		}
		inFlight?.abort();
		inFlight = new AbortController();
		searching = true;
		try {
			suggestions = await searchPlaces(query, { signal: inFlight.signal });
		} catch (err) {
			if (err.name !== 'AbortError') console.error(err);
		} finally {
			searching = false;
		}
	}

	function selectPlace(result) {
		point = { lon: Number(result.lon), lat: Number(result.lat), label: result.display_name };
		query = result.display_name;
		suggestions = [];
		zoom = 2;
	}

	let chain = $derived(point ? ancestorChain(point.lon, point.lat, MAX_ZOOM) : []);
	let highlightGeojson = $derived(chainToFeatureCollection(chain, zoom));
	let currentTile = $derived(chain.find((t) => t.z === zoom));
</script>

<div class="app">
	<MapView {point} {highlightGeojson} bind:zoom maxZoom={MAX_ZOOM} pmtilesUrl={PMTILES_URL} />

	<div class="panel search-panel">
		<form onsubmit={onSearchSubmit}>
			<input type="text" placeholder="Search a place…" bind:value={query} />
			<button type="submit" disabled={searching}>{searching ? 'searching…' : 'Search'}</button>
		</form>
		{#if suggestions.length}
			<ul class="suggestions">
				{#each suggestions as result (result.place_id)}
					<li>
						<button type="button" onclick={() => selectPlace(result)}>
							{result.display_name}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	{#if point}
		<div class="panel chain-panel">
			<label class="zoom-label" for="zoom-slider">
				zoom {zoom} of {MAX_ZOOM}
				{#if currentTile}
					— tile {currentTile.z}/{currentTile.x}/{currentTile.y} · quadkey {quadkey(
						currentTile.x,
						currentTile.y,
						currentTile.z
					)}
				{/if}
			</label>
			<input id="zoom-slider" type="range" min="0" max={MAX_ZOOM} step="1" bind:value={zoom} />

			<table>
				<thead>
					<tr>
						<th>z</th>
						<th>x</th>
						<th>y</th>
						<th>quadkey</th>
					</tr>
				</thead>
				<tbody>
					{#each chain as tile (tile.z)}
						<tr class:current={tile.z === zoom} onclick={() => (zoom = tile.z)}>
							<td>{tile.z}</td>
							<td>{tile.x}</td>
							<td>{tile.y}</td>
							<td>{quadkey(tile.x, tile.y, tile.z)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	:global(html, body) {
		margin: 0;
		height: 100%;
	}

	.app {
		position: relative;
		width: 100vw;
		height: 100vh;
		font-family:
			system-ui,
			-apple-system,
			sans-serif;
	}

	.panel {
		position: absolute;
		z-index: 1;
		background: rgba(255, 255, 255, 0.95);
		border-radius: 8px;
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
		padding: 0.75rem;
	}

	.search-panel {
		top: 1rem;
		left: 1rem;
		width: 320px;
	}

	.search-panel form {
		display: flex;
		gap: 0.4rem;
	}

	.search-panel input {
		flex: 1;
		min-width: 0;
		box-sizing: border-box;
		padding: 0.5rem;
		font-size: 1rem;
		border: 1px solid #ccc;
		border-radius: 6px;
	}

	.search-panel form button {
		padding: 0.5rem 0.75rem;
		font-size: 0.9rem;
		border: 1px solid #2563eb;
		background: #2563eb;
		color: white;
		border-radius: 6px;
		cursor: pointer;
		white-space: nowrap;
	}

	.search-panel form button:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.attribution {
		font-size: 0.7rem;
		color: #888;
		margin: 0.5rem 0 0;
	}

	.attribution a {
		color: inherit;
	}

	.suggestions {
		list-style: none;
		margin: 0.5rem 0 0;
		padding: 0;
		max-height: 240px;
		overflow-y: auto;
	}

	.suggestions li button {
		display: block;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		padding: 0.4rem;
		cursor: pointer;
		font-size: 0.85rem;
		border-radius: 4px;
	}

	.suggestions li button:hover {
		background: #eef2ff;
	}

	.chain-panel {
		top: 1rem;
		right: 1rem;
		max-width: 500px;
		font-size: 0.85rem;
	}

	.zoom-label {
		display: block;
		margin-bottom: 0.4rem;
	}

	.chain-panel input[type='range'] {
		width: 100%;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		margin-top: 0.5rem;
		font-variant-numeric: tabular-nums;
	}

	th,
	td {
		text-align: left;
		padding: 0.2rem 0.4rem;
	}

	tbody tr {
		cursor: pointer;
	}

	tbody tr:hover {
		background: #f3f4f6;
	}

	tbody tr.current {
		background: #ffe4d6;
		font-weight: 600;
	}
</style>
