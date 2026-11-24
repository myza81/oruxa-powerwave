# Independent arithmetic for the PU-MIG-001 assessment. Pure Python, no repo imports.
from math import sqrt
S3 = sqrt(3)
def pr(label, v, unit=""):
    print(f"{label:<62s}{v:>16.6f} {unit}")

print("== A. Voltage, system 275 kV LL, VT 275 kV/110 V (ratio 2500) ==")
Vll=275e3; Rvt=275e3/110.0
base_ln_p = Vll/S3
pr("A1 primary L-N sample 158 771 V / base_ln_primary", (Vll/S3)/base_ln_p, "pu")
sec_ln = (Vll/S3)/Rvt
pr("A2 secondary L-N sample (V)", sec_ln, "V")
base_ln_s = base_ln_p/Rvt
pr("A2 secondary denominator = base_ln_primary / ratio (V)", base_ln_s, "V")
pr("A2 pu", sec_ln/base_ln_s, "pu")
pr("A3 secondary sample / PRIMARY base (today's silent-wrong case)", sec_ln/base_ln_p, "pu")
pr("A4 secondary L-L sample (V)", Vll/Rvt, "V")
pr("A4 pu vs (Vll/ratio)", (Vll/Rvt)/(Vll/Rvt), "pu")

print("\n== B. VT primary != system nominal: nominal 132 kV, VT 138 kV/110 V ==")
Vn=132e3; Rb=138e3/110.0
sec_ll=(Vn/Rb)
pr("B1 secondary L-L at nominal system voltage (V)", sec_ll, "V")
pr("B1 correct denominator = Vn/ratio (V)", Vn/Rb, "V")
pr("B1 pu using Vn/ratio", sec_ll/(Vn/Rb), "pu")
pr("B1 pu if denominator were vt_secondary (110 V) -- WRONG", sec_ll/110.0, "pu")
pr("B1 error vs 1.0", sec_ll/110.0-1.0, "pu")

print("\n== C. Current: S=1000 MVA, 275 kV -> Ibase ==")
Sb=1000e6
Ib=Sb/(S3*Vll)
pr("C0 Ibase primary", Ib, "A")
CT=2000.0
pr("C1 primary current sample at 1.0 pu (A)", Ib, "A")
pr("C1 pu", Ib/Ib, "pu")
I_sec=Ib/CT
pr("C2 secondary sample at 1.0 pu (A)", I_sec, "A")
pr("C2 denominator Ibase/CT (A)", Ib/CT, "A")
pr("C2 pu", I_sec/(Ib/CT), "pu")
pr("C3 secondary sample 1.0 A / primary base (wrong)", 1.0/Ib, "pu")
pr("C3 secondary 1.0 A / (Ibase/CT)", 1.0/(Ib/CT), "pu")
pr("C3 equivalent: (1.0*CT)/Ibase", 1.0*CT/Ib, "pu")

print("\n== D. Mixed: primary voltage (kV) + secondary current (A) ==")
V_kv=158.771; I_a=1.0
pr("D1 Vpu = V_primary/base_ln_primary", V_kv*1e3/base_ln_p, "pu")
pr("D1 Ipu (secondary current, CT 2000:1) = I/(Ibase/CT)", I_a/(Ib/CT), "pu")
print("   voltage side never changes the current denominator; Ibase is built from NOMINAL LL (primary) only.")

print("\n== E. Mixed: secondary voltage (V) + primary current (A) ==")
pr("E1 Vpu = 63.508/(base_ln_primary/ratio)", 63.508/base_ln_s, "pu")
pr("E1 Ipu (primary) = 2099.6/Ibase", 2099.6/Ib, "pu")

print("\n== F. Manual bases ==")
print("F1 manual Ibase 2.1 kA declared PRIMARY, secondary current recorded, CT 4000:1")
pr("   denominator = 2100/4000 (A)", 2100/4000.0, "A")
pr("   I_sec 0.525 A -> pu", 0.525/(2100/4000.0), "pu")
print("F2 manual Ibase 1.0 A declared SECONDARY, secondary recorded: direct, no CT")
pr("   0.5 A / 1.0 A", 0.5/1.0, "pu")
print("F3 manual Ibase 1.0 A declared SECONDARY, PRIMARY recorded, CT 2000:1")
pr("   denominator = 1.0 A * 2000 = (A primary)", 1.0*2000, "A")
pr("   I_prim 1000 A -> pu", 1000/(1.0*2000), "pu")
print("F4 manual Ibase side UNKNOWN: no sound denominator; block (or legacy Unverified)")

print("\n== G. Calculated: L-L voltage from secondary L-N legs ==")
va=63.508; vb=63.508
import cmath
Va=cmath.rect(va,0); Vb=cmath.rect(vb,-2*3.141592653589793/3)
vab=abs(Va-Vb)
pr("G1 |Va-Vb| secondary (V)", vab, "V")
pr("G1 LL denominator = Vll/ratio (V)", Vll/Rvt, "V")
pr("G1 pu", vab/(Vll/Rvt), "pu")
pr("G1 pu vs PRIMARY LL base (silent wrong today if side Unknown)", vab/Vll, "pu")

print("\n== H. Equivalence: primary and secondary measurement of same condition ==")
for k in (0.0, 0.5, 0.87, 1.0, 1.1):
    p=(Vll/S3)*k
    s=p/Rvt
    assert abs(p/base_ln_p - s/base_ln_s) < 1e-15, k
print("H  PASS: pu_primary == pu_secondary for k in {0,0.5,0.87,1.0,1.1}")
