<script>
  import "maplibre-gl/dist/maplibre-gl.css";
  import { onMount, onDestroy, untrack } from "svelte";

  /** @typedef {{ lon: number, lat: number, label: string }} Point */

  let {
    point = null,
    highlightGeojson,
    zoom = $bindable(2),
    maxZoom = 15,
    pmtilesUrl,
    livePosition = $bindable(null),
    onDragEnd,
    // Caps the basemap source's own tile-fetch zoom below the viewport zoom,
    // so maplibre's built-in overzoom (stretch the coarser tile to fill the
    // finer viewport) kicks in deliberately — illustrates resolution loss.
    // null = uncapped/native. nativeDataMinZoom/MaxZoom are read-only, set
    // once the pmtiles archive's own header is known.
    dataMaxZoom = $bindable(null),
    nativeDataMinZoom = $bindable(null),
    nativeDataMaxZoom = $bindable(null),
    // Live, continuous camera zoom — read-only from the parent's side,
    // purely informational (zoom readout, data-cap ceiling). Never fed back
    // into a camera command, so scroll/pinch-zoom stays natural and smooth.
    viewportZoom = $bindable(0),
  } = $props();

  /** @type {HTMLDivElement} */
  let container;
  /** @type {import('maplibre-gl').Map | undefined} */
  let map;
  /** @type {typeof import('maplibre-gl') | undefined} */
  let maplibregl;
  /** @type {import('maplibre-gl').Marker | undefined} */
  let marker;
  let mapReady = $state(false);
  const BASEMAP_SOURCE_ID = "protomaps";
  // base source config (sans maxzoom) + generated layer specs, kept around
  // so the data-cap effect can remove/re-add the source with a new maxzoom
  /** @type {{ type: 'vector', url: string, attribution: string }} */
  let basemapSourceBase;
  /** @type {import('maplibre-gl').LayerSpecification[]} */
  let basemapLayerSpecs;

  const emptyFC = { type: "FeatureCollection", features: [] };

  onMount(() => {
    let protocol;
    let cancelled = false;

    (async () => {
      const [maplibreModule, workerUrlModule, pmtilesModule, basemapsModule] =
        await Promise.all([
          import("maplibre-gl"),
          // maplibre-gl locates its background worker via a sibling file at
          // runtime (import.meta.url); that breaks once a bundler merges
          // maplibre-gl.mjs into a shared chunk (production builds). Import
          // the worker as a proper Vite asset instead and point maplibre at
          // it explicitly below.
          import("maplibre-gl/dist/maplibre-gl-worker.mjs?url"),
          import("pmtiles"),
          import("@protomaps/basemaps"),
        ]);
      if (cancelled) return;

      maplibregl = maplibreModule;
      maplibregl.setWorkerUrl(workerUrlModule.default);
      protocol = new pmtilesModule.Protocol();
      maplibregl.addProtocol("pmtiles", protocol.tile);

      const { layers, namedFlavor } = basemapsModule;

      basemapSourceBase = {
        type: "vector",
        url: `pmtiles://${pmtilesUrl}`,
        attribution:
          '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a> contributors, <a href="https://protomaps.com">© Protomaps</a>',
      };
      basemapLayerSpecs = layers("protomaps", namedFlavor("light"));

      map = new maplibregl.Map({
        container,
        style: {
          version: 8,
          glyphs:
            "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
          sprite:
            "https://protomaps.github.io/basemaps-assets/sprites/v4/light",
          sources: {
            [BASEMAP_SOURCE_ID]: basemapSourceBase,
          },
          layers: basemapLayerSpecs,
        },
        center: [2, 1],
        zoom,
        maxZoom,
      });

      let scale = new maplibregl.ScaleControl({
        maxWidth: 100,
        unit: "metric",
      });
      map.addControl(scale), "bottom-left";

      map.addControl(
        new maplibregl.NavigationControl({
          showZoom: true,
          showCompass: true,
        }),
        "bottom-left",
      );

      // Continuous, read-only — no easing/snapping, so scroll/pinch-zoom
      // stays fully native. Feeds the zoom readout and the data-cap ceiling.
      viewportZoom = zoom;
      map.on("zoom", () => {
        viewportZoom = map.getZoom();
      });

      map.on("load", () => {
        map.addSource("tile-chain", {
          type: "geojson",
          data: highlightGeojson ?? emptyFC,
        });
        map.addLayer({
          id: "tile-chain-fill",
          type: "fill",
          source: "tile-chain",
          paint: {
            "fill-color": ["case", ["get", "current"], "#FF7F41", "#6CADDF"],
            "fill-opacity": ["case", ["get", "current"], 0.125, 0.0],
          },
        });
        map.addLayer({
          id: "tile-chain-line",
          type: "line",
          source: "tile-chain",
          paint: {
            "line-color": ["case", ["get", "current"], "#000d74", "#FF7F41"],
            "line-width": ["case", ["get", "current"], 2, 1.5],
          },
        });
        // "zN" reference label at each parent tile's NW corner..the
        // current tile is deliberately unlabeled (see chainToFeatureCollection).
        map.addLayer({
          id: "tile-chain-label",
          type: "symbol",
          source: "tile-chain",
          filter: ["has", "label"],
          layout: {
            "text-field": ["get", "label"],
            "text-font": ["Courier New Bold", "Arial Unicode MS Bold"],
            "text-size": 12,
            "text-padding": 12,
            "text-anchor": "top-left",
            "text-offset": [0.5, 0.5],
            "text-justify": "auto",
            "text-allow-overlap": false,
            "text-ignore-placement": false,
          },
          paint: {
            "text-color": "#FF7F41",
            "text-halo-color": "#ffffff",
            "text-halo-width": 0.85,
          },
        });

        // map.showTileBoundaries = true;

        // pmtiles resolves the archive's real min/maxzoom from its header
        // once the source loads — surface it so the parent can size a
        // "cap the data zoom" slider against the archive's actual range.
        const basemapSource = map.getSource(BASEMAP_SOURCE_ID);
        nativeDataMinZoom = basemapSource?.minzoom ?? 0;
        nativeDataMaxZoom = basemapSource?.maxzoom ?? maxZoom;

        mapReady = true;
      });
    })();

    return () => {
      cancelled = true;
    };
  });

  onDestroy(() => {
    marker?.remove();
    map?.remove();
  });

  $effect(() => {
    if (!mapReady) return;
    map.getSource("tile-chain")?.setData(highlightGeojson ?? emptyFC);
  });

  // Marker sync + fly-to-new-place. Re-centers the camera only when `point`
  // is an actually different location (a search pick, the initial
  // bootstrap) — not when it's just a drag-end relabel at the same coords
  // the marker is already sitting at. Otherwise every reverse-geocode
  // resolving after a drag would yank the camera back to the chain-panel's
  // zoom, hijacking whatever scroll-zoom level you were looking at.
  $effect(() => {
    if (!mapReady || !maplibregl || !map || !point) return;

    const current = marker?.getLngLat();
    const isNewPlace =
      !current ||
      Math.abs(current.lng - point.lon) > 1e-9 ||
      Math.abs(current.lat - point.lat) > 1e-9;

    if (marker) {
      marker.setLngLat([point.lon, point.lat]);
    } else {
      const m = new maplibregl.Marker({ color: "#000d74", draggable: true })
        .setLngLat([point.lon, point.lat])
        .addTo(map);
      m.on("drag", () => {
        const { lng, lat } = m.getLngLat();
        livePosition = { lon: lng, lat };
      });
      m.on("dragend", () => {
        const { lng, lat } = m.getLngLat();
        onDragEnd?.({ lon: lng, lat });
      });
      marker = m;
    }

    if (isNewPlace) {
      map.easeTo({ center: [point.lon, point.lat], zoom, duration: 400 });
    }
  });

  // Chain-panel slider / table-row click → camera: zoom back to the pin at
  // the chosen level. Reads `point` untracked so this effect depends only
  // on `zoom` — dragging the pin (which changes `point`, not `zoom`) never
  // triggers it, and scroll-zoom (which touches neither) is left alone.
  $effect(() => {
    if (!mapReady || !map) return;
    void zoom;
    /** @type {[number, number] | undefined} */
    const center = untrack(() => (point ? [point.lon, point.lat] : undefined));
    map.easeTo({ ...(center ? { center } : {}), zoom, duration: 400 });
  });

  // maplibre has no setMaxzoom() — changing a vector source's fetch-zoom
  // ceiling means removing + re-adding the source (and every layer that
  // references it). Tiles above dataMaxZoom are then served from the
  // dataMaxZoom tile, overzoomed (maplibre's built-in behavior) to fill
  // the viewport, rather than fetching the native finer tile.
  $effect(() => {
    if (!mapReady || !map || dataMaxZoom == null) return;
    const source = map.getSource(BASEMAP_SOURCE_ID);
    if (!source || source.maxzoom === dataMaxZoom) return;

    for (const spec of basemapLayerSpecs) {
      if (map.getLayer(spec.id)) map.removeLayer(spec.id);
    }
    map.removeSource(BASEMAP_SOURCE_ID);
    map.addSource(BASEMAP_SOURCE_ID, {
      ...basemapSourceBase,
      maxzoom: dataMaxZoom,
    });
    const beforeId = map.getLayer("tile-chain-fill")
      ? "tile-chain-fill"
      : undefined;
    for (const spec of basemapLayerSpecs) {
      map.addLayer(spec, beforeId);
    }
  });
</script>

<div bind:this={container} class="map"></div>

<style>
  .map {
    position: absolute;
    inset: 0;
  }
</style>
