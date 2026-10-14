<script>
  import "maplibre-gl/dist/maplibre-gl.css";
  import { onMount, onDestroy } from "svelte";

  /** @typedef {{ lon: number, lat: number, label: string }} Point */

  let {
    point = null,
    highlightGeojson,
    zoom = $bindable(2),
    maxZoom = 14,
    pmtilesUrl,
    livePosition = $bindable(null),
    onDragEnd,
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
  let programmaticMove = false;

  const emptyFC = { type: "FeatureCollection", features: [] };

  onMount(() => {
    let protocol;
    let cancelled = false;

    (async () => {
      const [maplibreModule, pmtilesModule, basemapsModule] = await Promise.all(
        [
          import("maplibre-gl"),
          import("pmtiles"),
          import("@protomaps/basemaps"),
        ],
      );
      if (cancelled) return;

      maplibregl = maplibreModule;
      protocol = new pmtilesModule.Protocol();
      maplibregl.addProtocol("pmtiles", protocol.tile);

      const { layers, namedFlavor } = basemapsModule;

      map = new maplibregl.Map({
        container,
        style: {
          version: 8,
          glyphs:
            "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
          sprite:
            "https://protomaps.github.io/basemaps-assets/sprites/v4/light",
          sources: {
            protomaps: {
              type: "vector",
              url: `pmtiles://${pmtilesUrl}`,
              attribution:
                '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a> contributors, <a href="https://protomaps.com">© Protomaps</a>',
            },
          },
          layers: layers("protomaps", namedFlavor("light")),
        },
        center: [2, 1],
        zoom,
        maxZoom,
      });

      map.addControl(
        new maplibregl.NavigationControl({
          showZoom: false, 
          showCompass: true,
        }),
        "bottom-left",
      );

      // map.showTileBoundaries = true;


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
            "fill-color": ["case", ["get", "current"], "#000d74", "#6CADDF"],
            "fill-opacity": ["case", ["get", "current"], 0.085, 0.04],
          },
        });
        map.addLayer({
          id: "tile-chain-line",
          type: "line",
          source: "tile-chain",
          paint: {
            "line-color": ["case", ["get", "current"], "#000d74", "#75AADB"],
            "line-width": ["case", ["get", "current"], 2, 1],
          },
        });
        mapReady = true;
      });

      map.on("zoomend", () => {
        if (programmaticMove) {
          programmaticMove = false;
          return;
        }
        zoom = Math.round(map.getZoom());
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

  $effect(() => {
    if (!mapReady || !maplibregl || !map) return;
    // re-run when `point` or `zoom` changes
    void point;
    void zoom;

    if (point) {
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
    }

    programmaticMove = true;
    map.easeTo({
      center: point ? [point.lon, point.lat] : map.getCenter(),
      zoom,
      duration: 400,
    });
  });
</script>

<div bind:this={container} class="map"></div>

<style>
  .map {
    position: absolute;
    inset: 0;
  }
</style>
