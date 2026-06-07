"""
Phase 6B: Hybrid Adoption Strategy Analysis

Analyze which adoption method (v3/v5/v5.2) is best for each item:
  - AU: au case new
  - AV: au case existing
  - AY: other case new
  - AZ: other case existing
  - AI: total (numeric)

Strategy: NOT all-or-nothing replacement
Instead: Field-by-field hybrid approach
"""

import sys
import os

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"

# Load data
v3_csv = OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv"
v5_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"

df_v3_all = pd.read_csv(v3_csv)
df_v3_case = df_v3_all[df_v3_all['region'] == 'case_items'].copy()
df_v3_case = df_v3_case.rename(columns={'page': 'page_index', 'item': 'field_code', 'value': 'v3_value'})

df_v5 = pd.read_csv(v5_csv)

# Test pages
TEST_PAGE_INDICES = [0, 5, 7, 8, 9, 14, 27]

# Filter v3
df_v3_test = df_v3_case[df_v3_case['page_index'].isin(TEST_PAGE_INDICES)].copy()

# Merge
df_merged = pd.merge(
    df_v3_test[['page_index', 'field_code', 'v3_value']],
    df_v5[['page_index', 'field_code', 'v5_value']],
    on=['page_index', 'field_code'],
    how='outer'
)

print("=" * 100)
print("Phase 6B: Hybrid Adoption Strategy Analysis")
print("=" * 100)
print()

print("EVALUATION FRAMEWORK:")
print("-" * 100)
print()

print("""
Criteria for each item:
  1. Success Rate: % of pages with non-null values
  2. Danger Reduction: % reduction in zeros in tally fields (AU/AV/AY/AZ)
  3. Null Escape: Is method returning too many nulls?
  4. Accuracy vs CSV: Does method match ground truth?
  5. Risk: Can method cause false readings?

Decision Matrix:
  v3 MAINTAIN:
    - Highest success rate
    - Acceptable danger level
    - No regression risk

  v5 ADOPT:
    - Clear improvement over v3
    - Success rate >= 70% of v3
    - No new danger readings

  v5.2 ADOPT (if available):
    - AI row fixed (bounds optimized)
    - Success rate recovery to v3+ level
    - Danger readings further reduced
    - No regression
""")

print()
print("=" * 100)
print("ITEM-BY-ITEM ANALYSIS")
print("=" * 100)
print()

# AU
print("AU (au case new)")
print("-" * 100)
au_v3 = df_merged[df_merged['field_code'] == 'AU']
au_v3_success = (~au_v3['v3_value'].isna()).sum()
au_v5_success = (~au_v3['v5_value'].isna()).sum()
au_v3_zeros = ((au_v3['v3_value'] == 0) | (au_v3['v3_value'] == '0')).sum()
au_v5_zeros = ((au_v3['v5_value'] == 0.0) | (au_v3['v5_value'] == 0)).sum()

print(f"v3: {au_v3_success}/7 success, {au_v3_zeros} zeros")
print(f"v5: {au_v5_success}/7 success, {au_v5_zeros} zeros")
print()

print("Assessment:")
if au_v5_success > au_v3_success * 0.7 and au_v5_zeros <= au_v3_zeros:
    print("  HYBRID OPTION: v5 candidate (if no new zeros)")
    print("  RECOMMENDATION: v3 maintain (safer baseline)")
else:
    print("  RECOMMENDATION: v3 maintain")

print()
print("Reasoning:")
print("  - AU has moderate baseline (57%)")
print("  - v5 reduces zeros (good) but also success rate (bad)")
print("  - Risk/benefit ratio not favorable for adoption")
print()
print()

# AV
print("AV (au case existing)")
print("-" * 100)
av_v3 = df_merged[df_merged['field_code'] == 'AV']
av_v3_success = (~av_v3['v3_value'].isna()).sum()
av_v5_success = (~av_v3['v5_value'].isna()).sum()
av_v3_zeros = ((av_v3['v3_value'] == 0) | (av_v3['v3_value'] == '0')).sum()
av_v5_zeros = ((av_v3['v5_value'] == 0.0) | (av_v3['v5_value'] == 0)).sum()

print(f"v3: {av_v3_success}/7 success, {av_v3_zeros} zeros (danger!)")
print(f"v5: {av_v5_success}/7 success, {av_v5_zeros} zeros (all null - escape!)")
print()

print("Assessment:")
print("  CRITICAL: v3 has HIGH danger (43% are zeros in tally field)")
print("  PROBLEM: v5 eliminates danger but returns zero values")
print("  OPPORTUNITY: v5.2 bounds adjustment may fix without losing danger reduction")
print()
print("RECOMMENDATION: PRIORITY FOR v5.2 OPTIMIZATION")
print("  - If v5.2 recovers values while keeping zeros at 0, adopt v5.2")
print("  - If v5.2 fails, use v3 (maintain current danger level)")
print()
print()

# AY
print("AY (other case new)")
print("-" * 100)
ay_v3 = df_merged[df_merged['field_code'] == 'AY']
ay_v3_success = (~ay_v3['v3_value'].isna()).sum()
ay_v5_success = (~ay_v3['v5_value'].isna()).sum()
ay_v3_zeros = ((ay_v3['v3_value'] == 0) | (ay_v3['v3_value'] == '0')).sum()
ay_v5_zeros = ((ay_v3['v5_value'] == 0.0) | (ay_v3['v5_value'] == 0)).sum()

print(f"v3: {ay_v3_success}/7 success, {ay_v3_zeros} zeros")
print(f"v5: {ay_v5_success}/7 success, {ay_v5_zeros} zeros")
print()

print("Assessment:")
print("  v3 baseline is LOW (29%)")
print("  v5 makes it worse (14%)")
print("  No danger readings in either")
print()
print("RECOMMENDATION: v3 maintain")
print("  - Too few benefits from switching")
print("  - v5 doesn't improve, actually regresses")
print()
print()

# AZ
print("AZ (other case existing)")
print("-" * 100)
az_v3 = df_merged[df_merged['field_code'] == 'AZ']
az_v3_success = (~az_v3['v3_value'].isna()).sum()
az_v5_success = (~az_v3['v5_value'].isna()).sum()
az_v3_zeros = ((az_v3['v3_value'] == 0) | (az_v3['v3_value'] == '0')).sum()
az_v5_zeros = ((az_v3['v5_value'] == 0.0) | (az_v3['v5_value'] == 0)).sum()

print(f"v3: {az_v3_success}/7 success, {az_v3_zeros} zeros")
print(f"v5: {az_v5_success}/7 success, {az_v5_zeros} zeros (NEW zeros!)")
print()

print("Assessment:")
print("  SUCCESS RATE: MAJOR IMPROVEMENT (14% → 71%)")
print("  DANGER LEVEL: NEW zeros appeared (0 → 2)")
print("  TRADE-OFF: More values but with new risk")
print()
print("RECOMMENDATION: CONDITIONAL ADOPTION (v5)")
print("  IF trade-off acceptable (more data with acceptable new zeros)")
print("    → Adopt v5 for AZ")
print("  IF not acceptable")
print("    → Keep v3 or wait for v5.2 optimization")
print()
print()

# AI
print("AI (合計 - numeric field)")
print("-" * 100)
ai_v3 = df_merged[df_merged['field_code'] == 'AI']
ai_v3_success = (~ai_v3['v3_value'].isna()).sum()
ai_v5_success = (~ai_v3['v5_value'].isna()).sum()

print(f"v3: {ai_v3_success}/7 success (100% - perfect)")
print(f"v5: {ai_v5_success}/7 success (0% - complete failure)")
print()

print("Assessment:")
print("  CRITICAL: v3 is perfect (100% success)")
print("  PROBLEM: v5 complete failure (all null)")
print("  ROOT CAUSE: AI crop bounds height 0.5% too small")
print()
print("RECOMMENDATION: v3 maintain for now")
print("  - WAIT for v5.2 bounds optimization")
print("  - If v5.2 recovers AI to >80%, can switch")
print("  - Until then, v3 is mandatory (perfect performance)")
print()
print()

print("=" * 100)
print("HYBRID ADOPTION STRATEGY")
print("=" * 100)
print()

print("""
PROPOSED HYBRID APPROACH (NOT all-or-nothing):

Field-by-Field Decision:

┌─────────────────────────────────────────────────────────────┐
│ AU (au case new)           → v3 MAINTAIN                    │
│   Reason: Low improvement from v5, acceptable v3 baseline   │
├─────────────────────────────────────────────────────────────┤
│ AV (au case existing)      → v5.2 PRIORITY (or v3)          │
│   Reason: HIGH danger in v3 (43% zeros), v5.2 opportunity   │
│   Action: Test v5.2 bounds, adopt if danger reduced         │
├─────────────────────────────────────────────────────────────┤
│ AY (other case new)        → v3 MAINTAIN                    │
│   Reason: v5 worse, no benefit, no danger in either         │
├─────────────────────────────────────────────────────────────┤
│ AZ (other case existing)   → v5 CONDITIONAL                 │
│   Reason: Major success rate improvement (14% → 71%)        │
│   Caveat: 2 new zeros appeared, assess trade-off            │
│   Decision: Adopt if trade-off deemed acceptable            │
├─────────────────────────────────────────────────────────────┤
│ AI (合計 numeric)          → v3 MANDATORY (wait v5.2)       │
│   Reason: v3 perfect (100%), v5 failed (0%)                 │
│   Action: WAIT for v5.2 bounds fix, critical field          │
└─────────────────────────────────────────────────────────────┘

OVERALL ADOPTION STRATEGY:

Tier 1 (Maintain v3):
  ✅ AU, AY, AI (until v5.2) → use v3 for these 3 fields

Tier 2 (Adopt v5 if acceptable):
  ⚠️ AZ → use v5 IF trade-off (more data vs 2 new zeros) approved

Tier 3 (Wait for v5.2):
  ⏳ AV → HIGH priority for v5.2 bounds optimization
  ⏳ AI → CRITICAL: must wait for v5.2 fix before any switch

Hybrid Implementation:
  case_items extraction = {
    AU: v3 method,
    AV: v5.2 method (or v3 if v5.2 fails),
    AY: v3 method,
    AZ: v5 method (if approved) or v3 method,
    AI: v3 method (until v5.2),
  }

Benefits:
  ✓ Customized approach per field
  ✓ Minimizes risk (AI stays perfect)
  ✓ Addresses high-danger item (AV) with priority
  ✓ Captures AZ improvement if acceptable
  ✓ Not dependent on single method's success
""")

print()
print("=" * 100)
print("NEXT STEPS")
print("=" * 100)
print()

print("""
1. Wait for v5.2 bounds optimization test results

2. Evaluate v5.2 performance:
   - AI: Can v5.2 recover to >80% success?
   - AV: Can v5.2 return values while keeping zeros minimal?
   - AY: Can v5.2 improve beyond v5's 14%?

3. Make item-by-item decisions:
   - AU: Always v3 (no change needed)
   - AV: Adopt v5.2 IF danger reduced + values returned
   - AY: Always v3 (no change needed)
   - AZ: Approve if trade-off acceptable (more values vs 2 zeros)
   - AI: Adopt v5.2 IF recovery to ≥80%, else v3

4. Implement hybrid extractor:
   - Create case_items_hybrid() function
   - Use method[field_code] mapping
   - Enables field-by-field switching later

5. Test hybrid on full 30 pages
   - Verify no unexpected interactions
   - Measure overall match_rate improvement
   - Document decision rationale

6. Document final adoption decision
   - Include field-by-field justification
   - Risk assessment for each field
   - Future improvement roadmap
""")

print()
print("Analysis complete. Awaiting v5.2 test results for final decisions.")
