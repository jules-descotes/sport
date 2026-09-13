"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

/**
 * Le scan de code-barres, quand le navigateur sait le faire.
 *
 * `BarcodeDetector` est natif sur Android et dans Chrome de bureau ; Safari ne
 * l'a pas. On **ne bricole pas** un décodeur maison ni une bibliothèque de
 * trois cents kilo-octets pour ça : le repli est la saisie du code à la main,
 * huit chiffres, et c'est un cas rare — on scanne ce qu'on a dans le placard,
 * et le placard ne change pas toutes les semaines.
 *
 * `available` dit lequel des deux chemins l'écran doit proposer. Il est lu par
 * `useSyncExternalStore` et non posé dans un effet : l'instantané serveur est
 * `false`, le client lit la vérité au premier rendu, et le bouton de scan
 * n'apparaît jamais une frame après le reste.
 *
 * La vidéo est branchée par une **ref de rappel** plutôt que par un objet
 * `useRef` rendu à l'appelant : une ref qui traverse une frontière de composant
 * finit par être lue pendant le rendu, ce qui est précisément ce que React
 * interdit.
 */

interface DetectedBarcode {
  rawValue: string;
}

interface BarcodeDetectorLike {
  detect: (source: CanvasImageSource) => Promise<DetectedBarcode[]>;
}

type BarcodeDetectorConstructor = new (options?: {
  formats?: string[];
}) => BarcodeDetectorLike;

/** Les formats des produits alimentaires, et eux seuls : chercher un QR code
 *  sur un paquet de riz ralentit la détection pour rien. */
const FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];

/** Intervalle entre deux analyses d'image. 400 ms : l'œil ne voit pas la
 *  différence, et le téléphone ne chauffe pas. */
const SCAN_INTERVAL_MS = 400;

function detectorClass(): BarcodeDetectorConstructor | null {
  if (typeof window === "undefined") return null;
  const candidate = (window as unknown as Record<string, unknown>)
    .BarcodeDetector;
  return typeof candidate === "function"
    ? (candidate as BarcodeDetectorConstructor)
    : null;
}

function isSupported(): boolean {
  return (
    detectorClass() !== null &&
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  );
}

/** La disponibilité ne change jamais en cours de vie : rien à réabonner. */
const noSubscribe = () => () => {};

export function useBarcodeScanner(onDetected: (code: string) => void) {
  const video = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [running, setRunning] = useState(false);

  const available = useSyncExternalStore(
    noSubscribe,
    isSupported,
    () => false,
  );

  const callback = useRef(onDetected);
  useEffect(() => {
    callback.current = onDetected;
  }, [onDetected]);

  const attach = useCallback((node: HTMLVideoElement | null) => {
    video.current = node;
    if (node && streamRef.current) {
      node.srcObject = streamRef.current;
      void node.play();
    }
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setRunning(false);
  }, []);

  const start = useCallback(async () => {
    if (detectorClass() === null) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        // La caméra arrière : personne ne scanne un paquet avec la selfie.
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      setRunning(true);
      if (video.current) {
        video.current.srcObject = stream;
        await video.current.play();
      }
    } catch {
      // Permission refusée, caméra occupée : on reste sur la saisie manuelle
      // plutôt que d'afficher une erreur qu'on ne sait pas résoudre.
      stop();
    }
  }, [stop]);

  useEffect(() => {
    if (!running) return;
    const Detector = detectorClass();
    if (Detector === null) return;

    const detector = new Detector({ formats: FORMATS });
    let cancelled = false;

    const timer = setInterval(async () => {
      const node = video.current;
      if (cancelled || !node || node.readyState < 2) return;
      try {
        const found = await detector.detect(node);
        const code = found[0]?.rawValue;
        if (code) {
          callback.current(code);
          stop();
        }
      } catch {
        // Une image floue lève parfois : on réessaiera dans 400 ms.
      }
    }, SCAN_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [running, stop]);

  // La caméra ne doit pas rester allumée quand l'écran disparaît.
  useEffect(() => stop, [stop]);

  return { attach, running, available, start, stop };
}
