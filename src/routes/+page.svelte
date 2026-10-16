<script>
  import { onMount } from "svelte";
  import MapView from "#lib/MapView.svelte";
  import { searchPlaces, reverseGeocode } from "#lib/nominatim.js";
  import {
    ancestorChain,
    chainToFeatureCollection,
    quadkey,
  } from "#lib/tiles.js";

  const MAX_ZOOM = 22;
  const DEFAULT_ADDRESS =
    "Lamont-Doherty Earth Observatory, Ludlow Lane, Sneden's Landing, Palisades, Tappan, Town of Orangetown, Rockland County, New York, 10964, United States";
  // used only if the default-address lookup above fails (e.g. offline)
  const DEFAULT_FALLBACK = { lon: -73.90582853328229, lat: 41.00595224485467 };
  let query = $state("");
  let suggestions = $state([]);
  let searching = $state(false);
  /** @type {{ lon: number, lat: number, label: string } | null} */
  let point = $state(null);
  // mirrors `point`, but updates continuously while the pin is being dragged
  // (before the drag-end reverse-geocode resolves) so the tile highlight
  // tracks the pin in real time
  /** @type {{ lon: number, lat: number } | null} */
  let livePosition = $state(null);
  let zoom = $state(2);
  let reverseGeocoding = $state(false);
  // live camera zoom, continuous — see MapView's `viewportZoom` bindable
  let viewportZoom = $state(2);

  // Caps the basemap's own tile-fetch zoom below the viewport zoom, so the
  // coarser tile renders overzoomed (stretched) instead of the native finer
  // one — illustrates how much detail a given zoom level actually carries.
  // null = uncapped/native (MapView applies no override at all).
  /** @type {number | null} */
  let dataMaxZoom = $state(null);
  /** @type {number | null} */
  let nativeDataMinZoom = $state(null);
  /** @type {number | null} */
  let nativeDataMaxZoom = $state(null);
  // last value the user explicitly dragged to, pre-ceiling-clamp; null means
  // "no explicit choice yet — follow the live ceiling" (see sliderValue below)
  /** @type {number | null} */
  let dataMaxZoomDisplay = $state(null);

  // You can't overzoom data to a finer level than the viewport is actually
  // showing — e.g. requesting z15 data while the camera sits at z0 has no
  // visible effect. So the cap control's own ceiling tracks the live
  // viewport zoom, not the archive's native max.
  let dataZoomCeiling = $derived(
    nativeDataMaxZoom == null
      ? null
      : Math.min(nativeDataMaxZoom, Math.floor(viewportZoom)),
  );
  let sliderValue = $derived(
    dataZoomCeiling == null
      ? 0
      : dataMaxZoomDisplay == null
        ? dataZoomCeiling
        : Math.min(dataMaxZoomDisplay, dataZoomCeiling),
  );

  /** @type {AbortController | undefined} */
  let inFlight;
  /** @type {AbortController | undefined} */
  let reverseInFlight;

  /** @param {{ lon: number, lat: number, label: string }} place */
  function commitPoint(place) {
    point = place;
    livePosition = { lon: place.lon, lat: place.lat };
  }

  onMount(async () => {
    try {
      const [result] = await searchPlaces(DEFAULT_ADDRESS, { limit: 1 });
      if (result) {
        commitPoint({
          lon: Number(result.lon),
          lat: Number(result.lat),
          label: result.display_name,
        });
        query = result.display_name;
        return;
      }
    } catch (err) {
      console.error(err);
    }
    const label = "Lamont-Doherty Earth Observatory";
    commitPoint({ ...DEFAULT_FALLBACK, label });
    query = label;
  });

  // Only reverse-geocode once the pin is dropped — not on every drag tick.
  /** @param {{ lon: number, lat: number }} pos */
  async function handleDragEnd(pos) {
    reverseInFlight?.abort();
    reverseInFlight = new AbortController();
    reverseGeocoding = true;
    try {
      const result = await reverseGeocode(pos.lat, pos.lon, {
        signal: reverseInFlight.signal,
      });
      commitPoint({ ...pos, label: result.display_name });
      query = result.display_name;
    } catch (err) {
      if (err.name !== "AbortError") {
        console.error(err);
        commitPoint({
          ...pos,
          label: `${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)}`,
        });
      }
    } finally {
      reverseGeocoding = false;
    }
  }

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
      if (err.name !== "AbortError") console.error(err);
    } finally {
      searching = false;
    }
  }

  function selectPlace(result) {
    commitPoint({
      lon: Number(result.lon),
      lat: Number(result.lat),
      label: result.display_name,
    });
    query = result.display_name;
    suggestions = [];
    zoom = 2;
  }

  let chain = $derived.by(() => {
    const pos = livePosition;
    return pos ? ancestorChain(pos.lon, pos.lat, MAX_ZOOM) : [];
  });
  let highlightGeojson = $derived(chainToFeatureCollection(chain, zoom));
  let currentTile = $derived(chain.find((t) => t.z === zoom));
</script>

<div class="app">
  <div class="map-area">
    <MapView
      {point}
      {highlightGeojson}
      bind:zoom
      bind:livePosition
      bind:dataMaxZoom
      bind:nativeDataMinZoom
      bind:nativeDataMaxZoom
      bind:viewportZoom
      maxZoom={MAX_ZOOM}
      onDragEnd={handleDragEnd}
    />

    <div class="panel search-panel">
      <form onsubmit={onSearchSubmit}>
        <input type="text" placeholder="Search a place…" bind:value={query} />
        <button type="submit" disabled={searching}
          >{searching ? "searching…" : "Search"}</button
        >
      </form>
      {#if point}
        <p class="pin-label">
          {point.label}
          {#if reverseGeocoding}
            <span class="hint">· updating…</span>
          {/if}
        </p>
      {/if}
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

    <div class="panel zoom-tooltip">current zoom {viewportZoom.toFixed(1)}</div>
  </div>

  {#if point}
    <div class="panel chain-panel">
      <label class="zoom-label" for="zoom-slider">
        pinned zoom {zoom} of {MAX_ZOOM}
        {#if currentTile}
        | tile {currentTile.z}/{currentTile.x}/{currentTile.y} | quadkey {quadkey(
            currentTile.x,
            currentTile.y,
            currentTile.z,
          )}
        {/if}
      </label>
      <input
        id="zoom-slider"
        type="range"
        min="0"
        max={MAX_ZOOM}
        step="1"
        color="#1D4F91"
        bind:value={zoom}
      />

      {#if dataZoomCeiling != null}
        <label class="zoom-label data-zoom-label" for="data-zoom-slider">
          draw tile zoom: z{sliderValue}{dataMaxZoom == null ? " (default)" : ""}
          {#if dataMaxZoom != null && dataMaxZoom < Math.floor(viewportZoom)}
            <span class="hint"
              >| z{dataMaxZoom} map data viewed at z{Math.floor(viewportZoom)}</span
            >
          {/if}
        </label>
        <div class="data-zoom-row">
          <input
            id="data-zoom-slider"
            type="range"
            min={nativeDataMinZoom}
            max={dataZoomCeiling}
            step="1"
            value={sliderValue}
            oninput={(e) => (dataMaxZoomDisplay = Number(e.currentTarget.value))}
            onchange={() =>
              (dataMaxZoom = sliderValue >= dataZoomCeiling ? null : sliderValue)}
          />
          <button
            type="button"
            class="reset-button"
            disabled={dataMaxZoom == null}
            onclick={() => {
              dataMaxZoomDisplay = null;
              dataMaxZoom = null;
            }}
          >
            reset
          </button>
        </div>
      {/if}

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
    display: flex;
    flex-direction: column;
    width: 100vw;
    height: 100vh;
    font-family: Helvetica, Arial, sans-serif;
  }

  .map-area {
    position: relative;
    flex: 1;
    min-height: 0;
  }

  .panel {
    position: absolute;
    z-index: 1;
    background: rgba(255, 255, 255, 0.95);
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
  }

  .search-panel form button {
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
    border: 1px solid #1d4f91;
    background: #1d4f91;
    color: white;
    cursor: pointer;
    white-space: nowrap;
  }

  .search-panel form button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .pin-label {
    font-size: 0.8rem;
    margin: 0.5rem 0 0;
    overflow-wrap: break-word;
  }

  .hint {
    color: #888;
    font-style: italic;
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

  .zoom-tooltip {
    bottom: 0;
    margin-bottom: 10px;
    margin-left: 10px;
    position: absolute;
    /* clear maplibre's own bottom-left compass/zoom control */
    left: 120px;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    padding: 0.35rem 0.5rem;
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

  .chain-panel input[type="range"] {
    width: 100%;
    accent-color: #1d4f91;
  }

  .data-zoom-label {
    margin-top: 0.6rem;
  }

  .data-zoom-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .data-zoom-row input[type="range"] {
    flex: 1;
  }

  .reset-button {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    border: 1px solid #1d4f91;
    background: white;
    color: #1d4f91;
    cursor: pointer;
    white-space: nowrap;
  }

  .reset-button:disabled {
    opacity: 0.4;
    cursor: default;
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
    background: #C4D8E2;
    font-weight: 600;
  }

  /* Narrow viewports: the chain-panel's table+sliders no longer fit as a
     floating overlay without covering the map, so it drops into normal
     flow as a footer (1/3 height) and the map keeps the remaining 2/3. */
  @media (max-width: 760px) {
    .map-area {
      flex: 2;
    }

    .chain-panel {
      position: static;
      flex: 1;
      min-height: 0;
      width: 100%;
      max-width: none;
      box-sizing: border-box;
      overflow-y: auto;
    }
  }
</style>
