import { useEffect, useRef } from "react";

export function MoleculeViewer3D({ sdf, label }: { sdf: string; label: string }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    let disposed = false;
    let viewer: ReturnType<(typeof import("3dmol"))["createViewer"]> | null = null;
    const element = container.current;
    void import("3dmol").then(({ createViewer }) => {
      if (disposed) return;
      viewer = createViewer(element, { backgroundColor: "#fbfaf5" });
      viewer.addModel(sdf, "sdf");
      viewer.setStyle({}, { stick: { radius: 0.14 }, sphere: { scale: 0.23 } });
      viewer.zoomTo();
      viewer.render();
    });
    return () => {
      disposed = true;
      viewer?.clear();
    };
  }, [sdf]);

  return <div className="molecule-viewer-3d" ref={container} role="img" aria-label={label} />;
}
