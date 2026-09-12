"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Carte à tuiles OpenStreetMap, écrite à la main.
 *
 * Pourquoi pas une librairie de cartographie : le budget est d'un premier
 * rendu utile en moins de deux secondes en 4G, et une librairie complète pèse
 * plus lourd que tout le reste de l'application réunie. Ce qu'il nous faut
 * tient en une projection Web Mercator, une grille de `<img>` et un
 * glisser-déposer.
 *
 * Attribution ODbL obligatoire — elle est affichée en bas à droite et ne doit
 * jamais disparaître (cf. PROJET.md §6, licence OSM).
 */

const TILE_SIZE = 256;
const MIN_ZOOM = 5;
const MAX_ZOOM = 17;
/** Au-delà, c'est un tap, pas un glissement. */
const DRAG_THRESHOLD_PX = 6;
/** Appui long = ajout d'un spot. */
const LONG_PRESS_MS = 550;

export interface MapMarker {
  id: number | string;
  lat: number;
  lon: number;
  label: string;
  /** Teinte l'épingle : un favori se repère sans lire. */
  highlight?: boolean;
  onSelect?: () => void;
}

interface TileMapProps {
  center: { lat: number; lon: number };
  zoom?: number;
  markers?: MapMarker[];
  /** Appui long sur la carte : les coordonnées du point touché. */
  onLongPress?: (position: { lat: number; lon: number }) => void;
  className?: string;
}

// ── Projection Web Mercator ────────────────────────────────────────────────

function lonToX(lon: number, zoom: number): number {
  return ((lon + 180) / 360) * Math.pow(2, zoom) * TILE_SIZE;
}

function latToY(lat: number, zoom: number): number {
  const radians = (lat * Math.PI) / 180;
  return (
    ((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) *
    Math.pow(2, zoom) *
    TILE_SIZE
  );
}

function xToLon(x: number, zoom: number): number {
  return (x / (Math.pow(2, zoom) * TILE_SIZE)) * 360 - 180;
}

function yToLat(y: number, zoom: number): number {
  const n = Math.PI - (2 * Math.PI * y) / (Math.pow(2, zoom) * TILE_SIZE);
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

export function TileMap({
  center,
  zoom: initialZoom = 12,
  markers = [],
  onLongPress,
  className = "",
}: TileMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 360, height: 360 });
  const [zoom, setZoom] = useState(initialZoom);
  // Centre de la vue, en pixels monde au zoom courant.
  const [focus, setFocus] = useState(center);

  const drag = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originLat: number;
    originLon: number;
    moved: boolean;
  } | null>(null);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Le centre est piloté par le parent (géoloc, domicile) mais déplaçable au
  // doigt : c'est un état dérivé d'une prop. React recommande de l'ajuster
  // pendant le rendu plutôt que dans un effet, qui provoquerait un rendu de
  // plus à chaque changement de position.
  const [lastCenter, setLastCenter] = useState(center);
  if (center.lat !== lastCenter.lat || center.lon !== lastCenter.lon) {
    setLastCenter(center);
    setFocus(center);
  }

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const update = () =>
      setSize({ width: element.clientWidth, height: element.clientHeight });
    update();

    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const centerX = lonToX(focus.lon, zoom);
  const centerY = latToY(focus.lat, zoom);
  const originX = centerX - size.width / 2;
  const originY = centerY - size.height / 2;

  const tiles: { key: string; x: number; y: number; left: number; top: number }[] =
    [];
  const maxTile = Math.pow(2, zoom);
  const firstX = Math.floor(originX / TILE_SIZE);
  const firstY = Math.floor(originY / TILE_SIZE);
  const countX = Math.ceil(size.width / TILE_SIZE) + 1;
  const countY = Math.ceil(size.height / TILE_SIZE) + 1;

  for (let ix = 0; ix < countX; ix += 1) {
    for (let iy = 0; iy < countY; iy += 1) {
      const tileX = firstX + ix;
      const tileY = firstY + iy;
      if (tileY < 0 || tileY >= maxTile) continue;
      tiles.push({
        key: `${zoom}/${tileX}/${tileY}`,
        x: ((tileX % maxTile) + maxTile) % maxTile,
        y: tileY,
        left: tileX * TILE_SIZE - originX,
        top: tileY * TILE_SIZE - originY,
      });
    }
  }

  const clearLongPress = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  }, []);

  const positionFromClient = useCallback(
    (clientX: number, clientY: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return null;
      const worldX = originX + (clientX - rect.left);
      const worldY = originY + (clientY - rect.top);
      return { lat: yToLat(worldY, zoom), lon: xToLon(worldX, zoom) };
    },
    [originX, originY, zoom],
  );

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    (event.target as Element).setPointerCapture?.(event.pointerId);
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originLat: focus.lat,
      originLon: focus.lon,
      moved: false,
    };

    if (onLongPress) {
      const { clientX, clientY } = event;
      longPressTimer.current = setTimeout(() => {
        const position = positionFromClient(clientX, clientY);
        if (position && drag.current && !drag.current.moved) {
          onLongPress(position);
        }
      }, LONG_PRESS_MS);
    }
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;

    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;

    if (!current.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
      current.moved = true;
      clearLongPress();
    }
    if (!current.moved) return;

    const startX = lonToX(current.originLon, zoom);
    const startY = latToY(current.originLat, zoom);
    setFocus({
      lat: yToLat(startY - dy, zoom),
      lon: xToLon(startX - dx, zoom),
    });
  };

  const endDrag = () => {
    clearLongPress();
    drag.current = null;
  };

  return (
    <div
      className={`relative overflow-hidden rounded-card border border-line bg-soft ${className}`}
    >
      <div
        ref={containerRef}
        className="h-full w-full touch-none select-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={endDrag}
      >
        {tiles.map((tile) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={tile.key}
            src={`https://tile.openstreetmap.org/${zoom}/${tile.x}/${tile.y}.png`}
            alt=""
            width={TILE_SIZE}
            height={TILE_SIZE}
            loading="lazy"
            draggable={false}
            className="pointer-events-none absolute"
            style={{ left: tile.left, top: tile.top }}
          />
        ))}

        {markers.map((marker) => {
          const left = lonToX(marker.lon, zoom) - originX;
          const top = latToY(marker.lat, zoom) - originY;
          if (
            left < -40 ||
            top < -40 ||
            left > size.width + 40 ||
            top > size.height + 40
          ) {
            return null;
          }
          return (
            <button
              key={marker.id}
              type="button"
              onClick={marker.onSelect}
              title={marker.label}
              className="absolute -translate-x-1/2 -translate-y-full"
              style={{ left, top }}
            >
              {/* Cible tactile de 44 px, pastille visible de 14 px. */}
              <span className="flex h-touch w-touch items-end justify-center">
                <span
                  className={`mb-1 block h-3.5 w-3.5 rounded-pill border-2 border-card ${
                    marker.highlight ? "bg-accent" : "bg-seq-5"
                  }`}
                />
              </span>
            </button>
          );
        })}
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between p-2">
        {/* L'attribution ODbL n'est pas négociable. */}
        <span className="pointer-events-auto rounded-chip bg-card/85 px-2 py-1 text-[10px] text-mute">
          © OpenStreetMap
        </span>
        <span className="pointer-events-auto flex flex-col gap-1">
          <button
            type="button"
            aria-label="Zoomer"
            onClick={() => setZoom((z) => Math.min(MAX_ZOOM, z + 1))}
            className="h-touch w-touch rounded-button border border-line bg-card text-[20px] font-semibold text-ink"
          >
            +
          </button>
          <button
            type="button"
            aria-label="Dézoomer"
            onClick={() => setZoom((z) => Math.max(MIN_ZOOM, z - 1))}
            className="h-touch w-touch rounded-button border border-line bg-card text-[20px] font-semibold text-ink"
          >
            −
          </button>
        </span>
      </div>
    </div>
  );
}
