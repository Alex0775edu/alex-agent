with open('core/intent_engine.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Add pattern declaration
target1 = """        # 15. Open Application"""
replacement1 = """        # 14h. SkillSum Resume Automation
        self.skillsum_patterns = [
            r"^(?:alex\\s*,?\\s*)?(?:skillsum\\s+)?(?:evaluate|parse|analyze|process)\\s+resume\\s+(.+)$",
            r"^(?:alex\\s*,?\\s*)?(?:skillsum\\s+)?resume\\s+(.+?)\\s+(?:ko\\s*)?(?:evaluate|analyze|parse|check)\\s*(?:karo|kar\\s*do)?$",
        ]

        # 15. Open Application"""

# 2. Add pattern match in parse()
target2 = """        for p in self.search_files_patterns:"""
replacement2 = """        # 14h. SkillSum Resume Automation
        for p in self.skillsum_patterns:
            m = re.match(p, clean, flags=re.IGNORECASE)
            if m:
                path_val = m.group(1).strip()
                return IntentResult("SKILLSUM_RESUME_EVAL", 0.96, {"resume_path": path_val}, lang, is_local_command=True)

        for p in self.search_files_patterns:"""

# 3. Add handler in execute_local_command()
target3 = """        if res.intent == "PROJECT_SWITCH":"""
replacement3 = """        if res.intent == "SKILLSUM_RESUME_EVAL":
            from actions.skillsum_automation import skillsum_service
            resume_path = res.slots.get("resume_path", "").strip()
            report = skillsum_service.process_candidate_resume(resume_path)
            res.handled = True
            if report.success:
                res.response_text = (
                    f"{OWNER_ADDRESS}, candidate '{report.candidate.candidate_name}' ka resume evaluate ho gaya hai. "
                    f"Match Score: {report.evaluation.match_score_pct}%. Report save kar di gayi hai at '{report.markdown_path}'."
                )
            else:
                res.response_text = f"{OWNER_ADDRESS}, resume processing mein error: {report.error_message}"
            return res

        if res.intent == "PROJECT_SWITCH":"""

assert target1 in c, "target1 not found"
assert target2 in c, "target2 not found"
assert target3 in c, "target3 not found"

c = c.replace(target1, replacement1, 1)
c = c.replace(target2, replacement2, 1)
c = c.replace(target3, replacement3, 1)

with open('core/intent_engine.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("SUCCESS: intent_engine.py updated")

