with open('ui.py', 'r', encoding='utf-8') as f:
    c = f.read()

target = """                lines_t = [f"\u25c8 AUTONOMOUS TASK CENTER (Autonomy: {d.get('autonomy_level', 'supervised').upper()})"]
                for t in tasks[:8]:
                    lines_t.append(f"  \u2022 [{t.get('status', 'PENDING').upper()}] {t.get('title', 'Task')}")"""

replacement = """                autonomy = d.get('autonomy_level', 'NORMAL').upper()
                lines_t = [f"\u25c8 AUTONOMOUS TASK CENTER (Autonomy: {autonomy})", ""]
                for t in tasks[:10]:
                    status = t.get('status', 'PENDING').upper()
                    goal = t.get('goal') or t.get('title', 'Task')
                    cur_step = t.get('current_step', 0)
                    tot_steps = t.get('total_steps', 0)
                    files = t.get('generated_files', [])
                    line = f"  \u2022 [{status}] {goal}"
                    if tot_steps > 0:
                        line += f" ({cur_step}/{tot_steps} steps)"
                    if files:
                        line += f"\\n      Deliverable: {files[0]}"
                    lines_t.append(line)"""

if target in c:
    c = c.replace(target, replacement, 1)
    with open('ui.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print("SUCCESS")
else:
    print("TARGET NOT FOUND")

