# simcsubmit

Small helper for generating, submitting, finishing, and moving SIMC jobs.

Clone or copy this directory inside a `simc_gfortran` checkout:

```text
simc_gfortran/
  simcsubmit/
    config/
    settings/
```

You can also keep it elsewhere and pass `--simc-dir /path/to/simc_gfortran`.

## Basic Use

From inside `simc_gfortran/simcsubmit`:

Preview the fan-out:

```bash
python3 simcsubmit.py plan \
  --settings settings/rpr1_all_settings.csv \
  --target LH2 \
  --particle pim \
  --ebeam 10.6716 \
  --x 0.25
```

Create missing input files only:

```bash
python3 simcsubmit.py generate \
  --settings settings/rpr1_all_settings.csv \
  --target LH2 \
  --particle pim \
  --ebeam 10.6716 \
  --x 0.25
```

Run directly from ifarm:

```bash
python3 simcsubmit.py submit \
  --backend ifarm \
  --settings settings/rpr1_all_settings.csv \
  --target LH2 \
  --particle pim \
  --ebeam 10.6716 \
  --x 0.25 \
  --outdir /path/to/output
```

Submit to SWIF2:

```bash
python3 simcsubmit.py submit \
  --backend swif2 \
  --settings settings/rpr1_all_settings.csv \
  --target LH2 \
  --particle pim \
  --ebeam 10.6716 \
  --x 0.25 \
  --workflow simc_LH2_pim_x0p25 \
  --outdir /path/to/output
```

Dry-run any command:

```bash
python3 simcsubmit.py submit ... --dry-run
```

## YAML Config

For repeated campaigns, put the common options in a YAML file:

```yaml
settings: ../settings/rpr1_all_settings.csv
simc_dir: ../..

target: LH2
particle: pim
ebeam: 10.6716
x: 0.25

backend: swif2
workflow: simc_LH2_pim_x0p25
outdir: /path/to/output

job_spec:
  - sidis:1:10:100000
  - rho:1:5:50000

swif:
  disk: 4GB
  ram: 2GB
  time: 2h
  partition: production
  cores: 1
```

Then run:

```bash
python3 simcsubmit.py plan --config config/example_campaign.yaml
python3 simcsubmit.py submit --config config/example_campaign.yaml --dry-run
```

Defaults are applied in this order:

```text
hardcoded defaults < YAML config < command-line arguments
```

So this uses the YAML campaign but changes the workflow just for this run:

```bash
python3 simcsubmit.py submit --config config/example_campaign.yaml --workflow test_run --dry-run
```

Relative `settings`, `simc_dir`, and `outdir` paths in YAML are resolved from
the YAML file's directory.

## Selection

Required selectors:

```text
--target
--particle
--ebeam
--x
```

Optional selectors:

```text
--z
--thpq
```

If `--z` or `--thpq` are omitted, all matching rows from the CSV are used.
The script uses actual CSV rows, not a blind Cartesian product.

## Reactions

Reactions are chosen from target and particle. For example, `LH2/pim` uses:

```text
sidis, delta, rho
```

There is no `excl` for `LH2/pim`.

## Adding Statistics

By default, each selected reaction gets one job:

```text
job0, ngen=100000
```

Use `--job-spec` for explicit top-ups:

```bash
python3 simcsubmit.py submit \
  --settings settings/rpr1_all_settings.csv \
  --target LH2 \
  --particle pip \
  --ebeam 10.6716 \
  --x 0.25 \
  --job-spec sidis:1:10:100000 \
  --job-spec rho:1:5:50000 \
  --outdir /path/to/output
```

Format:

```text
reaction:firstjob:njobs:ngen
```

If any `--job-spec` is provided, only the listed reactions are generated.

## Random Seeds

Each generated input file gets an explicit positive `random_seed` from OS
randomness. Multiple jobs in the same command are also checked for duplicate
seeds before the input files are written.

## SWIF2 Options

Defaults:

```text
--swif-disk 4GB
--swif-ram 2GB
--swif-time 2h
--swif-partition production
--swif-cores 1
```

Useful extras:

```text
--workflow NAME
--no-run
```

`--no-run` creates the workflow and adds jobs, but does not start it.

## Environment

Generated job scripts source this file if it exists:

```text
simc_gfortran/simcsubmit/setup_env.sh
```

Put any needed ifarm/SWIF2 setup there, such as `module load root` or experiment
setup scripts. SIMC and `util/root_tree/make_root_tree` should be built before
large submissions.

## Output Layout

After `finish`, the weighted ROOT file is moved directly into `--outdir`.
The original unweighted ROOT file is removed after the fWeight file is created:

```text
outdir/wfWeight_<stem>.root
```

SIMC text/log/input files are moved into `--outdir/simcout`:

```text
outdir/simcout/<stem>.inp
outdir/simcout/<stem>.out
outdir/simcout/<stem>.hist
outdir/simcout/<stem>.gen
outdir/simcout/<stem>.geni
```
