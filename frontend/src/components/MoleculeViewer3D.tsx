import { useEffect, useRef } from "react";

export function MoleculeViewer3D({ molBlock, label }: { molBlock: string; label: string }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    let disposed = false;
    let viewer: ReturnType<(typeof import("3dmol"))["createViewer"]> | null = null;
    let resizeObserver: ResizeObserver | null = null;
    const element = container.current;
    const fitMolecule = () => {
      if (!viewer || disposed) return;
      viewer.resize();
      viewer.zoomTo();
      viewer.zoom(0.85); // Keep roughly 15% visual padding after fitting the molecular bounds.
      viewer.render();
    };
    void import("3dmol").then(({ createViewer }) => {
      if (disposed) return;
      viewer = createViewer(element, { backgroundColor: "#ffffff", antialias: true });
      // RDKit MolBlock is the first-record structure consumed by 3Dmol's SDF parser.
      viewer.addModel(molBlock, "sdf");
      viewer.setStyle({}, {
        stick: { radius: 0.11, colorscheme: "Jmol" },
        sphere: { scale: 0.27, colorscheme: "Jmol" },
      });
      fitMolecule();
      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(fitMolecule);
        resizeObserver.observe(element);
      }
      window.addEventListener("resize", fitMolecule);
    });
    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      window.removeEventListener("resize", fitMolecule);
      viewer?.clear();
    };
  }, [molBlock]);

  return <div className="molecule-viewer-3d" ref={container} role="img" aria-label={label} />;
}
