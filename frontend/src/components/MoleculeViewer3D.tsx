import { useEffect, useRef } from "react";

type MoleculeViewer3DProps = {
  molBlock: string;
  proteinPdb?: string | null;
  label: string;
};

export function MoleculeViewer3D({ molBlock, proteinPdb, label }: MoleculeViewer3DProps) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    let disposed = false;
    let viewer: ReturnType<(typeof import("3dmol"))["createViewer"]> | null = null;
    let resizeObserver: ResizeObserver | null = null;
    const element = container.current;
    const ligandModelIndex = proteinPdb ? 1 : 0;
    const fitMolecule = () => {
      if (!viewer || disposed) return;
      viewer.resize();
      viewer.zoomTo({ model: ligandModelIndex });
      viewer.zoom(0.85); // Keep roughly 15% visual padding after fitting the molecular bounds.
      viewer.render();
    };
    void import("3dmol").then(({ createViewer }) => {
      if (disposed) return;
      viewer = createViewer(element, { backgroundColor: "#ffffff", antialias: true });
      if (proteinPdb) {
        const protein = viewer.addModel(proteinPdb, "pdb");
        protein.setStyle({}, { cartoon: { color: "spectrum" } });
        void viewer.addSurface("VDW", { opacity: 0.14, color: "#7fa698" }, { model: 0 });
      }
      // RDKit MolBlock is the first-record structure consumed by 3Dmol's SDF parser.
      const ligand = viewer.addModel(molBlock, "sdf");
      ligand.setStyle({}, {
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
  }, [molBlock, proteinPdb]);

  return <div className="molecule-viewer-3d" ref={container} role="img" aria-label={label} data-viewer-mode={proteinPdb ? "complex" : "ligand"} />;
}
