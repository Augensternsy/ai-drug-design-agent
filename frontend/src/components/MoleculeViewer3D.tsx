import { useEffect, useRef } from "react";

export function MoleculeViewer3D({ molBlock, label }: { molBlock: string; label: string }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    let disposed = false;
    let viewer: ReturnType<(typeof import("3dmol"))["createViewer"]> | null = null;
    const element = container.current;
    void import("3dmol").then(({ createViewer }) => {
      if (disposed) return;
      viewer = createViewer(element, { backgroundColor: "#ffffff" });
      // RDKit MolBlock is the first-record structure consumed by 3Dmol's SDF parser.
      viewer.addModel(molBlock, "sdf");
      viewer.setStyle({}, {
        stick: { radius: 0.15, colorscheme: "Jmol" },
        sphere: { scale: 0.24, colorscheme: "Jmol" },
      });
      viewer.zoomTo();
      viewer.render();
    });
    return () => {
      disposed = true;
      viewer?.clear();
    };
  }, [molBlock]);

  return <div className="molecule-viewer-3d" ref={container} role="img" aria-label={label} />;
}
