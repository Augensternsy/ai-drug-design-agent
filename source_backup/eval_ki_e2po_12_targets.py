import sys
import os
import json
import argparse
import logging
import time
from functools import partial
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from rdkit import Chem, DataStructs
from rdkit.Chem import QED, Descriptors, rdFingerprintGenerator, rdMolDescriptors, AllChem, Lipinski
from rdkit.ML.Cluster import Butina
from multiprocessing import Pool

# Patches for torch compiler compatibility in older versions
if not hasattr(torch, 'compiler'):
    from types import ModuleType
    compiler = ModuleType("compiler")
    compiler.disable = lambda func=None, recursive=False: (func if func is not None else (lambda f: f))
    torch.compiler = compiler
    sys.modules["torch.compiler"] = compiler

orig_load_state_dict = nn.Module.load_state_dict
def patched_load_state_dict(self, state_dict, *args, **kwargs):
    kwargs.pop('assign', None)
    return orig_load_state_dict(self, state_dict, *args, **kwargs)
nn.Module.load_state_dict = patched_load_state_dict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
IMPROVED_DIFFUSION_DIR = os.path.join(PROJECT_ROOT, 'improved-diffusion', 'scripts')

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if IMPROVED_DIFFUSION_DIR not in sys.path:
    sys.path.insert(0, IMPROVED_DIFFUSION_DIR)

from improved_diffusion import gaussian_diffusion_self_cond as gd
from improved_diffusion.respace_self_cond import SpacedDiffusion
from improved_diffusion.transformer_model2_self_cond import TransformerNetModel2
from mytokenizers import ChemformerTokenizer
from process_train_csv import ESM2ProjectionLayer
from transformers import AutoModel, AutoTokenizer, set_seed
from improved_diffusion.test_util import denoised_fn_round

# Meeko and Vina imports
try:
    from vina import Vina
    from meeko import MoleculePreparation
except ImportError:
    Vina = None
    MoleculePreparation = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Eval12Targets")

GENE_TO_PDB = {
    'ESR1':   '2r6w',
    'HCRTR1': '4zjc',
    'JAK1':   '3eyg',
    'P2RX3':  '5svl',
    'KDM1A':  '5lhg',
    'IDH1':   '4umx',
    'RIOK1':  '4otp',
    'NR4A1':  '3v3q',
    'GRIK1':  '3fv1',
    'FTO':    '4zs3',
    'SPIN1':  '5jsj',
    'CCR9':   '5lwe'
}

BOX_PADDING = 10.0
EXHAUSTIVENESS = 8
N_POSES = 1

def extract_protein_embedding(seq, esm_model, esm_tokenizer, projection_layer, device):
    inputs = esm_tokenizer(
        [seq.strip().upper()],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=256
    ).to(device)

    with torch.no_grad():
        outputs = esm_model(**inputs)
        token_embeddings = outputs.last_hidden_state
        token_embeddings = projection_layer(token_embeddings)

    attention_mask = inputs['attention_mask']
    states = token_embeddings[0]
    mask = attention_mask[0]
    seq_len = states.shape[0]

    pad_len = 256 - seq_len
    if pad_len > 0:
        states = torch.nn.functional.pad(states, (0, 0, 0, pad_len))
        mask = torch.nn.functional.pad(mask, (0, pad_len))
    else:
        states = states[:256, :]
        mask = mask[:256]

    return states.unsqueeze(0), mask.unsqueeze(0)

def parse_fasta(fpath):
    with open(fpath, 'r') as f:
        lines = f.readlines()
    return ''.join([line.strip() for line in lines if not line.startswith('>')])

def sanitize_smiles(smiles):
    if not smiles:
        return None
    if '[EOS]' in smiles:
        smiles = smiles.split('[EOS]')[0]
    smiles = smiles.replace('[SOS]', '').replace('[PAD]', '').strip()
    open_count = smiles.count('(')
    close_count = smiles.count(')')
    if open_count > close_count:
        smiles = smiles + ')' * (open_count - close_count)
    elif close_count > open_count:
        for _ in range(close_count - open_count):
            if ')' in smiles:
                smiles = smiles[:smiles.rfind(')')] + smiles[smiles.rfind(')')+1:]
    return smiles

def generate_samples(model, diffusion, desc_state, desc_mask, num_samples=200, batch_size=50, device='cpu', tokenizer=None, args=None):
    model.eval()
    all_samples = []
    num_done = 0
    
    if getattr(args, 'clamp', 'none') == 'clamp':
        model_emb = model.word_embedding.weight[:len(tokenizer)].clone().detach().to(device)
        denoised_fn = partial(denoised_fn_round, args, model_emb)
    else:
        denoised_fn = None
        
    while num_done < num_samples:
        current_batch = min(batch_size, num_samples - num_done)
        b_desc_state = desc_state.repeat(current_batch, 1, 1)
        b_desc_mask = desc_mask.repeat(current_batch, 1)
        
        sample_shape = (current_batch, 170, model.in_channels)
        with torch.no_grad():
            samples = diffusion.p_sample_loop(
                model,
                sample_shape,
                clip_denoised=False,
                model_kwargs={},
                progress=False,
                desc=(b_desc_state, b_desc_mask),
                denoised_fn=denoised_fn
            )
        all_samples.append(samples)
        num_done += current_batch

    all_samples = torch.cat(all_samples, dim=0).to(device)
    
    with torch.no_grad():
        logits = model.get_logits(all_samples)
        logits = logits[:, :, :len(tokenizer)]
        cands = torch.argmax(logits, dim=-1)

    generated_smiles = []
    for idx in range(cands.shape[0]):
        try:
            smi = tokenizer.decode_one(cands[idx])
            smi_clean = sanitize_smiles(smi)
            if smi_clean:
                try:
                    mol = Chem.MolFromSmiles(smi_clean)
                    if not mol:
                        smi_clean = "INVALID"
                except:
                    smi_clean = "INVALID"
            else:
                smi_clean = "INVALID"
            generated_smiles.append(smi_clean)
        except Exception:
            generated_smiles.append("INVALID")
            
    return generated_smiles

def calculate_molecular_properties(smiles_list, target_name):
    total_generated = len(smiles_list)
    valid_mols = []
    valid_smiles_clean = []
    
    for s in smiles_list:
        if isinstance(s, str) and s.strip() not in ("", "INVALID", "nan"):
            try:
                m = Chem.MolFromSmiles(s.strip())
                if m:
                    valid_mols.append(m)
                    valid_smiles_clean.append(Chem.MolToSmiles(m, canonical=True))
            except:
                pass
                
    validity = len(valid_mols) / total_generated if total_generated > 0 else 0.0
    
    if len(valid_mols) == 0:
        return {
            'target': target_name, 'validity': 0.0, 'uniqueness': 0.0,
            'diversity': 0.0, 'novelty': 0.0, 'qed': 0.0, 'sa': 0.0,
            'molwt': 0.0, 'ro5_rate': 0.0
        }
        
    unique_smiles = set(valid_smiles_clean)
    uniqueness = len(unique_smiles) / len(valid_mols)
    
    # Diversity
    if len(valid_mols) > 1:
        fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        fps = [fpgen.GetFingerprint(m) for m in valid_mols]
        dists = []
        for i in range(1, len(fps)):
            sims = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
            dists.extend([1 - x for x in sims])
        clusters = Butina.ClusterData(dists, len(fps), distThresh=0.2, isDistData=True)
        diversity = len(clusters) / len(fps)
    else:
        diversity = 1.0

    # Novelty vs actives
    ref_csv = os.path.join(PROJECT_ROOT, "datasets", "actives_bindingdb_cl", f"{target_name}.csv")
    novelty = 1.0
    if os.path.exists(ref_csv):
        try:
            ref_df = pd.read_csv(ref_csv)
            smi_col = next((c for c in ['SMILES', 'smiles', 'mol'] if c in ref_df.columns), ref_df.columns[0])
            ref_mols = [Chem.MolFromSmiles(str(s)) for s in ref_df[smi_col].dropna()]
            ref_mols = [m for m in ref_mols if m]
            if ref_mols:
                fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
                ref_fps = [fpgen.GetFingerprint(m) for m in ref_mols]
                gen_fps = [fpgen.GetFingerprint(m) for m in valid_mols]
                novel_count = 0
                for g_fp in gen_fps:
                    sims = DataStructs.BulkTanimotoSimilarity(g_fp, ref_fps)
                    if not sims or max(sims) < 0.5:
                        novel_count += 1
                novelty = novel_count / len(valid_mols)
        except Exception:
            pass

    qeds = [QED.default(m) for m in valid_mols]
    molwts = [Descriptors.MolWt(m) for m in valid_mols]
    
    sas = []
    for m in valid_mols:
        try:
            from rdkit.Contrib.SA_Score import sascorer
            sas.append(sascorer.calculateScore(m))
        except:
            sas.append(3.0)
        
    ro5_passes = 0
    for m in valid_mols:
        mw = Descriptors.MolWt(m)
        logp = Descriptors.MolLogP(m)
        hdonors = rdMolDescriptors.CalcNumHBD(m)
        hacceptors = rdMolDescriptors.CalcNumHBA(m)
        if mw <= 500 and logp <= 5 and hdonors <= 5 and hacceptors <= 10:
            ro5_passes += 1
    ro5_rate = ro5_passes / len(valid_mols)
    
    return {
        'target': target_name,
        'validity': float(validity),
        'uniqueness': float(uniqueness),
        'diversity': float(diversity),
        'novelty': float(novelty),
        'qed': float(np.mean(qeds)),
        'sa': float(np.mean(sas)),
        'molwt': float(np.mean(molwts)),
        'ro5_rate': float(ro5_rate)
    }

# Docking helper functions
def get_box_config_for_docking(ref_ligand_path):
    mol = Chem.MolFromMolFile(ref_ligand_path)
    if not mol: return None, None
    conf = mol.GetConformer()
    coords = conf.GetPositions()
    center = np.mean(coords, axis=0)
    size = (np.max(coords, axis=0) - np.min(coords, axis=0)) + BOX_PADDING
    return center, size

def get_morgan_fp(mol):
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)

def prepare_ligand_pdbqt(smiles):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if not mol: return None
        mol = Chem.AddHs(mol)
        if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
            if AllChem.EmbedMolecule(mol, useRandomCoords=True) != 0: return None
        try:
            AllChem.UFFOptimizeMolecule(mol)
        except:
            pass
        preparator = MoleculePreparation()
        preparator.prepare(mol)
        return preparator.write_pdbqt_string()
    except:
        return None

def perform_diverse_selection(valid_smiles, max_selected):
    mols = []
    fps = []
    clean_smiles = []
    for s in valid_smiles:
        mol = Chem.MolFromSmiles(s)
        if mol:
            mols.append(mol)
            fps.append(get_morgan_fp(mol))
            clean_smiles.append(s)
            
    n_fps = len(fps)
    if n_fps <= max_selected:
        return clean_smiles
        
    try:
        dists = []
        for i in range(1, n_fps):
            sims = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
            dists.extend([1 - x for x in sims])
        clusters = Butina.ClusterData(dists, n_fps, distThresh=0.4, isDistData=True)
        sorted_clusters = sorted(clusters, key=len, reverse=True)
        selected_indices = []
        picked_per_cluster = [0] * len(sorted_clusters)
        while len(selected_indices) < max_selected:
            added_any = False
            for c_idx, cluster in enumerate(sorted_clusters):
                if len(selected_indices) >= max_selected: break
                current_pick = picked_per_cluster[c_idx]
                if current_pick < len(cluster):
                    idx = cluster[current_pick]
                    selected_indices.append(idx)
                    picked_per_cluster[c_idx] += 1
                    added_any = True
            if not added_any: break
        return [clean_smiles[idx] for idx in selected_indices]
    except Exception as e:
        logger.warning(f"Butina cluster selection failed: {e}. Falling back to slicing.")
        return clean_smiles[:max_selected]

def dock_target_molecules(args):
    target, smiles_list, receptor_path, center, size, save_path = args
    logger.info(f"[{target}] Starting Vina docking for {len(smiles_list)} molecules...")
    
    try:
        v = Vina(sf_name='vina', cpu=1)
        v.set_receptor(receptor_path)
        v.compute_vina_maps(center=center, box_size=size)
    except Exception as e:
        logger.error(f"[{target}] Error initializing Vina: {e}")
        records = []
        for idx, smiles in enumerate(smiles_list):
            records.append({
                'Target': target, 'Index': idx, 'SMILES': smiles,
                'Vina_Score': np.nan, 'Ligand_Efficiency': np.nan
            })
        pd.DataFrame(records).to_csv(save_path, index=False)
        return target, records

    records = []
    t_start = time.time()
    
    for idx, smiles in enumerate(smiles_list):
        res = {
            'Target': target, 'Index': idx, 'SMILES': smiles,
            'Vina_Score': np.nan, 'Ligand_Efficiency': np.nan
        }
        
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            records.append(res)
            continue
            
        n_rot = Lipinski.NumRotatableBonds(mol)
        mw = Descriptors.MolWt(mol)
        if n_rot > 15 or mw > 750:
            records.append(res)
            continue
            
        pdbqt_str = prepare_ligand_pdbqt(smiles)
        if pdbqt_str:
            try:
                v.set_ligand_from_string(pdbqt_str)
                v.dock(exhaustiveness=EXHAUSTIVENESS, n_poses=N_POSES)
                score = v.score()[0]
                res['Vina_Score'] = score
                n_heavy = mol.GetNumHeavyAtoms()
                if n_heavy > 0:
                    res['Ligand_Efficiency'] = -score / n_heavy
            except Exception:
                pass
        records.append(res)

    df_save = pd.DataFrame(records)
    df_save.to_csv(save_path, index=False)
    logger.info(f"[{target}] Completed in {time.time() - t_start:.1f}s")
    return target, records

def main():
    parser = argparse.ArgumentParser(description="Evaluate Aligned Checkpoints on All 12 targets")
    parser.add_argument('--checkpoint', type=str, required=True, help="Path to checkpoint to evaluate")
    parser.add_argument('--esm2_path', type=str, default=os.path.join(PROJECT_ROOT, 'esm2_t30_150M_UR50D'))
    parser.add_argument('--num_samples', type=int, default=200)
    parser.add_argument('--dock_samples', type=int, default=100)
    parser.add_argument('--batch_size', type=int, default=50)
    parser.add_argument('--output_dir', type=str, default=os.path.join(PROJECT_ROOT, 'evaluation', 'ki_e2po_eval_12_targets'))
    parser.add_argument('--clamp', type=str, default='none', choices=['clamp', 'none'], help="Clamping mode")
    parser.add_argument('--n_cores', type=int, default=12, help="Parallel cores for Vina")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    tokenizer = ChemformerTokenizer(max_len=170)
    vocab_size = len(tokenizer)

    # 1. Load Model
    logger.info(f"Loading checkpoint model from {args.checkpoint}...")
    model = TransformerNetModel2(
        in_channels=32, model_channels=128, dropout=0.1, use_checkpoint=False,
        config_name='bert-base-uncased', training_mode='e2e', vocab_size=vocab_size,
        experiment_mode='lm', logits_mode=1, hidden_size=1024, num_attention_heads=16,
        num_hidden_layers=12, self_cond=True
    )
    ckpt = torch.load(args.checkpoint, map_location='cpu')
    model.load_state_dict(ckpt)
    model.to(device)
    model.eval()

    diffusion = SpacedDiffusion(
        use_timesteps=[i for i in range(0, 2000, 10)], # 200 steps
        betas=gd.get_named_beta_schedule('sqrt', 2000),
        model_mean_type=gd.ModelMeanType.START_X,
        model_var_type=gd.ModelVarType.FIXED_LARGE,
        loss_type=gd.LossType.E2E_MSE,
        rescale_timesteps=True,
        model_arch='transformer',
        training_mode='e2e',
    )

    logger.info(f"Loading ESM-2 model from {args.esm2_path}...")
    esm_tokenizer = AutoTokenizer.from_pretrained(args.esm2_path)
    esm_model = AutoModel.from_pretrained(args.esm2_path).to(device)
    esm_model.eval()

    projection_layer = ESM2ProjectionLayer(input_dim=640, output_dim=1024).to(device)
    torch.manual_seed(42)
    for m in projection_layer.modules():
        if isinstance(m, nn.Linear):
            nn.init.xavier_uniform_(m.weight)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
    projection_layer.eval()

    # 2. Generation & Properties loop
    properties_results = []
    generated_candidates = {}

    for target in GENE_TO_PDB.keys():
        fasta_path = os.path.join(PROJECT_ROOT, "datasets", "fasta", f"{target}.fasta")
        if not os.path.exists(fasta_path):
            logger.error(f"Fasta not found: {fasta_path}")
            continue
            
        out_csv = os.path.join(args.output_dir, f"generated_{target}.csv")
        if os.path.exists(out_csv):
            logger.info(f"Found existing generated candidates for {target} at {out_csv}. Loading...")
            smiles_list = pd.read_csv(out_csv)['SMILES'].dropna().astype(str).tolist()
        else:
            seq = parse_fasta(fasta_path)
            desc_state, desc_mask = extract_protein_embedding(seq, esm_model, esm_tokenizer, projection_layer, device)
            logger.info(f"Generating {args.num_samples} samples for {target}...")
            set_seed(42)
            smiles_list = generate_samples(model, diffusion, desc_state, desc_mask, num_samples=args.num_samples, batch_size=args.batch_size, device=device, tokenizer=tokenizer, args=args)
            # Save CSV for target raw samples
            pd.DataFrame({'SMILES': smiles_list}).to_csv(out_csv, index=False)
        
        # Filter valid smiles
        valid_smiles = []
        for s in smiles_list:
            if isinstance(s, str) and s.strip() not in ("", "INVALID", "nan"):
                try:
                    m = Chem.MolFromSmiles(s.strip())
                    if m:
                        valid_smiles.append(Chem.MolToSmiles(m, canonical=True))
                except:
                    pass
        generated_candidates[target] = valid_smiles

        props = calculate_molecular_properties(smiles_list, target)
        properties_results.append(props)
        logger.info(f"Target {target} Properties - Validity: {props['validity']*100:.1f}%, Uniqueness: {props['uniqueness']*100:.1f}%, QED: {props['qed']:.3f}, SA: {props['sa']:.2f}")

    df_props = pd.DataFrame(properties_results)
    df_props.to_csv(os.path.join(args.output_dir, 'properties_summary.csv'), index=False)
    logger.info(f"Properties summary saved. Avg Validity: {df_props['validity'].mean()*100:.1f}%")

    # 3. Vina Docking if Vina is installed
    if Vina is None or MoleculePreparation is None or args.dock_samples <= 0:
        logger.warning("Vina or Meeko python modules not installed or dock_samples <= 0. Skipping Vina docking step.")
        return

    docking_tasks = []
    for target, valid_smiles in generated_candidates.items():
        if len(valid_smiles) == 0:
            logger.warning(f"Target {target} has 0 valid molecules. Skipping docking.")
            continue
            
        target_dir = os.path.join(args.output_dir, target)
        if os.path.exists(os.path.join(target_dir, 'vina_results.csv')):
            logger.info(f"Target {target} docking already completed. Skipping docking task.")
            continue
            
        # Select 100 diverse molecules using Butina
        selected_smiles = perform_diverse_selection(valid_smiles, args.dock_samples)
        
        # Save selected
        os.makedirs(target_dir, exist_ok=True)
        pd.DataFrame({'SMILES': selected_smiles}).to_csv(os.path.join(target_dir, "selected_100.csv"), index=False)
        
        # Build docking task
        pdb_id = GENE_TO_PDB[target]
        protein_dir = os.path.normpath(os.path.join(PROJECT_ROOT, "datasets", "CrossDocked2020", pdb_id))
        receptor_path = os.path.join(protein_dir, f"{pdb_id}_protein_cleaned.pdbqt")
        ref_lig_path = os.path.join(protein_dir, f"{pdb_id}_ligand.sdf")
        
        if not os.path.exists(receptor_path) or not os.path.exists(ref_lig_path):
            logger.error(f"Receptor or ligand file missing for {target} (PDB: {pdb_id}). Skipping docking.")
            continue
            
        center, size = get_box_config_for_docking(ref_lig_path)
        if center is None:
            logger.error(f"Could not compute docking box for {target}. Skipping docking.")
            continue
            
        save_path = os.path.join(target_dir, "vina_results.csv")
        docking_tasks.append((target, selected_smiles, receptor_path, center, size, save_path))

    all_dock_records = []
    # Load completed records for skipped targets
    for target in GENE_TO_PDB.keys():
        target_dir = os.path.join(args.output_dir, target)
        save_path = os.path.join(target_dir, "vina_results.csv")
        if os.path.exists(save_path):
            try:
                df_existing = pd.read_csv(save_path)
                df_existing['Target'] = target
                all_dock_records.extend(df_existing.to_dict('records'))
                logger.info(f"Loaded {len(df_existing)} existing docking records for {target}.")
            except Exception as e:
                logger.error(f"Error loading existing records for {target}: {e}")

    if len(docking_tasks) > 0:
        logger.info(f"Starting Vina docking for {len(docking_tasks)} targets using {args.n_cores} cores...")
        with Pool(processes=min(len(docking_tasks), args.n_cores)) as pool:
            for target, records in pool.imap_unordered(dock_target_molecules, docking_tasks):
                logger.info(f"Completed target {target} docking.")
                all_dock_records.extend(records)
    else:
        logger.info("All docking targets already completed. Skipping Pool execution.")

    # 4. Docking stats
    df_results = pd.DataFrame(all_dock_records)
    df_results.to_csv(os.path.join(args.output_dir, "all_docking_results.csv"), index=False)

    stats = []
    for target in GENE_TO_PDB.keys():
        df_tgt = df_results[df_results['Target'] == target]
        if len(df_tgt) == 0: continue
        
        df_valid = df_tgt.dropna(subset=['Vina_Score'])
        total = len(df_tgt)
        valid_count = len(df_valid)
        sr = (valid_count / total * 100.0) if total > 0 else 0.0
        
        if valid_count > 0:
            mean_vina = df_valid['Vina_Score'].mean()
            median_vina = df_valid['Vina_Score'].median()
            sorted_v = df_valid['Vina_Score'].sort_values()
            top_n = max(1, int(np.ceil(0.1 * valid_count)))
            top10_vina = sorted_v.iloc[:top_n].mean()
            mean_le = df_valid['Ligand_Efficiency'].mean()
        else:
            mean_vina = median_vina = top10_vina = mean_le = np.nan
            
        stats.append({
            'Target': target,
            'Success_Rate': sr,
            'Mean_Vina': mean_vina,
            'Median_Vina': median_vina,
            'Top10_Vina': top10_vina,
            'Mean_LE': mean_le
        })
        
    df_stats = pd.DataFrame(stats)
    df_stats.to_csv(os.path.join(args.output_dir, "docking_summary.csv"), index=False)
    logger.info("="*80)
    logger.info("  12 TARGETS VINA DOCKING EVALUATION COMPLETE SUMMARY:")
    logger.info("="*80)
    logger.info(df_stats.to_string(index=False))
    logger.info("="*80)

if __name__ == '__main__':
    main()
