import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { type Region } from "wavesurfer.js/dist/plugins/regions.esm.js";

// Audio provenance: the waveform is the "moment in the audio" a value traces back to (CLAUDE.md §3).
// Each segment is an utterance span; selecting a field seeks + plays its region so the reviewer hears
// exactly the audio the extraction claims as its source.

export interface AudioSegment {
  start: number; // seconds
  end: number; // seconds
  id: string;
  label?: string;
}

export interface AudioProvenanceProps {
  src: string; // audio URL to load into the waveform
  segments: AudioSegment[]; // utterance/segment spans in seconds (provenance regions)
  activeId: string | null; // the selected segment — highlight + seek + play from its start
  onSegmentClick?: (id: string) => void; // clicking a region selects that segment
}

// Colours come from the design tokens (styles.css :root) — wavesurfer draws to a canvas and needs plain
// colour strings, so we read the CSS custom properties at runtime rather than hard-code hex here.
function cssVar(name: string, fallback: string): string {
  if (typeof getComputedStyle === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
const REGION_IDLE = () => cssVar("--wave-region-idle", "rgba(245, 165, 36, 0.16)");
const REGION_ACTIVE = () => cssVar("--wave-region-active", "rgba(245, 165, 36, 0.42)");

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function AudioProvenance({
  src,
  segments,
  activeId,
  onSegmentClick,
}: AudioProvenanceProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsPluginRef = useRef<RegionsPlugin | null>(null);
  const regionMapRef = useRef<Map<string, Region>>(new Map());

  // Latest props for callbacks/builders that must not re-subscribe or rebuild on every render.
  const onClickRef = useRef(onSegmentClick);
  const activeIdRef = useRef(activeId);
  onClickRef.current = onSegmentClick;
  activeIdRef.current = activeId;

  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // (Re)create the WaveSurfer instance whenever the source changes; destroy cleanly on unmount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return; // guard: ref not mounted

    const ws = WaveSurfer.create({
      container,
      url: src,
      height: 64,
      waveColor: cssVar("--wave-wave", "#6b7480"),
      progressColor: cssVar("--wave-progress", "#9aa4b1"),
      cursorColor: cssVar("--wave-cursor", "#e6e9ee"),
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
    });
    const regionsPlugin = ws.registerPlugin(RegionsPlugin.create());

    wsRef.current = ws;
    regionsPluginRef.current = regionsPlugin;

    ws.on("ready", (dur) => {
      setDuration(dur);
      setReady(true);
      buildRegions(); // regions need the decoded duration to place correctly
    });
    ws.on("timeupdate", (t) => setCurrentTime(t));
    ws.on("play", () => setPlaying(true));
    ws.on("pause", () => setPlaying(false));
    ws.on("finish", () => setPlaying(false));

    // Region click selects the segment; stop propagation so the click doesn't also seek to that point.
    regionsPlugin.on("region-clicked", (region, e) => {
      e.stopPropagation();
      onClickRef.current?.(region.id);
    });

    return () => {
      setReady(false);
      setPlaying(false);
      setCurrentTime(0);
      regionMapRef.current.clear();
      regionsPluginRef.current = null;
      wsRef.current = null;
      ws.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rebuild only on src; segments/activeId sync below
  }, [src]);

  // Rebuild regions from the current segments (empty array is fine — the waveform still renders).
  function buildRegions() {
    const plugin = regionsPluginRef.current;
    if (!plugin) return;
    plugin.clearRegions();
    regionMapRef.current.clear();
    for (const seg of segments) {
      const region = plugin.addRegion({
        id: seg.id,
        start: seg.start,
        end: seg.end,
        color: seg.id === activeIdRef.current ? REGION_ACTIVE() : REGION_IDLE(),
        content: seg.label,
        drag: false,
        resize: false,
      });
      regionMapRef.current.set(seg.id, region);
    }
  }

  // Keep regions in sync when the segment set changes after the waveform is ready.
  useEffect(() => {
    if (ready) buildRegions();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- buildRegions reads live refs
  }, [segments, ready]);

  // React to selection: recolour, then seek + play the active region (or stop when cleared).
  useEffect(() => {
    const ws = wsRef.current;
    if (!ready || !ws) return;

    for (const [id, region] of regionMapRef.current) {
      region.setOptions({ color: id === activeId ? REGION_ACTIVE() : REGION_IDLE() });
    }

    if (activeId === null) {
      ws.pause();
      return;
    }
    const region = regionMapRef.current.get(activeId);
    if (!region) return; // id doesn't match a known segment — leave playback untouched
    ws.setTime(region.start);
    void ws.play().catch(() => {}); // browsers reject play() without a gesture — safe to ignore
  }, [activeId, ready]);

  function togglePlay() {
    void wsRef.current?.playPause();
  }

  return (
    <div className="audio-prov">
      <div
        ref={containerRef}
        className="audio-prov__wave"
        role="img"
        aria-label="audio waveform with provenance segments"
      />
      <div className="audio-prov__bar">
        <button
          type="button"
          className="audio-prov__play"
          onClick={togglePlay}
          disabled={!ready}
          aria-label={playing ? "pause audio" : "play audio"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="audio-prov__time" aria-live="off">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>
    </div>
  );
}
