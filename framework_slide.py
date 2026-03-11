"""
Single PPT slide: How reward is generated + where human intervenes.
Episode timeline view.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

fig, ax = plt.subplots(figsize=(20, 11.25))
BG = '#0f172a'
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 100)
ax.set_ylim(0, 56.25)
ax.axis('off')

SURFACE = '#1e293b'; BORDER = '#475569'
ACCENT = '#818cf8'; CYAN = '#06b6d4'; GREEN = '#10b981'
RED = '#ef4444'; ORANGE = '#f59e0b'; TEXT = '#e2e8f0'; MUTED = '#94a3b8'

def rbox(x, y, w, h, fc, ec=None, alpha=0.18, lw=2, zorder=2):
    r = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3",
                        facecolor=(*matplotlib.colors.to_rgb(fc), alpha),
                        edgecolor=ec or fc, linewidth=lw, zorder=zorder)
    ax.add_patch(r)

def txt(x, y, s, fs=10, c=TEXT, fw='normal', ha='center', va='center', zorder=5, style='normal'):
    ax.text(x, y, s, fontsize=fs, color=c, fontweight=fw, ha=ha, va=va,
            zorder=zorder, fontstyle=style)

def arr(x1, y1, x2, y2, c=ACCENT, lw=2.5, rad=0):
    conn = f'arc3,rad={rad}'
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=c, lw=lw,
                                connectionstyle=conn), zorder=4)

def arr_label(x, y, s, c=MUTED, fs=8):
    ax.text(x, y, s, fontsize=fs, color=c, ha='center', va='center', zorder=6,
            bbox=dict(boxstyle='round,pad=0.25', facecolor=BG, edgecolor='none', alpha=0.9))

# ══════════════════════════════════════════════════════
# TITLE
# ══════════════════════════════════════════════════════
txt(50, 55, 'Sentinel-KG: Reward Generation & Human-in-the-Loop',
    fs=20, fw='bold')

# ══════════════════════════════════════════════════════
# LEFT HALF: EPISODE FLOW (how reward accumulates)
# ══════════════════════════════════════════════════════

txt(27, 52.5, 'One Episode: How Reward Accumulates', fs=14, fw='bold', c=ORANGE)

# Timeline backbone
Y_TOP = 49; Y_BOT = 4
ax.plot([6, 6], [Y_BOT, Y_TOP], color=BORDER, lw=2, zorder=1)

# ── Step 0: Spawn ──
y = 48
ax.plot(6, y, 'o', color=ACCENT, markersize=10, zorder=5)
txt(6, y+1, 'START', fs=8, c=MUTED, fw='bold')
rbox(9, y-1.5, 38, 3, ACCENT, alpha=0.08, lw=1)
txt(28, y+0.3, 'Spawn at seed node (70% threat seed, 30% random)', fs=9, c=TEXT, ha='center')
txt(28, y-0.7, 'Initial evidence = [start_node].  Clearance = Level 0 (financial + corporate only)', fs=8, c=MUTED)

# ── Steps 1-N: Explore ──
y = 42.5
ax.plot(6, y, 'o', color=CYAN, markersize=10, zorder=5)
txt(6, y+1.2, 'EXPLORE', fs=8, c=CYAN, fw='bold')
rbox(9, y-3.5, 38, 7, CYAN, alpha=0.08, lw=1)
txt(28, y+2.5, 'explore_node(i)  →  move to visible neighbor', fs=10, c=CYAN, fw='bold')
txt(13, y+1, 'Per-step rewards:', fs=9, c=TEXT, ha='left')

# reward breakdown
items = [
    ('Visit threat node',     '+0.06',  GREEN, '= α × 0.2 = 0.3 × 0.2'),
    ('Visit benign node',     '−0.30',  RED,   '= −γ × 0.3 = −1.0 × 0.3'),
    ('Visit benign near threat', '−0.05', ORANGE, '= −γ × 0.05 (lesser penalty)'),
    ('Low-confidence ER link (<0.6)', '−0.10', RED, '= −γ × 0.1 (don\'t trust bad links)'),
    ('Efficiency cost (every step)',  '−0.001', MUTED, '= −β × 0.01'),
]
for i, (desc, val, col, expl) in enumerate(items):
    yy = y + 0.0 - i * 1.15
    txt(14, yy, desc, fs=8, c=MUTED, ha='left')
    txt(35, yy, val, fs=9, c=col, fw='bold', ha='center')
    txt(43, yy, expl, fs=7, c=BORDER, ha='left')

# KEY INSIGHT
rbox(9, y-3.3, 38, 1.5, RED, alpha=0.10, lw=1.5)
txt(28, y-2.6, 'Visiting one innocent person costs 5× more than finding one criminal  →  agent learns precision',
    fs=8, c=RED, style='italic')

# ── Optional: Request Clearance ──
y = 33
ax.plot(6, y, 'o', color=ORANGE, markersize=10, zorder=5)
txt(6, y+1.2, 'CLEARANCE', fs=8, c=ORANGE, fw='bold')
rbox(9, y-2, 38, 4, ORANGE, alpha=0.08, lw=1)
txt(28, y+1.2, 'request_clearance()  →  HUMAN DECIDES', fs=10, c=ORANGE, fw='bold')
txt(14, y-0.0, 'Approved (80%):  window widens to Personal edges', fs=8.5, c=GREEN, ha='left')
txt(38, y-0.0, '−0.05', fs=9, c=ORANGE, fw='bold')
txt(14, y-1.1, 'Denied (20%):  window stays narrow', fs=8.5, c=RED, ha='left')
txt(38, y-1.1, '−0.10', fs=9, c=RED, fw='bold')

# human icon
txt(49, y+0.5, '← HUMAN', fs=10, c=GREEN, fw='bold', ha='left')

# ── Continue exploring ──
y = 29.5
ax.plot([6, 6], [30.5, 29], color=BORDER, lw=2, ls=':', zorder=1)
txt(6, y+0.5, '...', fs=12, c=BORDER)
txt(12, y+0.5, 'continue exploring (accumulating reward)', fs=8, c=MUTED, ha='left')

# ── Submit ──
y = 25
ax.plot(6, y, 'o', color=GREEN, markersize=10, zorder=5)
txt(6, y+1.2, 'SUBMIT', fs=8, c=GREEN, fw='bold')
rbox(9, y-4.5, 38, 6, GREEN, alpha=0.08, lw=1)
txt(28, y+0.7, 'submit_evidence_bundle()  →  episode ends', fs=10, c=GREEN, fw='bold')

txt(14, y-0.5, 'Submission reward:', fs=9, c=TEXT, ha='left')
sub_items = [
    ('F1(precision, recall) of evidence vs cluster', 'α · F1 · 10', ACCENT),
    ('Efficiency bonus (faster = better)',           'β · (1 − steps/50) · 5', CYAN),
    ('Anti-hallucination (unvisited evidence)',      '−γ · 2.0 × count', RED),
]
for i, (desc, formula, col) in enumerate(sub_items):
    yy = y - 1.5 - i * 1.1
    txt(14, yy, desc, fs=8, c=MUTED, ha='left')
    txt(43, yy, formula, fs=8, c=col, fw='bold', ha='left')

# ── OR: Budget exceeded ──
y = 18
ax.plot(6, y, 'o', color=RED, markersize=10, zorder=5)
txt(6, y+1, 'TIMEOUT', fs=8, c=RED, fw='bold')
rbox(9, y-1, 20, 2, RED, alpha=0.10, lw=1)
txt(19, y, '50 steps exceeded → −0.5 penalty', fs=9, c=RED)

# ── Total ──
y = 14.5
rbox(5, y-1.5, 42, 3.5, ORANGE, alpha=0.12, lw=2)
txt(26, y+0.8, 'Total Episode Reward  =  Σ (per-step rewards)  +  submission reward', fs=11, c=ORANGE, fw='bold')
txt(26, y-0.3, 'This total reward is the signal that updates the agent\'s LoRA policy via PPO', fs=9, c=TEXT)

arr(26, y-1.5, 26, y-3.5, ORANGE, lw=2.5)
rbox(13, y-6.5, 26, 2.5, ACCENT, alpha=0.12, lw=2)
txt(26, y-5.3, 'Policy Update (PPO → LoRA adapters)', fs=11, c=ACCENT, fw='bold')

# ══════════════════════════════════════════════════════
# RIGHT HALF: WHERE HUMAN ENTERS
# ══════════════════════════════════════════════════════

RX = 73
txt(RX, 52.5, 'Where Human Enters', fs=14, fw='bold', c=GREEN)

# ── Intervention 1: Semantic Window ──
rbox(55, 43, 36, 8, GREEN, alpha=0.10, lw=2)
ax.add_patch(plt.Circle((58, 47.5), 1.5, color=GREEN, alpha=0.2, zorder=3))
txt(58, 47.5, '1', fs=16, c=GREEN, fw='bold')
txt(RX, 49.5, 'During Episode: Semantic Window Gate', fs=12, fw='bold', c=GREEN)
txt(RX, 47.8, 'Agent calls request_clearance() → human approves or denies', fs=9, c=TEXT)
txt(RX, 46.5, 'Effect: unlocks personal edges (employment, benefits, addresses)', fs=9, c=MUTED)
txt(RX, 45.2, 'Design: agent must justify privacy intrusion to a human', fs=9, c=ORANGE, style='italic')
txt(RX, 43.8, 'This is NOT a formality — 20% denial rate during training', fs=8, c=RED)

# ── Intervention 2: Evidence Review ──
rbox(55, 32.5, 36, 9.5, GREEN, alpha=0.10, lw=2)
ax.add_patch(plt.Circle((58, 37.5), 1.5, color=GREEN, alpha=0.2, zorder=3))
txt(58, 37.5, '2', fs=16, c=GREEN, fw='bold')
txt(RX, 40.5, 'After Episode: Evidence Review', fs=12, fw='bold', c=GREEN)
txt(RX, 39, 'Evidence bundle passes through G1-G6 guardrails first', fs=9, c=TEXT)
txt(RX, 37.7, 'Then presented to human operator:', fs=9, c=TEXT)
txt(62, 36.2, '•  Evidence shown FIRST, agent conclusion HIDDEN', fs=8.5, c=MUTED, ha='left')
txt(62, 35, '•  Operator must write reasoning', fs=8.5, c=MUTED, ha='left')
txt(62, 33.8, '•  Mandatory alternative (benign) hypothesis', fs=8.5, c=MUTED, ha='left')
txt(RX, 32.8, 'Prevents anchoring bias — human thinks independently', fs=8, c=GREEN, style='italic')

# ── Intervention 3: Anti-rubber-stamp ──
rbox(55, 24, 36, 7.5, ORANGE, alpha=0.10, lw=2)
ax.add_patch(plt.Circle((58, 28.5), 1.5, color=ORANGE, alpha=0.2, zorder=3))
txt(58, 28.5, '3', fs=16, c=ORANGE, fw='bold')
txt(RX, 30, 'Safeguard: Anti-Rubber-Stamp', fs=12, fw='bold', c=ORANGE)
txt(RX, 28.5, 'System monitors operator approval rates', fs=9, c=TEXT)
txt(RX, 27.2, 'Risk-tiered routing with escalation:', fs=9, c=TEXT)
txt(62, 25.8, 'Low → analyst  |  Medium → senior + reasoning', fs=8.5, c=MUTED, ha='left')
txt(62, 24.7, 'High → + deliberation delay  |  Critical → dual approval', fs=8.5, c=MUTED, ha='left')

# ── Intervention 4: Oversight ──
rbox(55, 17, 36, 6, CYAN, alpha=0.10, lw=2)
ax.add_patch(plt.Circle((58, 20.5), 1.5, color=CYAN, alpha=0.2, zorder=3))
txt(58, 20.5, '4', fs=16, c=CYAN, fw='bold')
txt(RX, 21.8, 'Meta-Level: Democratic Oversight', fs=12, fw='bold', c=CYAN)
txt(RX, 20.3, 'Full audit trail (SHA-256 hash chain)', fs=9, c=TEXT)
txt(RX, 19, 'Oversight body can halt pipeline at any time', fs=9, c=TEXT)
txt(RX, 17.7, 'Riksdag: 3-year sunset review — system must justify continued existence', fs=8.5, c=MUTED)

# ── Bottom: the key message ──
rbox(52, 8, 44, 7, RED, alpha=0.08, lw=2)
txt(74, 13.5, 'Why This Design Works', fs=13, fw='bold', c=RED)
txt(74, 11.8, 'Reward encodes constitutional constraint:  γ >> α', fs=10, c=TEXT)
txt(74, 10.5, '→ Agent internally learns "don\'t surveil innocent people"', fs=9, c=ORANGE)
txt(74, 9.2, 'Human is not just a checkbox — 4 layers of meaningful intervention', fs=9, c=GREEN)
txt(74, 7.9, '(window gate, evidence review, anti-rubber-stamp, democratic sunset)', fs=8, c=MUTED)

plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
plt.savefig('/Users/yifan/NatioanlSecurity/framework_slide.png', dpi=200,
            facecolor=BG, bbox_inches='tight', pad_inches=0.3)
print("Saved → framework_slide.png")
