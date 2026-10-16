// Slippy-map (XYZ) tile math .. see https://www.analyze.earth/posts/web-mercator-tiles/
// Each zoom level recursively quarters the previous one: tile (x, y) at zoom z
// contains tiles (2x..2x+1, 2y..2y+1) at zoom z+1.

/** @returns {{ x: number, y: number }} the tile containing [lon, lat] at zoom z */
export function lonLatToTile(lon, lat, z) {
	const n = 2 ** z;
	const latRad = (lat * Math.PI) / 180;
	const x = Math.floor(((lon + 180) / 360) * n);
	const y = Math.floor(((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n);
	return { x: clamp(x, 0, n - 1), y: clamp(y, 0, n - 1) };
}

function clamp(v, min, max) {
	return Math.min(Math.max(v, min), max);
}

function tileYToLat(y, n) {
	const yFrac = y / n;
	return (Math.atan(Math.sinh(Math.PI * (1 - 2 * yFrac))) * 180) / Math.PI;
}

/** @returns {[number, number, number, number]} [lonMin, latMin, lonMax, latMax] */
export function tileBounds(x, y, z) {
	const n = 2 ** z;
	return [(x / n) * 360 - 180, tileYToLat(y + 1, n), ((x + 1) / n) * 360 - 180, tileYToLat(y, n)];
}

/** @returns {[number, number][]} a closed ring tracing the tile's edge, lon/lat pairs */
export function tilePolygonRing(x, y, z) {
	const [lonMin, latMin, lonMax, latMax] = tileBounds(x, y, z);
	return [
		[lonMin, latMax],
		[lonMax, latMax],
		[lonMax, latMin],
		[lonMin, latMin],
		[lonMin, latMax]
	];
}

/** The quadtree key for a tile: one base-4 digit per zoom level, root first. */
export function quadkey(x, y, z) {
	let qk = '';
	for (let i = z; i > 0; i--) {
		const mask = 1 << (i - 1);
		let digit = 0;
		if ((x & mask) !== 0) digit += 1;
		if ((y & mask) !== 0) digit += 2;
		qk += digit;
	}
	return qk;
}

/**
 * The full z0..maxZoom ancestor chain of tiles containing a point .. the
 * recursive "which quadrant, then which quadrant of that quadrant" path
 * the blog post walks through.
 * @returns {{ z: number, x: number, y: number }[]}
 */
export function ancestorChain(lon, lat, maxZoom) {
	const chain = [];
	for (let z = 0; z <= maxZoom; z++) {
		chain.push({ z, ...lonLatToTile(lon, lat, z) });
	}
	return chain;
}

/**
 * The chain's tiles from z0 up to `currentZoom`, as a GeoJSON FeatureCollection
 * of nested polygons .. the tile at `currentZoom` is flagged `current` so the
 * map style can draw it emphasized. Each non-current ("parent") tile also
 * gets a companion Point feature at its NW corner, tagged `label`, for a
 * "zN" reference label .. the current tile is skipped since the active zoom
 * is already shown elsewhere in the UI.
 */
export function chainToFeatureCollection(chain, currentZoom) {
	const ancestry = chain.filter((tile) => tile.z <= currentZoom);

	const polygons = ancestry.map((tile) => ({
		type: 'Feature',
		properties: { z: tile.z, x: tile.x, y: tile.y, current: tile.z === currentZoom },
		geometry: { type: 'Polygon', coordinates: [tilePolygonRing(tile.x, tile.y, tile.z)] }
	}));

	const labels = ancestry
		// .filter((tile) => tile.z !== currentZoom)
		.map((tile) => {
			const [lonMin, , , latMax] = tileBounds(tile.x, tile.y, tile.z);
			return {
				type: 'Feature',
				properties: { z: tile.z, label: `Z${tile.z}` },
				geometry: { type: 'Point', coordinates: [lonMin, latMax] }
			};
		});

	return { type: 'FeatureCollection', features: [...polygons, ...labels] };
}
