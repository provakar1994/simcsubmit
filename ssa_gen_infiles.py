def infile_template(process_flags, kinematics, target_props, outfile):
    infile_text = (f"""
; This is a CTP file

begin parm experiment
  ngen = {process_flags.ngen}	;  POS: # of successes; NEG: # of tries
  EXPER%charge = 1.0		;  total charge (mC)
  doing_phsp = 0		;  (ONE = TRUE)
  doing_kaon = 0		;  (ONE = TRUE)
  doing_pion = {process_flags.doing_pion}		;  (ONE = TRUE)
  which_pion = {process_flags.which_pion}		;  (0=p->pi+,1=n->pi-,10/11 for pi+/pi- coherent), 2=Delta+pi+ final state, 3=Delta+pi- final state)
  doing_rho = {process_flags.doing_rho}
  doing_decay = 1		;  1=decay ON, 0=decay OFF.
  ctau = 780.4			;  decay length (cm)
  doing_semi = {process_flags.doing_semi}
  doing_hplus = {process_flags.doing_hplus}
  doing_pizero = 0
  pizero_ngamma=2               ; 1=require at least 1 photon, 2=require both photons
end parm experiment

begin parm kinematics_main
  Ebeam = {kinematics.ebeam}		;  (MeV)
  dEbeam = 0.05			;  beam energy variation (%)
  electron_arm = 1              ;  1=hms,2=sos,3=hrsr,4=hrsl,5=shms
  hadron_arm = 5                ;  1=hms,2=sos,3=hrsr,4=hrsl,5=shms,7=calo:BR,8=calo:BL
  spec%e%P = {kinematics.hsp}		;  e arm central momentum (MeV/c)
  spec%e%theta = {kinematics.hsth}		;  e arm angle setting (degrees)
  spec%p%P = {kinematics.ssp}		;  p arm central momentum (MeV/c)
  spec%p%theta = {kinematics.ssth}		;  p arm angle setting (degrees)
end parm kinematics_main

begin parm target
  targ%A = {target_props.A}			;  target A
  targ%Z = {target_props.Z}			;  target Z
  targ%mass_amu = {target_props.mass_amu}	;  target mass in amu
  targ%mrec_amu = 0.		;  recoil mass in amu (eep=A-1 system,pion=A-2)
  targ%rho = {target_props.rho}		;  target density (g/cm^3)
  targ%thick = {target_props.thick}		;  target thick (mg/cm^2)
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
end parm beamandtergetinfo

;These are offsets applied before the call to the single arm montecarlos.
; Offsets are in spectrometer coordinate system.  Positive xptar offset
; means spectrometer is positioned at large xptar (i.e. below target, and
; thus pointing above target and giving a negative shift to particle's xptar)
begin parm spect_offset
  spec%e%offset%x = 0.0         ;  x offset (cm)
  spec%e%offset%y = 0.0         ;  y offset (cm)
  spec%e%offset%z = 0.          ;  z offset (cm)
  spec%e%offset%xptar = 0.0    ;  xptar offset (mr)    !x(y)ptar is slope, so
  spec%e%offset%yptar = 0.      ;  yptar offset (mr)    !it's really unitless.
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
  Egamma_gen_max = {process_flags.egamma_max}   ;  Set >0 to hardwire the Egamma limits.
  drift_to_cal = 300.0  ;  distance to calorimeter (cm)
end parm simulate
""")
    with open(outfile, 'w') as f:
        f.write(infile_text)    
    #print(infile_text)

from dataclasses import dataclass

@dataclass
class kinematics:
    target   : str
    particle : str   # pip/pim
    ebeam    : float # MeV
    hsp      : float # MeV/c  
    hsth     : float # deg
    ssp      : float # MeV/c
    ssth     : float # deg
    x        : float
    Q2       : float
    z        : float
    thpq     : float    

@dataclass
class TargetProps:
    A: float
    Z: float
    mass_amu: float
    rho: float
    thick: float    

@dataclass
class ProcessFlags:
    doing_pion : int
    which_pion : int
    doing_semi : int
    doing_hplus: int
    doing_rho  : int
    egamma_max : float
    ngen       : int

def fill_kin_info(row):
    kin = kinematics(
        row['target'],
        "pip" if (row['run_type']=="PI+SIDIS") else "pim",
        row['ebeam']*1e3,
        abs(row['hms_p'])*1e3,
        row['hms_th'],
        abs(row['shms_p'])*1e3,
        row['shms_th'],
        row['x'],
        row['Q2'],
        row['z'],
        row['thpq'],
        )
    return kin

def fill_info(ebeam, target, particle):
    
    target_props = {
        "LH2" : TargetProps(1., 1., 1.007276, 0.0759, 759.0),
        "LD2" : TargetProps(2., 1., 2.014102, 0.16743, 1674.3),
        "C"   : TargetProps(12.0, 6.0, 12.011, 2.7, 1072),
        "Cu"  : TargetProps(64.0, 29.0, 64.0, 8.96, 760),
    }
    
    process_flags = {
        "sidis_pip" : ProcessFlags(1, 0, 1, 1, 0, ebeam, 100000),
        "sidis_pim" : ProcessFlags(1, 1, 1, 0, 0, ebeam, 100000),
        "excl_pip"  : ProcessFlags(1, 0, 0, 1, 0, ebeam, 100000),
        "excl_pim"  : ProcessFlags(1, 1, 0, 0, 0, ebeam, 100000),
        "delta_pip" : ProcessFlags(1, 2, 0, 1, 0, ebeam, 100000),
        "delta_pim" : ProcessFlags(1, 3, 0, 0, 0, ebeam, 100000),        
        "rho"       : ProcessFlags(0, 0, 0, 1, 1, ebeam, 100000),
    }

    reactions = {
        "LH2_pip"   : ["sidis_pip", "excl_pip", "delta_pip", "rho"],
        "LH2_pim"   : ["sidis_pim", "delta_pim", "rho"],
        "LD2_pip"   : ["sidis_pip", "excl_pip", "delta_pip", "rho"],
        "LD2_pim"   : ["sidis_pim", "excl_pim", "delta_pim", "rho"],
        "C_pip"     : ["sidis_pip", "excl_pip", "delta_pip", "rho"],
        "C_pim"     : ["sidis_pim", "excl_pim", "delta_pim", "rho"],
        "Cu_pip"    : ["sidis_pip", "excl_pip", "delta_pip", "rho"],
        "Cu_pim"    : ["sidis_pim", "excl_pim", "delta_pim", "rho"],                
    }

    return target_props[target], process_flags, reactions[f"{target}_{particle}"]

#print(targets["C"].rho)

# a, b, c = fill_info(10.7, "LH2", "pip")

# print(b[c[1]])

import pandas as pd

settings = pd.read_csv("rpr1_all_settings.csv")
settings = settings[(settings['target'] == "LH2")
                    & (settings['z'] == 0.36)
                    & (settings['run_type'] == "PI+SIDIS")]
#print(settings.head())

# Loop over settings row:
#   fill kinematics
#   fill_info(kinematics)
# loop over reactions:
#   generate_infle(process_flags[reaction], kinematics, target_props)

for index, row in settings.iterrows():
    kin = fill_kin_info(row)
    targprop, processflag, reactions = fill_info(kin.ebeam, kin.target, kin.particle)
    for reaction in reactions:
        print("=======================")
        print(f"======= {kin.target} | {kin.particle} | {reaction} ========")
        pros = reaction.split('_')[0]
        x = "x" + str(kin.x).replace(".", "p")
        q2 = "q2" + str(kin.Q2).replace(".", "p")
        z = "z" + str(kin.z).replace(".", "p")
        thpq = ("thpq" + str(kin.thpq).replace(".", "p")).replace("-", "m")
        outfile = f"bsa_{pros}_{kin.target}_{kin.particle}_e10p7_{x}_{z}_{thpq}.inp"
        print(outfile)
        infile_template(processflag[reaction], kin, targprop, outfile)
        print("=======================")
