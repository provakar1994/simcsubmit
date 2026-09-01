#!/usr/bin/env python3
"""
Small SIMC campaign helper.

Clone this directory inside simc_gfortran/ or pass --simc-dir explicitly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_NGEN = 100000
DEFAULT_BACKEND = "ifarm"
MAX_RANDOM_SEED = 2_147_483_647
SWIF_DEFAULTS = {
    "disk": "4GB",
    "ram": "2GB",
    "time": "2h",
    "partition": "production",
    "cores": 1,
}


@dataclass(frozen=True)
class Kinematics:
    target: str
    particle: str
    ebeam_gev: float
    ebeam_raw: str
    hsp: float
    hsth: float
    ssp: float
    ssth: float
    x: float
    x_raw: str
    q2: float
    q2_raw: str
    z: float
    z_raw: str
    thpq: float
    thpq_raw: str


@dataclass(frozen=True)
class TargetProps:
    A: float
    Z: float
    mass_amu: float
    rho: float
    thick: float


@dataclass(frozen=True)
class ProcessFlags:
    doing_pion: int
    which_pion: int
    doing_semi: int
    doing_hplus: int
    doing_rho: int
    egamma_max: float
    ngen: int


@dataclass(frozen=True)
class JobSpec:
    reaction: str
    firstjob: int
    njobs: int
    ngen: int


@dataclass(frozen=True)
class SimcJob:
    kin: Kinematics
    reaction: str
    jobid: int
    ngen: int
    stem: str
    random_seed: int


TARGET_PROPS = {
    "LH2": TargetProps(1.0, 1.0, 1.007276, 0.0759, 759.0),
    "LD2": TargetProps(2.0, 1.0, 2.014102, 0.16743, 1674.3),
    "C": TargetProps(12.0, 6.0, 12.011, 2.7, 1072.0),
    "Cu": TargetProps(64.0, 29.0, 64.0, 8.96, 760.0),
}

REACTIONS = {
    "LH2_pip": ["sidis", "excl", "delta", "rho"],
    "LH2_pim": ["sidis", "delta", "rho"],
    "LD2_pip": ["sidis", "excl", "delta", "rho"],
    "LD2_pim": ["sidis", "excl", "delta", "rho"],
    "C_pip": ["sidis", "excl", "delta", "rho"],
    "C_pim": ["sidis", "excl", "delta", "rho"],
    "Cu_pip": ["sidis", "excl", "delta", "rho"],
    "Cu_pim": ["sidis", "excl", "delta", "rho"],
}


def process_flags(reaction: str, particle: str, ebeam_mev: float, ngen: int) -> ProcessFlags:
    if reaction == "sidis" and particle == "pip":
        return ProcessFlags(1, 0, 1, 1, 0, ebeam_mev, ngen)
    if reaction == "sidis" and particle == "pim":
        return ProcessFlags(1, 1, 1, 0, 0, ebeam_mev, ngen)
    if reaction == "excl" and particle == "pip":
        return ProcessFlags(1, 0, 0, 1, 0, ebeam_mev, ngen)
    if reaction == "excl" and particle == "pim":
        return ProcessFlags(1, 1, 0, 0, 0, ebeam_mev, ngen)
    if reaction == "delta" and particle == "pip":
        return ProcessFlags(1, 2, 0, 1, 0, ebeam_mev, ngen)
    if reaction == "delta" and particle == "pim":
        return ProcessFlags(1, 3, 0, 0, 0, ebeam_mev, ngen)
    if reaction == "rho":
        return ProcessFlags(0, 0, 0, 1, 1, ebeam_mev, ngen)
    raise ValueError(f"Unsupported reaction/particle combination: {reaction}/{particle}")


def tag(value: str | float | int) -> str:
    text = str(value).strip()
    text = text.replace("-", "m").replace(".", "p")
    return re.sub(r"[^A-Za-z0-9_]+", "", text)


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "yes", "on"}:
        return True
    if value.lower() in {"false", "no", "off"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_simple_yaml(path: Path) -> dict:
    data: dict = {}
    current_key = None
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not line.startswith(" "):
            if ":" not in line:
                raise SystemExit(f"ERROR: Bad YAML line {lineno} in {path}: {raw}")
            key, value = line.split(":", 1)
            key = key.strip().replace("-", "_")
            value = value.strip()
            if value:
                data[key] = parse_scalar(value)
                current_key = None
            else:
                data[key] = {}
                current_key = key
            continue
        if current_key is None:
            raise SystemExit(f"ERROR: Bad YAML indentation on line {lineno} in {path}: {raw}")
        child = line.strip()
        if child.startswith("- "):
            if not isinstance(data[current_key], list):
                data[current_key] = []
            data[current_key].append(parse_scalar(child[2:]))
            continue
        if ":" not in child:
            raise SystemExit(f"ERROR: Bad YAML line {lineno} in {path}: {raw}")
        key, value = child.split(":", 1)
        if not isinstance(data[current_key], dict):
            raise SystemExit(f"ERROR: Cannot mix YAML list and map under {current_key!r}")
        data[current_key][key.strip().replace("-", "_")] = parse_scalar(value)
    return data


def load_config(path_value: str | None) -> dict:
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"ERROR: config file not found: {path}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
    else:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(path.read_text()) or {}
        except ImportError:
            data = parse_simple_yaml(path)
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: config file must contain a top-level map: {path}")

    config = normalize_config(data)
    for key in ["settings", "simc_dir", "outdir"]:
        if key in config and config[key]:
            config[key] = str(resolve_config_path(path.parent, str(config[key])))
    return config


def normalize_config(data: dict) -> dict:
    config = {str(k).replace("-", "_"): v for k, v in data.items()}
    swif = config.pop("swif", None)
    if swif:
        if not isinstance(swif, dict):
            raise SystemExit("ERROR: config key 'swif' must be a map")
        for key, value in swif.items():
            config[f"swif_{str(key).replace('-', '_')}"] = value
    if "job_spec" in config and isinstance(config["job_spec"], str):
        config["job_spec"] = [config["job_spec"]]
    return config


def resolve_config_path(config_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def find_config_arg(argv: list[str]) -> str | None:
    for idx, item in enumerate(argv):
        if item == "--config" and idx + 1 < len(argv):
            return argv[idx + 1]
        if item.startswith("--config="):
            return item.split("=", 1)[1]
    return None


def particle_from_run_type(run_type: str) -> str:
    rt = run_type.strip().upper()
    if rt == "PI+SIDIS":
        return "pip"
    if rt == "PI-SIDIS":
        return "pim"
    raise ValueError(f"Cannot derive particle from run_type={run_type!r}")


def detect_simc_dir(given: str | None) -> Path:
    candidates = []
    if given:
        candidates.append(Path(given).expanduser())
    here = Path.cwd()
    script_dir = Path(__file__).resolve().parent
    candidates.extend([here, here.parent, here.parent.parent, script_dir.parent])

    for cand in candidates:
        cand = cand.resolve()
        if (cand / "run_simc_tree").exists() and (cand / "infiles").is_dir():
            return cand

    raise SystemExit(
        "ERROR: Could not find simc_gfortran. Pass --simc-dir pointing to the SIMC top directory."
    )


def validate_simc_dir(simc_dir: Path, create_worksim: bool) -> None:
    missing = []
    for rel in ["run_simc_tree", "infiles", "outfiles", "runout"]:
        if not (simc_dir / rel).exists():
            missing.append(rel)
    if missing:
        raise SystemExit(f"ERROR: {simc_dir} is missing required SIMC paths: {', '.join(missing)}")
    worksim = simc_dir / "worksim"
    if not worksim.exists():
        if create_worksim:
            print(f"Creating missing worksim directory: {worksim}")
            worksim.mkdir(parents=True, exist_ok=True)
        else:
            print(f"note     worksim directory does not exist yet: {worksim}")


def read_settings(path: Path) -> list[Kinematics]:
    rows: list[Kinematics] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "target",
            "ebeam",
            "hms_p",
            "hms_th",
            "shms_p",
            "shms_th",
            "x",
            "Q2",
            "z",
            "thpq",
            "run_type",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"ERROR: settings file is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            particle = particle_from_run_type(row["run_type"])
            rows.append(
                Kinematics(
                    target=row["target"].strip(),
                    particle=particle,
                    ebeam_gev=float(row["ebeam"]),
                    ebeam_raw=row["ebeam"].strip(),
                    hsp=abs(float(row["hms_p"])) * 1000.0,
                    hsth=float(row["hms_th"]),
                    ssp=abs(float(row["shms_p"])) * 1000.0,
                    ssth=float(row["shms_th"]),
                    x=float(row["x"]),
                    x_raw=row["x"].strip(),
                    q2=float(row["Q2"]),
                    q2_raw=row["Q2"].strip(),
                    z=float(row["z"]),
                    z_raw=row["z"].strip(),
                    thpq=float(row["thpq"]),
                    thpq_raw=row["thpq"].strip(),
                )
            )
    return rows


def select_kinematics(args: argparse.Namespace) -> list[Kinematics]:
    rows = read_settings(Path(args.settings).expanduser())
    selected = [
        row
        for row in rows
        if row.target == args.target
        and row.particle == args.particle
        and close(row.ebeam_gev, args.ebeam)
        and close(row.x, args.x)
        and (args.z is None or close(row.z, args.z))
        and (args.thpq is None or close(row.thpq, args.thpq))
    ]
    if not selected:
        raise SystemExit("ERROR: No settings rows matched the requested selection.")
    return selected


def valid_reactions(target: str, particle: str) -> list[str]:
    key = f"{target}_{particle}"
    if key not in REACTIONS:
        raise SystemExit(
            f"ERROR: No reaction map for {key}. Add it to REACTIONS in simcsubmit.py."
        )
    if target not in TARGET_PROPS:
        raise SystemExit(
            f"ERROR: No target properties for {target}. Add it to TARGET_PROPS in simcsubmit.py."
        )
    return REACTIONS[key]


def parse_job_specs(values: list[str] | None, target: str, particle: str) -> list[JobSpec]:
    reactions = valid_reactions(target, particle)
    if not values:
        return [JobSpec(rxn, 0, 1, DEFAULT_NGEN) for rxn in reactions]

    specs = []
    seen = set()
    for value in values:
        parts = value.split(":")
        if len(parts) != 4:
            raise SystemExit(
                f"ERROR: Bad --job-spec {value!r}. Expected reaction:firstjob:njobs:ngen"
            )
        reaction, firstjob, njobs, ngen = parts
        reaction = reaction.strip()
        if reaction not in reactions:
            raise SystemExit(
                f"ERROR: reaction {reaction!r} is not valid for {target}/{particle}. "
                f"Valid reactions: {', '.join(reactions)}"
            )
        if reaction in seen:
            raise SystemExit(f"ERROR: Duplicate --job-spec for reaction {reaction!r}")
        seen.add(reaction)
        specs.append(JobSpec(reaction, int(firstjob), int(njobs), int(ngen)))

    for spec in specs:
        if spec.firstjob < 0 or spec.njobs <= 0 or spec.ngen <= 0:
            raise SystemExit(f"ERROR: Invalid --job-spec values for {spec.reaction}")
    return specs


def make_stem(kin: Kinematics, reaction: str, jobid: int) -> str:
    return (
        f"bsa_{reaction}_{kin.target}_{kin.particle}"
        f"_e{tag(kin.ebeam_raw)}"
        f"_x{tag(kin.x_raw)}"
        f"_z{tag(kin.z_raw)}"
        f"_thpq{tag(kin.thpq_raw)}"
        f"_job{jobid}"
    )


def random_seed(used: set[int]) -> int:
    while True:
        seed = secrets.randbelow(MAX_RANDOM_SEED) + 1
        if seed not in used:
            used.add(seed)
            return seed


def build_jobs(args: argparse.Namespace) -> list[SimcJob]:
    rows = select_kinematics(args)
    specs = parse_job_specs(args.job_spec, args.target, args.particle)
    jobs: list[SimcJob] = []
    seeds: set[int] = set()
    for kin in rows:
        for spec in specs:
            for jobid in range(spec.firstjob, spec.firstjob + spec.njobs):
                jobs.append(
                    SimcJob(
                        kin=kin,
                        reaction=spec.reaction,
                        jobid=jobid,
                        ngen=spec.ngen,
                        stem=make_stem(kin, spec.reaction, jobid),
                        random_seed=random_seed(seeds),
                    )
                )
    return jobs


def infile_text(job: SimcJob) -> str:
    kin = job.kin
    targ = TARGET_PROPS[kin.target]
    flags = process_flags(job.reaction, kin.particle, kin.ebeam_gev * 1000.0, job.ngen)
    return f"""
; This is a CTP file

begin parm experiment
  ngen = {flags.ngen}	;  POS: # of successes; NEG: # of tries
  EXPER%charge = 1.0		;  total charge (mC)
  doing_phsp = 0		;  (ONE = TRUE)
  doing_kaon = 0		;  (ONE = TRUE)
  doing_pion = {flags.doing_pion}		;  (ONE = TRUE)
  which_pion = {flags.which_pion}		;  (0=p->pi+,1=n->pi-,10/11 for pi+/pi- coherent), 2=Delta+pi+ final state, 3=Delta+pi- final state)
  doing_rho = {flags.doing_rho}
  doing_decay = 1		;  1=decay ON, 0=decay OFF.
  ctau = 780.4			;  decay length (cm)
  random_seed = {job.random_seed}              ;  generated by simcsubmit
  doing_semi = {flags.doing_semi}
  doing_hplus = {flags.doing_hplus}
  doing_pizero = 0
  pizero_ngamma=2               ; 1=require at least 1 photon, 2=require both photons
end parm experiment

begin parm kinematics_main
  Ebeam = {kin.ebeam_gev * 1000.0}		;  (MeV)
  dEbeam = 0.05			;  beam energy variation (%)
  electron_arm = 1              ;  1=hms,2=sos,3=hrsr,4=hrsl,5=shms
  hadron_arm = 5                ;  1=hms,2=sos,3=hrsr,4=hrsl,5=shms,7=calo:BR,8=calo:BL
  spec%e%P = {kin.hsp}		;  e arm central momentum (MeV/c)
  spec%e%theta = {kin.hsth}		;  e arm angle setting (degrees)
  spec%p%P = {kin.ssp}		;  p arm central momentum (MeV/c)
  spec%p%theta = {kin.ssth}		;  p arm angle setting (degrees)
end parm kinematics_main

begin parm target
  targ%A = {targ.A}			;  target A
  targ%Z = {targ.Z}			;  target Z
  targ%mass_amu = {targ.mass_amu}	;  target mass in amu
  targ%mrec_amu = 0.		;  recoil mass in amu (eep=A-1 system,pion=A-2)
  targ%rho = {targ.rho}		;  target density (g/cm^3)
  targ%thick = {targ.thick}		;  target thick (mg/cm^2)
  targ%angle = 0.		;  target angle (for solid target) (degrees)
  targ%abundancy = 100.		;  target purity (%)
  targ%can = 3			;  1=beer can (fpi), 2=pudding can (nucpi),3=12GeV-style 10 cm cells
end parm target

begin parm debug		;  (ONES give helpful debug info)
  debug(1) = 0			;  turns on output from brem.f
  debug(2) = 0			;  into/outa subs.
  debug(3) = 0			;  spit out values (init. and main loop).
  debug(4) = 0			;  mostly comp_ev, gen_rad diagnostics.
  debug(5) = 0			;  a bit of everything.
end parm debug

begin parm e_arm_accept
  SPedge%e%delta%min = -11.0	;  delta min (SPECTROMETER ACCEPTANCE!)
  SPedge%e%delta%max =  11.0	;  delta max
  SPedge%e%yptar%min = -60.0	; .yptar.min = {{TF}} / 1000 (mrad)
  SPedge%e%yptar%max =  60.0	; .yptar.max = {{TF}} / 1000
  SPedge%e%xptar%min = -100.0	; .xptar.min = {{TF}} / 1000 (mrad)
  SPedge%e%xptar%max =  100.0	; .xptar.max = {{TF}} / 1000
end parm e_arm_accept

begin parm p_arm_accept
  SPedge%p%delta%min = -15.0	;  delta min (SPECTROMETER ACCEPTANCE!)
  SPedge%p%delta%max =  25.0	;  delta max
  SPedge%p%yptar%min = -70.0	; .yptar.min = {{TF}} / 1000 (mrad)
  SPedge%p%yptar%max =  70.0	; .yptar.max = {{TF}} / 1000
  SPedge%p%xptar%min = -70.0	; .xptar.min = {{TF}} / 1000 (mrad)
  SPedge%p%xptar%max =  70.0	; .xptar.max = {{TF}} / 1000
end parm p_arm_accept

begin parm beamandtargetinfo
  gen%xwid = 0.008868           ;  beam width - one sigma (cm)  (89microns)
  gen%ywid = 0.004235           ;  beam width - one sigma (cm)  (42microns)
  targ%fr_pattern = 3.          ;  raster pattern: 1=square, 2=circular, 3=triangular
  targ%fr1 = 0.1                ;  horizontal size OR inner radius(2)
  targ%fr2 = 0.1                ;  vertical size OR outer radius(2)
  targ%xoffset = 0.00           ;  target x-offset (cm): +x = beam right
  targ%yoffset = 0.0            ;  target y-offset (cm): +y = up
  targ%zoffset = 0.0            ;  target z-offset (cm): +z = downstream, zreal = znominal + zoffset
end parm beamandtargetinfo

begin parm spect_offset
  spec%e%offset%x = 0.0         ;  x offset (cm)
  spec%e%offset%y = 0.0         ;  y offset (cm)
  spec%e%offset%z = 0.          ;  z offset (cm)
  spec%e%offset%xptar = 0.0    ;  xptar offset (mr)
  spec%e%offset%yptar = 0.      ;  yptar offset (mr)
  spec%p%offset%x = 0.0         ;  x offset (cm)
  spec%p%offset%y = 0.0         ;  y offset (cm)
  spec%p%offset%z = 0.          ;  z offset (cm)
  spec%p%offset%xptar = 0.0    ;  xptar offset (mr)
  spec%p%offset%yptar = 0.      ;  yptar offset (mr)
end parm spect_offset

begin parm simulate
  hard_cuts = 0         ;  (ONE = TRUE) SPedge and Em.max are hard cuts(ntuple)
  using_rad = 1         ;  (ONE = TRUE)
  use_expon = 0         ;  (LEAVE AT 0)
  one_tail = 0          ;  0=all, 1=e, 2=e', 3=p, -3=all but p
  intcor_mode = 1       ;  (LEAVE AT 1)
  spect_mode = 0        ;  0=e+p arms, -1=p arm, -2=e arm only, 1=none
  cuts%Em%min = 0.      ;  (Em.min=Em.max=0.0 gives wide open cuts)
  cuts%Em%max = 0.      ;  Must be wider than cuts in analysis(elastic or e,e'p)
  using_Eloss = 1       ;  (ONE = TRUE)
  correct_Eloss = 0     ;  ONE = correct reconstructed events for eloss.
  correct_raster = 1    ;  ONE = Reconstruct events using 'raster' matrix elements.
  mc_smear = 1          ;  ONE = target & hut mult scatt AND DC smearing.
  deForest_flag = 0     ;  0=sigcc1, 1=sigcc2, -1=sigcc1 ONSHELL
  rad_flag = 0          ;  (radiative option #1...see init.f)
  extrad_flag = 2       ;  (rad. option #2...see init.f)
  lambda(1) = 0.0       ;  if rad_flag.eq.4 then lambda(1) = {{TF}}
  lambda(2) = 0.0       ;  if rad_flag.eq.4 then lambda(2) = {{TF}}
  lambda(3) = 0.0       ;  if rad_flag.eq.4 then lambda(3) = {{TF}}
  Nntu = 1              ;  ONE = generate ntuples
  using_Coulomb = 1     ;  (ONE = TRUE)
  dE_edge_test = 0.     ;  (move around energy edges)
  use_offshell_rad = 1  ;  (ONE = TRUE)
  Egamma_gen_max = {flags.egamma_max}   ;  Set >0 to hardwire the Egamma limits.
  drift_to_cal = 300.0  ;  distance to calorimeter (cm)
end parm simulate
""".lstrip()


def input_path(simc_dir: Path, stem: str) -> Path:
    return simc_dir / "infiles" / f"{stem}.inp"


def generate_infiles(jobs: Iterable[SimcJob], simc_dir: Path, dry_run: bool, overwrite: bool) -> None:
    for job in jobs:
        path = input_path(simc_dir, job.stem)
        if path.exists() and not overwrite:
            print(f"exists   {path}")
            continue
        action = "overwrite" if path.exists() else "create"
        if dry_run:
            action = f"would {action}"
        print(f"{action:<8} {path}  seed={job.random_seed}")
        if not dry_run:
            path.write_text(infile_text(job))


def run_ifarm_job(job: SimcJob, simc_dir: Path, outdir: Path, dry_run: bool, overwrite: bool) -> None:
    script = write_job_script(job, simc_dir, outdir, dry_run=dry_run, overwrite=overwrite)
    if dry_run:
        print(f"would run bash {script}")
        return
    subprocess.run(["bash", str(script)], check=True)


def write_job_script(
    job: SimcJob, simc_dir: Path, outdir: Path, dry_run: bool, overwrite: bool
) -> Path:
    jobs_dir = simc_dir / ".simcsubmit" / "jobs"
    script = jobs_dir / f"{job.stem}.sh"
    print(f"{'would write' if dry_run else 'write':<11} {script}")
    if dry_run:
        return script
    jobs_dir.mkdir(parents=True, exist_ok=True)
    py = Path(__file__).resolve()
    setup_env = py.parent / "setup_env.sh"
    overwrite_flag = " --overwrite-fweight" if overwrite else ""
    text = f"""#!/usr/bin/env bash
set -euo pipefail

SIMC_DIR={shquote(str(simc_dir))}
STEM={shquote(job.stem)}
OUTDIR={shquote(str(outdir))}
SETUP_ENV={shquote(str(setup_env))}

if [ -f "$SETUP_ENV" ]; then
  source "$SETUP_ENV"
fi

cd "$SIMC_DIR"

./simc <<EOF > "runout/${{STEM}}.out"
${{STEM}}
EOF

if [ ! -s "outfiles/${{STEM}}.hist" ]; then
  echo "ERROR: SIMC did not create outfiles/${{STEM}}.hist"
  echo "Last lines from runout/${{STEM}}.out:"
  tail -80 "runout/${{STEM}}.out" || true
  exit 1
fi

if [ ! -s "worksim/${{STEM}}.bin" ]; then
  echo "ERROR: SIMC did not create a non-empty worksim/${{STEM}}.bin"
  echo "Last lines from runout/${{STEM}}.out:"
  tail -80 "runout/${{STEM}}.out" || true
  exit 1
fi

cd "$SIMC_DIR/util/root_tree"
set +e
./make_root_tree <<EOF
${{STEM}}
EOF
TREE_STATUS=$?
set -e

cd "$SIMC_DIR"

if [ ! -s "worksim/${{STEM}}.root" ]; then
  echo "ERROR: make_root_tree did not create worksim/${{STEM}}.root"
  echo "make_root_tree exit status: $TREE_STATUS"
  exit 1
fi

if [ "$TREE_STATUS" -ne 0 ]; then
  echo "WARNING: make_root_tree exited with status $TREE_STATUS, but worksim/${{STEM}}.root exists; continuing"
fi

rm -f "worksim/${{STEM}}.bin"

python3 {shquote(str(py))} finish --simc-dir "$SIMC_DIR" --stem "$STEM" --outdir "$OUTDIR"{overwrite_flag}
"""
    script.write_text(text)
    script.chmod(0o755)
    return script


def shquote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def swif_workflow_name(args: argparse.Namespace) -> str:
    pieces = ["simc", args.target, args.particle, f"e{tag(args.ebeam)}", f"x{tag(args.x)}"]
    if args.z is not None:
        pieces.append(f"z{tag(args.z)}")
    if args.thpq is not None:
        pieces.append(f"thpq{tag(args.thpq)}")
    pieces.append(datetime.now().strftime("%Y%m%d"))
    return "_".join(pieces)


def run_cmd(cmd: list[str], dry_run: bool) -> None:
    printable = " ".join(shquote(c) if any(ch.isspace() for ch in c) else c for c in cmd)
    if dry_run:
        print(f"would run {printable}")
    else:
        print(f"run      {printable}")
        subprocess.run(cmd, check=True)


def submit_swif2(jobs: list[SimcJob], simc_dir: Path, outdir: Path, args: argparse.Namespace) -> None:
    workflow = args.workflow or swif_workflow_name(args)
    run_cmd(["swif2", "create", "-workflow", workflow], args.dry_run)
    for job in jobs:
        script = write_job_script(job, simc_dir, outdir, dry_run=args.dry_run, overwrite=args.overwrite_fweight)
        stdout = simc_dir / ".simcsubmit" / "logs" / f"{job.stem}.out"
        stderr = simc_dir / ".simcsubmit" / "logs" / f"{job.stem}.err"
        if not args.dry_run:
            stdout.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "swif2",
            "add-job",
            workflow,
            "-name",
            job.stem,
            "-cores",
            str(args.swif_cores),
            "-ram",
            args.swif_ram,
            "-disk",
            args.swif_disk,
            "-time",
            args.swif_time,
            "-partition",
            args.swif_partition,
            "-stdout",
            str(stdout),
            "-stderr",
            str(stderr),
            "-shell",
            "/bin/bash",
            str(script),
        ]
        run_cmd(cmd, args.dry_run)
    if args.no_run:
        print(f"workflow created but not started: {workflow}")
    else:
        run_cmd(["swif2", "run", workflow], args.dry_run)


def read_simc_histfile(histfile: Path) -> dict[str, str]:
    regex = re.compile(r"\s+([A-Za-z\s{}()/_\.>]+)\s+=\s+([0-9E+\?.-]+)")
    result = {}
    for line in histfile.read_text(errors="replace").splitlines():
        if "GeV^2" in line:
            continue
        match = regex.findall(line)
        if match:
            result[match[0][0].strip()] = match[0][1]
    return result


def norm_factor(histfile: Path) -> float:
    entries = read_simc_histfile(histfile)
    normfac = float(entries.get("normfac", 0))
    ngenrequest = float(entries.get("Ngen (request)", 0))
    if ngenrequest == 0:
        raise SystemExit(f"ERROR: Could not read Ngen (request) from {histfile}")
    return normfac / ngenrequest


def add_fweight(simc_dir: Path, stem: str, overwrite: bool) -> Path:
    histfile = simc_dir / "outfiles" / f"{stem}.hist"
    rootfile = simc_dir / "worksim" / f"{stem}.root"
    weighted = simc_dir / "worksim" / f"wfWeight_{stem}.root"
    if weighted.exists() and not overwrite:
        print(f"exists   {weighted}")
        if rootfile.exists():
            print(f"remove   {rootfile}")
            rootfile.unlink()
        return weighted
    if not histfile.exists():
        raise SystemExit(f"ERROR: missing hist file: {histfile}")
    if not rootfile.exists():
        raise SystemExit(f"ERROR: missing root file: {rootfile}")
    fnorm = norm_factor(histfile)
    macro = Path(__file__).resolve().parent / "add_fWeight.cpp"
    print(f"fWeight  {rootfile}  norm={fnorm}")
    subprocess.run(["root", "-l", "-b", "-q", "-n", f'{macro}("{rootfile}",{fnorm})'], check=True)
    if not weighted.exists():
        raise SystemExit(f"ERROR: fWeight macro did not create {weighted}")
    print(f"remove   {rootfile}")
    rootfile.unlink()
    return weighted


def move_outputs(simc_dir: Path, stem: str, outdir: Path, dry_run: bool) -> None:
    root_sources = [
        simc_dir / "worksim" / f"wfWeight_{stem}.root",
    ]
    simcout_sources = [
        simc_dir / "infiles" / f"{stem}.inp",
        simc_dir / "runout" / f"{stem}.out",
    ]
    outfile_sources = sorted((simc_dir / "outfiles").glob(f"{stem}*"))
    simcout_dir = outdir / "simcout"
    if dry_run:
        print(f"would mkdir {outdir}")
        print(f"would mkdir {simcout_dir}")
    else:
        outdir.mkdir(parents=True, exist_ok=True)
        simcout_dir.mkdir(parents=True, exist_ok=True)
    for src in root_sources:
        move_one(src, outdir, dry_run)
    for src in simcout_sources:
        move_one(src, simcout_dir, dry_run)
    if outfile_sources:
        for src in outfile_sources:
            move_one(src, simcout_dir, dry_run)
    else:
        print(f"missing   {simc_dir / 'outfiles' / f'{stem}*'}")


def move_one(src: Path, dst_dir: Path, dry_run: bool) -> None:
    if dry_run:
        dst = dst_dir / src.name
        print(f"would move {src} -> {dst}")
        return
    if src.exists():
        dst = dst_dir / src.name
        print(f"{'move':<10} {src} -> {dst}")
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))
    else:
        print(f"missing   {src}")


def finish_stems(stems: Iterable[str], simc_dir: Path, outdir: Path, args: argparse.Namespace) -> None:
    for stem in stems:
        if args.dry_run:
            print(f"would add fWeight for {stem}")
            print(f"would remove {simc_dir / 'worksim' / f'{stem}.root'}")
        else:
            add_fweight(simc_dir, stem, overwrite=args.overwrite_fweight)
        move_outputs(simc_dir, stem, outdir, args.dry_run)


def print_plan(jobs: list[SimcJob], simc_dir: Path) -> None:
    by_z: dict[str, dict[str, list[SimcJob]]] = {}
    for job in jobs:
        by_z.setdefault(job.kin.z_raw, {}).setdefault(job.kin.thpq_raw, []).append(job)
    rows = {(j.kin.target, j.kin.particle, j.kin.ebeam_raw, j.kin.x_raw, j.kin.z_raw, j.kin.thpq_raw) for j in jobs}
    print(f"SIMC directory: {simc_dir}")
    print(f"Selected {len(rows)} kinematic rows")
    print(f"Will create/use {len(jobs)} SIMC jobs")
    for z_value in sorted(by_z, key=float):
        print(f"\nz={z_value}")
        for thpq_value in sorted(by_z[z_value], key=float):
            group = by_z[z_value][thpq_value]
            reactions = ", ".join(f"{j.reaction}:job{j.jobid}:ngen{j.ngen}" for j in group)
            print(f"  thpq={thpq_value}: {reactions}")


def add_selection_args(parser: argparse.ArgumentParser, require_settings: bool = True) -> None:
    parser.add_argument("--settings", help="CSV settings file")
    parser.add_argument("--target", help="Target, e.g. LH2")
    parser.add_argument("--particle", choices=["pip", "pim"])
    parser.add_argument("--ebeam", type=float, help="Beam energy in GeV")
    parser.add_argument("--x", type=float, help="Bjorken x")
    parser.add_argument("--z", type=float, help="Optional z selector")
    parser.add_argument("--thpq", type=float, help="Optional thpq selector")
    parser.add_argument(
        "--job-spec",
        action="append",
        help="Repeatable reaction:firstjob:njobs:ngen. If provided, only listed reactions are used.",
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="YAML or JSON campaign config")
    parser.add_argument("--simc-dir", help="Top-level simc_gfortran directory")
    parser.add_argument("--dry-run", action="store_true", default=None)


def add_output_args(parser: argparse.ArgumentParser, required: bool = True) -> None:
    parser.add_argument("--outdir", help="Directory to move completed outputs into")


def require_args(args: argparse.Namespace, names: list[str]) -> None:
    missing = [name for name in names if getattr(args, name, None) is None]
    if missing:
        formatted = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        raise SystemExit(f"ERROR: missing required argument(s): {formatted}")


def apply_config(args: argparse.Namespace, config: dict) -> None:
    for key, value in config.items():
        if not hasattr(args, key):
            continue
        if getattr(args, key) is None:
            setattr(args, key, value)


def apply_hardcoded_defaults(args: argparse.Namespace) -> None:
    if getattr(args, "dry_run", None) is None:
        args.dry_run = False
    if getattr(args, "backend", None) is None:
        args.backend = DEFAULT_BACKEND
    for key, value in SWIF_DEFAULTS.items():
        attr = f"swif_{key}"
        if getattr(args, attr, None) is None:
            setattr(args, attr, value)
    for attr in ["no_run", "overwrite_infiles", "overwrite_fweight"]:
        if hasattr(args, attr) and getattr(args, attr, None) is None:
            setattr(args, attr, False)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Generate, submit, and finish SIMC jobs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Show selected jobs without writing anything")
    add_common_args(p_plan)
    add_selection_args(p_plan)

    p_gen = sub.add_parser("generate", help="Create missing SIMC input files")
    add_common_args(p_gen)
    add_selection_args(p_gen)
    p_gen.add_argument("--overwrite-infiles", action="store_true", default=None)

    p_submit = sub.add_parser("submit", help="Generate inputs and run/submit jobs")
    add_common_args(p_submit)
    add_selection_args(p_submit)
    add_output_args(p_submit)
    p_submit.add_argument("--backend", choices=["ifarm", "swif2"])
    p_submit.add_argument("--workflow", help="SWIF2 workflow name")
    p_submit.add_argument(
        "--no-run",
        action="store_true",
        default=None,
        help="For SWIF2: add jobs but do not start workflow",
    )
    p_submit.add_argument("--overwrite-infiles", action="store_true", default=None)
    p_submit.add_argument("--overwrite-fweight", action="store_true", default=None)
    p_submit.add_argument("--swif-disk")
    p_submit.add_argument("--swif-ram")
    p_submit.add_argument("--swif-time")
    p_submit.add_argument("--swif-partition")
    p_submit.add_argument("--swif-cores", type=int)

    p_finish = sub.add_parser("finish", help="Add fWeight and move outputs")
    add_common_args(p_finish)
    p_finish.add_argument("--stem", action="append", help="Specific SIMC stem to finish; repeatable")
    add_selection_args(p_finish, require_settings=False)
    add_output_args(p_finish)
    p_finish.add_argument("--overwrite-fweight", action="store_true", default=None)

    p_all = sub.add_parser("all", help="Generate, run locally on ifarm, add fWeight, and move outputs")
    add_common_args(p_all)
    add_selection_args(p_all)
    add_output_args(p_all)
    p_all.add_argument("--overwrite-infiles", action="store_true", default=None)
    p_all.add_argument("--overwrite-fweight", action="store_true", default=None)

    config_defaults = load_config(find_config_arg(argv))
    args = parser.parse_args(argv)
    apply_config(args, config_defaults)
    apply_hardcoded_defaults(args)
    if args.command in {"plan", "generate", "submit", "all"}:
        require_args(args, ["settings", "target", "particle", "ebeam", "x"])
    if args.command in {"submit", "all"}:
        require_args(args, ["outdir"])
    if args.command == "finish":
        require_args(args, ["outdir"])
        if not args.stem:
            if args.settings:
                require_args(args, ["target", "particle", "ebeam", "x"])
            else:
                require_args(args, ["stem"])

    simc_dir = detect_simc_dir(args.simc_dir)
    create_worksim = args.command in {"submit", "all"} and not args.dry_run
    validate_simc_dir(simc_dir, create_worksim=create_worksim)

    if args.command == "finish" and args.stem:
        finish_stems(args.stem, simc_dir, Path(args.outdir).expanduser(), args)
        return 0

    if args.command == "finish" and not args.settings:
        raise SystemExit("ERROR: finish requires either --stem or a full settings selection.")

    jobs = build_jobs(args)

    if args.command == "plan":
        print_plan(jobs, simc_dir)
        return 0

    if args.command == "generate":
        generate_infiles(jobs, simc_dir, args.dry_run, args.overwrite_infiles)
        return 0

    if args.command == "submit":
        generate_infiles(jobs, simc_dir, args.dry_run, args.overwrite_infiles)
        if args.backend == "ifarm":
            for job in jobs:
                run_ifarm_job(
                    job,
                    simc_dir,
                    Path(args.outdir).expanduser(),
                    dry_run=args.dry_run,
                    overwrite=args.overwrite_fweight,
                )
        else:
            submit_swif2(jobs, simc_dir, Path(args.outdir).expanduser(), args)
        return 0

    if args.command == "finish":
        finish_stems((job.stem for job in jobs), simc_dir, Path(args.outdir).expanduser(), args)
        return 0

    if args.command == "all":
        args.backend = "ifarm"
        generate_infiles(jobs, simc_dir, args.dry_run, args.overwrite_infiles)
        for job in jobs:
            run_ifarm_job(
                job,
                simc_dir,
                Path(args.outdir).expanduser(),
                dry_run=args.dry_run,
                overwrite=args.overwrite_fweight,
            )
        return 0

    raise SystemExit(f"ERROR: unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
