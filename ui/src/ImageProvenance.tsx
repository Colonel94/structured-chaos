import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

// Image-region provenance: the visual half of the "where did this come from?" trust gate (CLAUDE.md
// §3). A source document (or a rasterized PDF page) is shown with the extracted regions overlaid, so
// clicking a value on the review screen can light up the exact pixels it was read from. Boxes are
// stored normalized (0..1 of the natural image), so the same provenance survives any rendered size —
// we re-scale to the CURRENT rendered <img> box, measured live, never to the natural dimensions.

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  id: string;
  label?: string;
} // pixel coords of the NATURAL image (top-left x,y + w,h) — exactly the OCR bbox locator shape

interface ImageProvenanceProps {
  src: string; // image URL (a source document, or a rasterized PDF page)
  boxes: Box[]; // provenance regions on the image
  activeId: string | null; // the box whose value is currently selected — highlight + scroll into view
  onBoxClick?: (id: string) => void;
}

/** The rendered <img> content-box (CSS px) plus the image's natural pixel size. Overlay geometry is
 * derived from the rendered box; each box is placed as a fraction of the NATURAL size, so a raw OCR
 * bbox (natural pixels) maps correctly at any rendered scale. Remeasured on load + every resize. */
interface RenderedSize {
  width: number;
  height: number;
  natW: number;
  natH: number;
}

export default function ImageProvenance({
  src,
  boxes,
  activeId,
  onBoxClick,
}: ImageProvenanceProps): JSX.Element {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const activeRef = useRef<HTMLButtonElement | null>(null);
  // null until the image reports natural dimensions — no overlay is drawn on a not-yet-loaded image.
  const [size, setSize] = useState<RenderedSize | null>(null);

  // Read the current rendered content-box of the <img>. clientWidth/Height exclude border, which is
  // what the absolutely-positioned overlay layer is sized against.
  const measure = useCallback(() => {
    const img = imgRef.current;
    if (!img || !img.complete || img.naturalWidth === 0) return;
    setSize({
      width: img.clientWidth,
      height: img.clientHeight,
      natW: img.naturalWidth,
      natH: img.naturalHeight,
    });
  }, []);

  // The rendered size changes with container width (responsive img), not just the window — a
  // ResizeObserver on the element itself is the only reliable trigger, so boxes stay aligned when the
  // review panel resizes or the layout stacks on mobile.
  useEffect(() => {
    const img = imgRef.current;
    if (!img || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(img);
    return () => ro.disconnect();
  }, [measure]);

  // Reset when the source changes: the old natural dimensions no longer apply, so drop the overlay
  // until the new image loads and re-measures.
  useEffect(() => {
    setSize(null);
  }, [src]);

  // Measure synchronously after paint too — covers a cached image that is already `complete` before
  // the `load` event would fire.
  useLayoutEffect(() => {
    measure();
  }, [measure, src]);

  // Bring the selected region into view without yanking the whole page — block:'nearest' only scrolls
  // if it is actually off-screen.
  useEffect(() => {
    if (activeId && activeRef.current) {
      activeRef.current.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [activeId, size]);

  const ready = size !== null && size.width > 0 && size.height > 0;

  return (
    <figure className="img-prov">
      {/* A scanned invoice / photographed receipt is a large white rectangle; in a near-black instrument
          it glares. So the document sits INSIDE a matte surround (`__mat`), never flush against the
          canvas (DESIGN.md §6). The frame still shrinks to the rendered image box (inline-block) so the
          absolute overlay stays anchored to the image itself — precision unchanged. */}
      <div className="img-prov__mat">
        <div className="img-prov__frame">
          <img
            ref={imgRef}
            className="img-prov__img"
            src={src}
            alt=""
            onLoad={measure}
            draggable={false}
          />
          {ready && (
            <div className="img-prov__overlay" style={{ width: size.width, height: size.height }}>
              {boxes.map((box) => {
                const active = box.id === activeId;
                return (
                  <button
                    key={box.id}
                    ref={active ? activeRef : undefined}
                    type="button"
                    className={`img-prov__box${active ? " img-prov__box--active" : " img-prov__box--faint"}`}
                    style={{
                      left: `${(box.x / size.natW) * 100}%`,
                      top: `${(box.y / size.natH) * 100}%`,
                      width: `${(box.w / size.natW) * 100}%`,
                      height: `${(box.h / size.natH) * 100}%`,
                    }}
                    title={box.label}
                    aria-label={box.label ?? `region ${box.id}`}
                    aria-pressed={active}
                    onClick={() => onBoxClick?.(box.id)}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>
      <figcaption className="img-prov__caption">
        {ready ? `${boxes.length} region${boxes.length === 1 ? "" : "s"}` : "loading image…"}
      </figcaption>
    </figure>
  );
}
